"""
境町拠点（GS境）専用 配送スケジュール最適化エンジン。

実データに基づく情報:
  ・冷蔵庫: 第一(120P) / 第二(120P) / 第三(124P) = 計364パレット
  ・商品: GS境玉レタス / GS境サニー / GS境Gリーフ / GSキャベツ / 本社原料キャベツ
  ・スタッフ: 宮下・奥野・斎藤・大久保・伊藤・新井 の6名
  ・外注: 明信運輸①②③④（繁忙期は最大4台）
  ・主要納品先: アスカット / ヤオコー / カネミ食品 / ヨシケイ栃木 / DIC信濃川上 等
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal

# ──────────────────────────────────────────────
# 定数定義
# ──────────────────────────────────────────────

REFRIGERATORS = {
    "第一冷蔵庫": {"capacity": 120, "priority": 1},
    "第二冷蔵庫": {"capacity": 120, "priority": 2},
    "第三冷蔵庫": {"capacity": 124, "priority": 3},  # バッファ庫
}
TOTAL_CAPACITY = sum(r["capacity"] for r in REFRIGERATORS.values())  # 364 パレット

PRODUCTS = [
    "GS境玉レタス", "GS境サニー", "GS境Gリーフ",
    "GSキャベツ", "本社原料キャベツ", "GS経由商品保管", "お米",
]

STAFF = {
    "宮下清隆":  {"shift_start": "06:30", "role": "倉庫主任", "days": 5},
    "奥野":      {"shift_start": "07:30", "role": "配送・GSS", "days": 5},
    "斎藤良":    {"shift_start": "07:30", "role": "境町給食担当", "days": 5},
    "大久保誠":  {"shift_start": "07:30", "role": "配送", "days": 5},
    "伊藤将真":  {"shift_start": "08:00", "role": "配送", "days": 5},
    "新井里美":  {"shift_start": "09:00", "role": "配送・コンテナ回収", "days": 5},
}

OUTSOURCED_TRUCKS = {
    "明信運輸①": {"capacity_pallets": 10, "shift": "07:30"},
    "明信運輸②": {"capacity_pallets": 10, "shift": "07:30"},
    "明信運輸③": {"capacity_pallets": 10, "shift": "07:30"},
    "明信運輸④": {"capacity_pallets": 10, "shift": "08:00"},
}

# 主要納品先と優先度・推奨統合ルート
DELIVERY_POINTS = {
    # name: { priority(1=高), area, weekly_freq }
    "アスカット":      {"priority": 1, "area": "埼玉北", "weekly_freq": 4},
    "ヤオコー":        {"priority": 1, "area": "埼玉",   "weekly_freq": 3},
    "カネミ食品":      {"priority": 1, "area": "埼玉",   "weekly_freq": 4},
    "ヨシケイ栃木":    {"priority": 1, "area": "栃木",   "weekly_freq": 3},
    "DIC信濃川上":     {"priority": 2, "area": "長野",   "weekly_freq": 5},
    "マルエツ":        {"priority": 2, "area": "埼玉",   "weekly_freq": 3},
    "ロピア":          {"priority": 2, "area": "埼玉",   "weekly_freq": 2},
    "ピックルス":      {"priority": 2, "area": "群馬",   "weekly_freq": 2},
    "ヤマダイフーズ":  {"priority": 2, "area": "埼玉",   "weekly_freq": 3},
    "デセールクレア":  {"priority": 3, "area": "東京",   "weekly_freq": 2},
    "東京シティ":      {"priority": 3, "area": "東京",   "weekly_freq": 2},
    "オーケー東扇島":  {"priority": 3, "area": "東京",   "weekly_freq": 2},
    "元気寿司":        {"priority": 3, "area": "埼玉",   "weekly_freq": 1},
    "丸庄":            {"priority": 3, "area": "群馬",   "weekly_freq": 2},
    "とりせん":        {"priority": 3, "area": "栃木",   "weekly_freq": 1},
    "境町給食":        {"priority": 1, "area": "境町",   "weekly_freq": 5},  # 毎日固定
}

# 推奨統合ルート（同エリア便の組み合わせ）
RECOMMENDED_COMBINED_ROUTES = [
    {"route_name": "埼玉北ルート", "stops": ["アスカット", "ヤオコー", "カネミ食品"], "area": "埼玉"},
    {"route_name": "栃木ルート",   "stops": ["ヨシケイ栃木", "とりせん"],             "area": "栃木"},
    {"route_name": "東京ルート",   "stops": ["東京シティ", "オーケー東扇島", "デセールクレア"], "area": "東京"},
    {"route_name": "群馬ルート",   "stops": ["ピックルス", "丸庄", "ヤマダイフーズ"], "area": "群馬"},
]


# ──────────────────────────────────────────────
# シーズン判定
# ──────────────────────────────────────────────

SeasonType = Literal["繁忙期", "通常期", "閑散期"]

def detect_season(
    avg_occupancy_pct: float,
    month: int | None = None,
) -> SeasonType:
    """
    冷蔵庫平均占有率 と 月 からシーズンを自動判定する。
    ・繁忙期 (Busy)    : 占有率 70%以上 または 夏季(7-9月)
    ・通常期 (Normal)  : 占有率 50-70%
    ・閑散期 (Slack)   : 占有率 50%未満
    """
    # 月ベースのヒント
    if month is not None:
        if month in (7, 8, 9):     # 夏=繁忙
            occupancy_bias = +15
        elif month in (1, 2):      # 冬=閑散
            occupancy_bias = -10
        else:
            occupancy_bias = 0
        effective = avg_occupancy_pct + occupancy_bias
    else:
        effective = avg_occupancy_pct

    if effective >= 70:
        return "繁忙期"
    if effective >= 50:
        return "通常期"
    return "閑散期"


# ──────────────────────────────────────────────
# スケジュール最適化
# ──────────────────────────────────────────────

@dataclass
class SchedulePlan:
    season: SeasonType
    avg_occupancy: float
    ref1_occupancy: float
    ref2_occupancy: float
    ref3_occupancy: float
    # 推奨スタッフ配置
    staff_assignments: dict = field(default_factory=dict)
    # 推奨トラック台数
    trucks_needed: int = 2
    # 推奨出発時刻
    loading_start: str = "07:30"
    # ルート推奨
    priority_routes: list = field(default_factory=list)
    combined_routes: list = field(default_factory=list)
    # アラート
    alerts: list[str] = field(default_factory=list)
    # 節約効果
    estimated_savings: str = ""


def optimize_schedule(
    ref1_pct: float,
    ref2_pct: float,
    ref3_pct: float,
    weekday: int = 1,   # 0=月曜
    month: int | None = None,
    special_events: list[str] | None = None,
) -> SchedulePlan:
    """
    3冷蔵庫の占有率から最適な配送スケジュールを生成する。

    Args:
        ref1_pct: 第一冷蔵庫占有率 (%)
        ref2_pct: 第二冷蔵庫占有率 (%)
        ref3_pct: 第三冷蔵庫占有率 (%)
        weekday:  曜日 (0=月, 1=火, ..., 6=日)
        month:    月 (1〜12)
        special_events: ["境町給食", "棚卸"] など
    """
    avg_occ = (ref1_pct * 120 + ref2_pct * 120 + ref3_pct * 124) / 364
    season = detect_season(avg_occ, month)
    plan = SchedulePlan(
        season=season,
        avg_occupancy=avg_occ,
        ref1_occupancy=ref1_pct,
        ref2_occupancy=ref2_pct,
        ref3_occupancy=ref3_pct,
    )
    special_events = special_events or []

    # ── 繁忙期 ────────────────────────────────
    if season == "繁忙期":
        plan.trucks_needed = 3 if avg_occ < 85 else 4
        plan.loading_start = "06:30"
        plan.staff_assignments = {
            "宮下清隆": "06:30 倉庫管理・積込指揮",
            "奥野":     "07:30 GSS業務 + ソイル集荷",
            "斎藤良":   "07:30 境町給食 + 本社便",
            "大久保誠": "07:30 明信運輸①同行・東京ルート",
            "伊藤将真": "07:30 明信運輸②同行・栃木ルート",
            "新井里美": "09:00 コンテナ回収・アスカット",
        }
        plan.priority_routes = ["境町給食", "アスカット", "ヤオコー", "カネミ食品"]
        plan.combined_routes = RECOMMENDED_COMBINED_ROUTES
        plan.alerts = []
        if ref1_pct >= 90:
            plan.alerts.append("🔴 第一冷蔵庫が満杯に近い！当日出荷便を最優先してください。")
        if ref2_pct >= 90:
            plan.alerts.append("🔴 第二冷蔵庫が満杯に近い！翌日分まで含めて出荷スケジュールを前倒しください。")
        if ref3_pct >= 85:
            plan.alerts.append("🟡 第三冷蔵庫（バッファ庫）も逼迫しています。外注追加便を検討してください。")
        plan.estimated_savings = "外注最大4台フル活用 / 6:30早出しで出荷リードタイム確保"

    # ── 通常期 ────────────────────────────────
    elif season == "通常期":
        plan.trucks_needed = 2
        plan.loading_start = "07:30"
        plan.staff_assignments = {
            "宮下清隆": "06:30 倉庫管理・朝積込",
            "奥野":     "07:30 GSS業務",
            "斎藤良":   "07:30 境町給食",
            "大久保誠": "07:30 配送（埼玉北ルート）",
            "伊藤将真": "08:00 配送（栃木ルート）",
            "新井里美": "09:00 コンテナ回収",
        }
        plan.priority_routes = ["境町給食", "アスカット", "カネミ食品"]
        plan.combined_routes = [r for r in RECOMMENDED_COMBINED_ROUTES if r["area"] != "東京"]
        if ref2_pct >= 80:
            plan.alerts.append("🟡 第二冷蔵庫が高占有率です。週内に出荷量を増やす調整を検討してください。")
        plan.estimated_savings = "明信運輸2台体制で外注費 約25%削減 / ルート統合で走行距離10〜15%削減見込み"

    # ── 閑散期 ────────────────────────────────
    else:
        plan.trucks_needed = 1
        plan.loading_start = "08:00"
        plan.staff_assignments = {
            "宮下清隆": "08:00 倉庫管理",
            "奥野":     "08:00 GSS業務",
            "斎藤良":   "07:30 境町給食",
            "大久保誠": "08:00 配送（統合ルート）",
            "伊藤将真": "公休または応援",
            "新井里美": "09:00 コンテナ回収（週3日）",
        }
        plan.priority_routes = ["境町給食"]
        plan.combined_routes = [
            {"route_name": "埼玉統合ルート", "stops": ["アスカット", "ヤオコー", "カネミ食品", "マルエツ"], "area": "埼玉"},
        ]
        plan.alerts = ["🟢 閑散期モード：外注1台体制で運用。棚卸・施設メンテナンスを推奨します。"]
        plan.estimated_savings = "外注1台体制で外注費 約60%削減 / スタッフ休暇消化・教育訓練に適したタイミング"

    # ── 曜日別調整 ────────────────────────────
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    if weekday == 0:  # 月曜
        plan.alerts.append(f"📅 月曜日：週初め出荷量が集中しやすいです。積込を15分前倒し推奨。")
    if weekday == 4:  # 金曜
        plan.alerts.append(f"📅 金曜日：週末分まとめ出荷の可能性あり。トラック積載量を事前確認してください。")
    if weekday in (5, 6):  # 土日
        plan.alerts.append(f"📅 週末：固定配送（DIC信濃川上）の確認を忘れずに。")

    # ── 特殊イベント調整 ──────────────────────
    if "棚卸" in special_events:
        plan.alerts.append("📋 棚卸実施日：宮下・大久保を棚卸に優先配置。配送は外注中心で対応してください。")
    if "訓練日" in special_events:
        plan.alerts.append("🚒 訓練日：伊藤将真は午前不在。ルート再割り当てが必要です。")

    return plan


def get_weekly_plan(
    weekly_occupancy: list[tuple[float, float, float]],
    month: int | None = None,
) -> list[SchedulePlan]:
    """
    1週間分（月〜金）の最適スケジュールをまとめて生成する。
    weekly_occupancy: [(ref1%, ref2%, ref3%), ...] 月曜〜金曜
    """
    plans = []
    for i, (r1, r2, r3) in enumerate(weekly_occupancy[:5]):
        plan = optimize_schedule(r1, r2, r3, weekday=i, month=month)
        plans.append(plan)
    return plans


def get_seasonal_strategy(season: SeasonType) -> dict:
    """繁忙期・閑散期ごとの戦略サマリーを返す。"""
    strategies = {
        "繁忙期": {
            "外注台数":    "3〜4台（明信運輸①②③ 毎日 + ④ 必要時）",
            "積込開始":    "6:30（宮下リード）",
            "重点施策":    "・出荷最優先でストレージ圧縮\n・高積載率ルートを統合して空走をゼロに\n・第三冷蔵庫をバッファ活用",
            "KPI目標":    "積載率80%以上 / 第一・第二冷蔵庫 90%以下に維持",
            "注意事項":   "・DIC信濃川上（長野）は毎日固定便のため削減不可\n・境町給食は学校カレンダーに従い変動",
        },
        "通常期": {
            "外注台数":    "2台（明信運輸①②）",
            "積込開始":    "7:30",
            "重点施策":    "・同エリア便の統合でコスト削減\n・帰り荷の確保検討（外部貨物）\n・翌週繁忙期への準備",
            "KPI目標":    "積載率70%以上 / 外注費25%削減",
            "注意事項":   "・週末に翌週の占有率予測を確認\n・月次棚卸は通常期に実施推奨",
        },
        "閑散期": {
            "外注台数":    "1台（明信運輸①のみ）",
            "積込開始":    "8:00",
            "重点施策":    "・全エリアを1ルートに統合\n・スタッフ有給休暇消化・教育訓練\n・施設メンテナンス（冷蔵庫点検）",
            "KPI目標":    "外注費60%削減 / スタッフ有給消化率向上",
            "注意事項":   "・DIC信濃川上のみ毎日維持\n・閑散期でも境町給食は継続（学校カレンダー確認）",
        },
    }
    return strategies[season]


def build_schedule_dataframe(plan: SchedulePlan) -> pd.DataFrame:
    """スケジュールプランを表形式 DataFrame に変換する。"""
    rows = []
    for name, assignment in plan.staff_assignments.items():
        rows.append({
            "担当者": name,
            "配置・業務": assignment,
            "役割": STAFF.get(name, {}).get("role", ""),
        })
    # 外注
    trucks = list(OUTSOURCED_TRUCKS.keys())[:plan.trucks_needed]
    for t in trucks:
        rows.append({
            "担当者": t,
            "配置・業務": f"{OUTSOURCED_TRUCKS[t]['shift']} 出荷（積載率目標80%以上）",
            "役割": "外注配送",
        })
    return pd.DataFrame(rows)
