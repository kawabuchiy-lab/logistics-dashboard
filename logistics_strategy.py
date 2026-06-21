"""
舞台ファーム 物流プラットフォーム戦略モジュール
─────────────────────────────────────────────────
◆ 対サラダボウル差別化戦略
◆ 3拠点最適化（GS境 / KIFA川越 / 中越通運羽生）
◆ 関東全域カバー　リード2タイム配送体制
◆ プラットフォーム戦略 KPI 管理シート
"""

from __future__ import annotations
import datetime
import math
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import folium
from folium import plugins

# ═══════════════════════════════════════════════════════════
# 1. 拠点マスタ
# ═══════════════════════════════════════════════════════════

HUBS: dict[str, dict] = {
    "GS境（自社冷蔵）": {
        "coords":          (36.2215, 139.8340),
        "capacity_pallets": 364,
        "monthly_cost_yen": 500_000,      # 自社運営：固定費ベース
        "cost_per_pallet":   1_380,       # 1パレットあたり保管単価
        "status":          "稼働中",
        "type":            "自社冷蔵倉庫",
        "coverage_km":      90,
        "lead_time_h":      2.0,
        "strength":        "大容量・自社コントロール・生産直結",
        "weakness":        "都心まで距離あり（高速使用で1.5〜2h）",
        "color":           "#1565C0",
        "icon":            "🏭",
    },
    "KIFA川越（OEM連携）": {
        "coords":          (35.9252, 139.4853),
        "capacity_pallets": 200,
        "monthly_cost_yen": 1_800_000,    # 現状：高コスト
        "cost_per_pallet":   9_000,       # 1パレットあたりコスト（高い）
        "status":          "稼働中",
        "type":            "外部倉庫（OEM）",
        "coverage_km":      60,
        "lead_time_h":      1.5,
        "strength":        "都心・埼玉南部・東京北西へのアクセス◎",
        "weakness":        "拠点利用料が高い・外部依存リスク",
        "color":           "#d73027",
        "icon":            "⚠️",
    },
    "中越通運（羽生）": {
        "coords":          (36.1724, 139.5867),
        "capacity_pallets": 150,
        "monthly_cost_yen": 900_000,      # KIFA比▲50%想定
        "cost_per_pallet":   6_000,       # 交渉余地あり
        "status":          "検討中",
        "type":            "3PL（外部物流委託）",
        "coverage_km":      75,
        "lead_time_h":      2.0,
        "strength":        "KIFA比コスト50%削減・関越道・東北道アクセス◎",
        "weakness":        "都心直送は距離があり要確認",
        "color":           "#4dac26",
        "icon":            "🔄",
    },
}

# 配送エリア × 優先拠点マトリクス
DELIVERY_ZONES: dict[str, dict] = {
    "東京都心圏":     {"coords": (35.6762, 139.6503), "priority": "S", "primary": "KIFA川越（OEM連携）", "secondary": "中越通運（羽生）", "monthly_demand_pallets": 60, "avg_revenue_per_pallet": 65000},
    "埼玉南部":       {"coords": (35.8617, 139.6455), "priority": "A", "primary": "KIFA川越（OEM連携）", "secondary": "中越通運（羽生）", "monthly_demand_pallets": 35, "avg_revenue_per_pallet": 58000},
    "埼玉北部・熊谷": {"coords": (36.1473, 139.3886), "priority": "A", "primary": "中越通運（羽生）",   "secondary": "GS境（自社冷蔵）",     "monthly_demand_pallets": 28, "avg_revenue_per_pallet": 55000},
    "栃木南部":       {"coords": (36.5600, 139.8800), "priority": "A", "primary": "GS境（自社冷蔵）",   "secondary": None,               "monthly_demand_pallets": 25, "avg_revenue_per_pallet": 52000},
    "茨城南部":       {"coords": (36.0800, 140.1100), "priority": "B", "primary": "GS境（自社冷蔵）",   "secondary": "中越通運（羽生）",   "monthly_demand_pallets": 20, "avg_revenue_per_pallet": 50000},
    "千葉北西":       {"coords": (35.7500, 139.9500), "priority": "B", "primary": "中越通運（羽生）",   "secondary": "KIFA川越（OEM連携）", "monthly_demand_pallets": 18, "avg_revenue_per_pallet": 56000},
    "群馬南東":       {"coords": (36.3912, 139.0608), "priority": "B", "primary": "中越通運（羽生）",   "secondary": "GS境（自社冷蔵）",   "monthly_demand_pallets": 15, "avg_revenue_per_pallet": 50000},
    "神奈川北部":     {"coords": (35.5500, 139.6000), "priority": "C", "primary": "KIFA川越（OEM連携）", "secondary": None,               "monthly_demand_pallets": 12, "avg_revenue_per_pallet": 60000},
}

# 競合（サラダボウル）プロファイル
COMPETITOR_PROFILE = {
    "name": "サラダボウル",
    "strength": ["大量・標準品の低価格供給", "全国流通網", "スーパー・量販店向け"],
    "weakness":  ["小ロット対応が弱い", "OEM・カスタム対応に時間がかかる", "産地直送の鮮度では不利", "外食・給食向け多品種に非効率"],
    "target_segment": "大型スーパー・量販チェーン（標準品・大量）",
}

BUTAI_DIFFERENTIATION = {
    "戦略コンセプト": "産地直結・鮮度最優先・OEM対応力でニッチ高付加価値市場を独占",
    "ターゲットセグメント": [
        "中規模外食チェーン（200〜500店舗）",
        "高級スーパー・食品専門店",
        "給食センター・病院・福祉施設",
        "食品メーカー（OEM原料供給）",
        "ECサイト（産直野菜定期便）",
    ],
    "差別化ポイント": [
        "農場→冷蔵庫→配送先の48時間以内完結（リード2体制）",
        "OEM対応（カット・袋詰め・ラベル）の一括提供",
        "多品種小ロット（1パレット単位〜）",
        "トレーサビリティ（産地・収穫日・担当者）",
        "3拠点連携による関東全域2時間以内配送",
    ],
}

# 戦略オプション提案
STRATEGY_OPTIONS: list[dict] = [
    {
        "name":     "①3拠点トライアングル体制",
        "category": "拠点最適化",
        "priority": "最優先",
        "summary":  "GS境（生産）→ 中越通運羽生（一次仕分け）→ KIFA川越（都市配送）のチェーンを構築。",
        "detail":   "GS境で収穫・一次加工→当日中に羽生でエリア別仕分け→翌朝にKIFA川越から都心配送。最短リード24〜36時間を実現。",
        "expected_cost_reduction": "▲15〜20%（KIFA川越への一極集中を分散）",
        "timeline": "3ヶ月",
        "kpi":      "拠点コスト合計・エリアカバー率・リードタイム",
    },
    {
        "name":     "②羽生センター優先移行（リスクヘッジ）",
        "category": "コスト削減",
        "priority": "高",
        "summary":  "KIFA川越の利用量を段階的に削減し、中越通運（羽生）へ移行。コスト▲50%。",
        "detail":   "現状KIFA月額¥180万→羽生で¥90万想定。差額¥90万/月=年間▲¥1,080万。川越は季節繁忙期のみ使用するハイブリッド体制へ。",
        "expected_cost_reduction": "▲¥90万/月（年間▲¥1,080万）",
        "timeline": "2ヶ月",
        "kpi":      "KIFA川越月額コスト・羽生稼働率・配送遅延率",
    },
    {
        "name":     "③産直ECサブスク便（新規収益）",
        "category": "新規事業",
        "priority": "中",
        "summary":  "B2C向け産直野菜定期便をGS境から直送。サラダボウルが手を出せない個人・飲食店向け小口市場。",
        "detail":   "週1回定期便・3種セット（玉レタス/サニー/Gリーフ）。ヤマト冷蔵と提携でラストワンマイル解決。固定収益で繁忙期の収益安定化。",
        "expected_cost_reduction": "新規売上 +¥200〜500万/月（初年度）",
        "timeline": "4〜6ヶ月",
        "kpi":      "サブスク契約数・定期便積載率・解約率",
    },
    {
        "name":     "④混載プラットフォーム（他社農産物受託）",
        "category": "稼働率向上",
        "priority": "中",
        "summary":  "自社トラックの空きスペースに他社農産物を混載受託。積載率70%→90%に引き上げ。",
        "detail":   "関東近郊の農家・農協からの混載受託。GS境発のトラックに同乗させることで1便あたり売上+20%。地産地消プラットフォームとして地域ブランド化。",
        "expected_cost_reduction": "輸送コスト効率 +25%（固定費を他社と分担）",
        "timeline": "3〜4ヶ月",
        "kpi":      "混載積載率・受託先数・1便あたり売上",
    },
    {
        "name":     "⑤大田市場・豊洲サテライト拠点",
        "category": "ネットワーク拡張",
        "priority": "中〜低",
        "summary":  "東京都内の中央卸売市場にサテライト冷蔵スペースを確保。都心ラストワンマイルの弱点解消。",
        "detail":   "大田市場か豊洲の共同冷蔵スペース（外部委託20〜30P）を借用。GS境→大田/豊洲→都内当日配送。KIFA川越を完全代替できる可能性。",
        "expected_cost_reduction": "KIFA川越廃止で▲¥180万/月（サテライト費用▲¥30〜50万）",
        "timeline": "6ヶ月",
        "kpi":      "都心エリア配送時間・サテライト稼働率",
    },
    {
        "name":     "⑥デジタル受発注プラットフォーム",
        "category": "DX・差別化",
        "priority": "低（中長期）",
        "summary":  "顧客がオンラインでリアルタイム在庫確認・発注できるシステム構築。サラダボウルにない透明性。",
        "detail":   "現在の在庫・収穫予定・配送スロットをリアルタイムで顧客公開。自動発注・定期便管理をセルフサービス化。受注コスト削減と顧客囲い込みを同時実現。",
        "expected_cost_reduction": "受注業務工数▲40%・顧客単価+10%（透明性プレミアム）",
        "timeline": "6〜12ヶ月",
        "kpi":      "デジタル受注率・自動発注率・顧客LTV",
    },
]


# ═══════════════════════════════════════════════════════════
# 2. 計算関数
# ═══════════════════════════════════════════════════════════

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の直線距離（km）を計算。"""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def calc_zone_hub_assignment() -> pd.DataFrame:
    """エリアごとの最適拠点割当・コスト・リードタイムを算出。"""
    rows = []
    for zone_name, zone in DELIVERY_ZONES.items():
        zc = zone["coords"]
        for hub_name, hub in HUBS.items():
            hc = hub["coords"]
            dist_km = _haversine_km(zc[0], zc[1], hc[0], hc[1])
            lead_h = hub["lead_time_h"] + dist_km / 60  # 60km/h 換算
            rows.append({
                "エリア":       zone_name,
                "拠点":         hub_name,
                "直線距離(km)": round(dist_km, 1),
                "推定リードタイム(h)": round(lead_h, 1),
                "拠点タイプ":   hub["type"],
                "月額コスト(円)": hub["monthly_cost_yen"],
                "1P単価(円)":   hub["cost_per_pallet"],
                "優先度":       zone["priority"],
                "主担当":       zone["primary"] == hub_name,
            })
    return pd.DataFrame(rows)


def calc_cost_comparison() -> pd.DataFrame:
    """3拠点のコスト比較表を生成。"""
    rows = []
    for hub_name, hub in HUBS.items():
        rows.append({
            "拠点":             hub_name,
            "タイプ":           hub["type"],
            "ステータス":       hub["status"],
            "容量(パレット)":   hub["capacity_pallets"],
            "月額固定費(円)":   hub["monthly_cost_yen"],
            "1P保管単価(円)":   hub["cost_per_pallet"],
            "年間コスト(円)":   hub["monthly_cost_yen"] * 12,
            "カバー圏(km)":     hub["coverage_km"],
            "標準リード(h)":    hub["lead_time_h"],
            "強み":             hub["strength"],
            "課題":             hub["weakness"],
        })
    return pd.DataFrame(rows)


def calc_scenario_comparison() -> pd.DataFrame:
    """
    シナリオ別 年間コスト・リスク比較。
    A: 現状維持（境町+川越）
    B: 3拠点体制（境町+川越+羽生ハイブリッド）
    C: 境町+羽生（川越廃止）
    """
    kifa_annual   = HUBS["KIFA川越（OEM連携）"]["monthly_cost_yen"] * 12
    gs_annual     = HUBS["GS境（自社冷蔵）"]["monthly_cost_yen"] * 12
    hanyu_annual  = HUBS["中越通運（羽生）"]["monthly_cost_yen"] * 12

    scenarios = [
        {
            "シナリオ":           "A：現状維持",
            "使用拠点":           "GS境＋KIFA川越",
            "年間拠点コスト(円)": gs_annual + kifa_annual,
            "カバーエリア":        "埼玉〜東京中心",
            "リスク":              "KIFA川越コスト依存・1拠点障害リスク高",
            "差別化力":            "★★☆",
            "推奨度":              "現状維持のみ",
        },
        {
            "シナリオ":           "B：3拠点ハイブリッド（推奨）",
            "使用拠点":           "GS境＋KIFA川越（繁忙期）＋中越通運羽生",
            "年間拠点コスト(円)": gs_annual + int(kifa_annual * 0.4) + hanyu_annual,
            "カバーエリア":        "関東全域",
            "リスク":              "低（3拠点でリスク分散）",
            "差別化力":            "★★★",
            "推奨度":              "◎ 最優先推奨",
        },
        {
            "シナリオ":           "C：川越廃止・境町＋羽生",
            "使用拠点":           "GS境＋中越通運羽生",
            "年間拠点コスト(円)": gs_annual + hanyu_annual,
            "カバーエリア":        "北関東〜埼玉〜一部東京",
            "リスク":              "都心カバー弱・顧客離れリスク",
            "差別化力":            "★★☆",
            "推奨度":              "コスト優先時の次善策",
        },
    ]
    df = pd.DataFrame(scenarios)
    df["現状比コスト削減(円)"] = df["年間拠点コスト(円)"].iloc[0] - df["年間拠点コスト(円)"]
    df["現状比削減率(%)"] = (df["現状比コスト削減(円)"] / df["年間拠点コスト(円)"].iloc[0] * 100).round(1)
    return df


def calc_kanto_coverage_table() -> pd.DataFrame:
    """エリア別 月間需要・担当拠点・売上見込を計算。"""
    rows = []
    for zone_name, zone in DELIVERY_ZONES.items():
        primary_hub = HUBS.get(zone["primary"], {})
        monthly_rev = zone["monthly_demand_pallets"] * zone["avg_revenue_per_pallet"]
        rows.append({
            "エリア":                 zone_name,
            "優先度":                 zone["priority"],
            "主担当拠点":             zone["primary"],
            "副担当拠点":             zone.get("secondary") or "なし",
            "月間需要(パレット)":     zone["monthly_demand_pallets"],
            "1P平均売上(円)":         zone["avg_revenue_per_pallet"],
            "月間売上見込(円)":       monthly_rev,
            "年間売上見込(円)":       monthly_rev * 12,
        })
    return pd.DataFrame(rows)


def calc_platform_kpi_sheet(
    actual_monthly_pallets: int = 0,
    actual_monthly_revenue: int = 0,
    kifa_cost_actual: int = 1_800_000,
    kifa_cost_target: int = 720_000,   # ▲60%目標
) -> pd.DataFrame:
    """
    プラットフォームKPI管理シート。
    実績値を入力すると目標対比・達成率を算出。
    """
    target_pallets = sum(z["monthly_demand_pallets"] for z in DELIVERY_ZONES.values())
    target_revenue = sum(z["monthly_demand_pallets"] * z["avg_revenue_per_pallet"] for z in DELIVERY_ZONES.values())
    target_coverage = len(DELIVERY_ZONES)
    actual_coverage = len([z for z in DELIVERY_ZONES.values() if z["priority"] in ["S", "A"]])

    kpis = [
        {
            "KPI項目":       "月間取り扱いパレット数",
            "カテゴリ":      "物量",
            "目標":          target_pallets,
            "実績":          actual_monthly_pallets or "---",
            "単位":          "P/月",
            "達成率(%)":     f"{actual_monthly_pallets/target_pallets*100:.1f}%" if actual_monthly_pallets else "---",
        },
        {
            "KPI項目":       "月間売上見込み",
            "カテゴリ":      "収益",
            "目標":          f"¥{target_revenue:,}",
            "実績":          f"¥{actual_monthly_revenue:,}" if actual_monthly_revenue else "---",
            "単位":          "円/月",
            "達成率(%)":     f"{actual_monthly_revenue/target_revenue*100:.1f}%" if actual_monthly_revenue else "---",
        },
        {
            "KPI項目":       "KIFA川越 拠点コスト",
            "カテゴリ":      "コスト削減",
            "目標":          f"¥{kifa_cost_target:,}（現状比▲60%）",
            "実績":          f"¥{kifa_cost_actual:,}",
            "単位":          "円/月",
            "達成率(%)":     f"{(kifa_cost_actual-kifa_cost_target)/(kifa_cost_actual)*100:.1f}%削減余地" if kifa_cost_actual else "---",
        },
        {
            "KPI項目":       "関東エリアカバー率",
            "カテゴリ":      "ネットワーク",
            "目標":          f"{target_coverage}エリア",
            "実績":          f"{actual_coverage}エリア（S/A優先）",
            "単位":          "エリア",
            "達成率(%)":     f"{actual_coverage/target_coverage*100:.0f}%",
        },
        {
            "KPI項目":       "平均リードタイム（配送先着荷まで）",
            "カテゴリ":      "サービス品質",
            "目標":          "24〜48h（リード2）",
            "実績":          "---",
            "単位":          "時間",
            "達成率(%)":     "---",
        },
        {
            "KPI項目":       "積載率（外注トラック）",
            "カテゴリ":      "効率",
            "目標":          "80%以上",
            "実績":          "---",
            "単位":          "%",
            "達成率(%)":     "---",
        },
        {
            "KPI項目":       "新規顧客獲得数（対サラダボウル切替）",
            "カテゴリ":      "営業",
            "目標":          "月3社以上",
            "実績":          "---",
            "単位":          "社/月",
            "達成率(%)":     "---",
        },
        {
            "KPI項目":       "OEM受注件数",
            "カテゴリ":      "差別化",
            "目標":          "月5件以上",
            "実績":          "---",
            "単位":          "件/月",
            "達成率(%)":     "---",
        },
    ]
    return pd.DataFrame(kpis)


# ═══════════════════════════════════════════════════════════
# 3. チャート生成
# ═══════════════════════════════════════════════════════════

def build_hub_strategy_map() -> folium.Map:
    """
    3拠点＋配送エリアのFoliumマップ。
    拠点の圏域を円で表示、エリアとの接続線付き。
    """
    center = (36.05, 139.65)
    m = folium.Map(
        location=center,
        zoom_start=9,
        tiles="CartoDB positron",
    )

    priority_color = {"S": "#d73027", "A": "#fc8d59", "B": "#4dac26", "C": "#91bfdb"}

    # ── 拠点圏域（円）
    for hub_name, hub in HUBS.items():
        lat, lon = hub["coords"]
        # 半透明の圏域円
        folium.Circle(
            location=[lat, lon],
            radius=hub["coverage_km"] * 1000,
            color=hub["color"],
            fill=True,
            fill_color=hub["color"],
            fill_opacity=0.06,
            weight=2,
            dash_array="6 4",
            tooltip=f"{hub_name}：カバー圏{hub['coverage_km']}km",
        ).add_to(m)

    # ── 拠点マーカー
    for hub_name, hub in HUBS.items():
        lat, lon = hub["coords"]
        popup_html = f"""
        <div style="font-family:sans-serif;min-width:220px">
          <h4 style="margin:0 0 6px">{hub['icon']} {hub_name}</h4>
          <table style="font-size:13px;border-collapse:collapse">
            <tr><td><b>タイプ</b></td><td>{hub['type']}</td></tr>
            <tr><td><b>ステータス</b></td><td>{hub['status']}</td></tr>
            <tr><td><b>容量</b></td><td>{hub['capacity_pallets']}パレット</td></tr>
            <tr><td><b>月額</b></td><td>¥{hub['monthly_cost_yen']:,}</td></tr>
            <tr><td><b>リード</b></td><td>{hub['lead_time_h']}h〜</td></tr>
            <tr style="color:#1565C0"><td><b>強み</b></td><td>{hub['strength']}</td></tr>
            <tr style="color:#d73027"><td><b>課題</b></td><td>{hub['weakness']}</td></tr>
          </table>
        </div>
        """
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{hub['icon']} {hub_name}",
            icon=folium.DivIcon(
                html=f"""<div style="
                    background:{hub['color']};color:white;
                    font-size:12px;font-weight:bold;
                    padding:6px 10px;border-radius:6px;
                    white-space:nowrap;box-shadow:0 2px 4px rgba(0,0,0,0.3)">
                    {hub['icon']} {hub_name.split('（')[0]}
                </div>""",
                icon_size=(160, 30),
                icon_anchor=(80, 15),
            ),
        ).add_to(m)

    # ── 配送エリアマーカー＋拠点への接続線
    for zone_name, zone in DELIVERY_ZONES.items():
        zlat, zlon = zone["coords"]
        pc = priority_color.get(zone["priority"], "#888")

        # エリアマーカー（円）
        folium.CircleMarker(
            location=[zlat, zlon],
            radius=10 + zone["monthly_demand_pallets"] // 5,
            color=pc,
            fill=True,
            fill_color=pc,
            fill_opacity=0.7,
            weight=2,
            popup=folium.Popup(
                f"<b>{zone_name}</b><br>優先度: {zone['priority']}<br>"
                f"主担当: {zone['primary']}<br>"
                f"月間需要: {zone['monthly_demand_pallets']}P<br>"
                f"月間売上見込: ¥{zone['monthly_demand_pallets']*zone['avg_revenue_per_pallet']:,}",
                max_width=240,
            ),
            tooltip=f"{zone_name}（{zone['priority']}）",
        ).add_to(m)

        # 主担当拠点への接続線
        primary = zone["primary"]
        if primary in HUBS:
            hlat, hlon = HUBS[primary]["coords"]
            folium.PolyLine(
                locations=[[zlat, zlon], [hlat, hlon]],
                color=HUBS[primary]["color"],
                weight=2,
                opacity=0.5,
                dash_array="6 3",
            ).add_to(m)

    # ── 凡例
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
         background:white;padding:12px 16px;border-radius:8px;
         box-shadow:0 2px 8px rgba(0,0,0,0.2);font-family:sans-serif;font-size:13px">
      <b>🗺️ 拠点・エリア凡例</b><br><br>
      <span style="color:#1565C0">●</span> GS境（自社冷蔵）<br>
      <span style="color:#d73027">●</span> KIFA川越（OEM/高コスト）<br>
      <span style="color:#4dac26">●</span> 中越通運羽生（検討中）<br><br>
      <b>エリア優先度：</b><br>
      <span style="color:#d73027">●</span> S（最優先）
      <span style="color:#fc8d59">●</span> A（高）
      <span style="color:#4dac26">●</span> B（中）
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def build_cost_comparison_chart() -> go.Figure:
    """3拠点コスト比較 棒グラフ。"""
    hub_names = list(HUBS.keys())
    monthly   = [h["monthly_cost_yen"] for h in HUBS.values()]
    annual    = [c * 12 for c in monthly]
    colors    = [h["color"] for h in HUBS.values()]
    status    = [h["status"] for h in HUBS.values()]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["月額コスト比較（円）", "年間コスト比較（円）"],
        horizontal_spacing=0.12,
    )

    fig.add_trace(go.Bar(
        name="月額コスト",
        x=hub_names,
        y=monthly,
        marker_color=colors,
        text=[f"¥{c:,}" for c in monthly],
        textposition="outside",
        textfont=dict(size=13),
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        name="年間コスト",
        x=hub_names,
        y=annual,
        marker_color=colors,
        opacity=0.85,
        text=[f"¥{a//10000:,}万" for a in annual],
        textposition="outside",
        textfont=dict(size=13),
    ), row=1, col=2)

    fig.update_layout(
        title=dict(text="🏭 拠点別 コスト比較（月額・年間）", x=0.5, xanchor="center", font=dict(size=15)),
        height=380,
        showlegend=False,
        margin=dict(t=80, b=60, l=60, r=40),
        plot_bgcolor="#fafafa",
    )
    fig.update_yaxes(tickformat=",.0f", row=1, col=1)
    fig.update_yaxes(tickformat=",.0f", row=1, col=2)
    return fig


def build_scenario_chart(df_scenario: pd.DataFrame) -> go.Figure:
    """シナリオ別年間コスト比較バー。"""
    colors = ["#d73027", "#1565C0", "#4dac26"]
    fig = go.Figure(go.Bar(
        x=df_scenario["シナリオ"],
        y=df_scenario["年間拠点コスト(円)"],
        marker_color=colors,
        text=df_scenario["年間拠点コスト(円)"].apply(lambda x: f"¥{x//10000:,}万"),
        textposition="outside",
        textfont=dict(size=14, color="black"),
    ))
    # 現状コストライン
    current_cost = df_scenario["年間拠点コスト(円)"].iloc[0]
    fig.add_hline(y=current_cost, line_dash="dot", line_color="#d73027",
                  annotation_text=f"現状コスト ¥{current_cost//10000:,}万")

    fig.update_layout(
        title=dict(text="📊 シナリオ別 年間拠点コスト比較", x=0.5, xanchor="center", font=dict(size=15)),
        yaxis=dict(title="年間コスト（円）", tickformat=",.0f"),
        height=360,
        margin=dict(t=70, b=40, l=80, r=40),
        plot_bgcolor="#fafafa",
        showlegend=False,
    )
    return fig


def build_kanto_demand_chart() -> go.Figure:
    """エリア別 月間需要・売上見込み 棒グラフ。"""
    zones       = list(DELIVERY_ZONES.keys())
    pallets     = [z["monthly_demand_pallets"] for z in DELIVERY_ZONES.values()]
    revenues    = [z["monthly_demand_pallets"] * z["avg_revenue_per_pallet"] for z in DELIVERY_ZONES.values()]
    primaries   = [z["primary"] for z in DELIVERY_ZONES.values()]
    hub_colors  = {h: HUBS[h]["color"] for h in HUBS}
    bar_colors  = [hub_colors.get(p, "#888") for p in primaries]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        name="月間需要（パレット）",
        x=zones, y=pallets,
        marker_color=bar_colors,
        opacity=0.85,
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        name="月間売上見込（円）",
        x=zones, y=revenues,
        mode="lines+markers",
        line=dict(color="#333", width=2),
        marker=dict(size=8),
    ), secondary_y=True)

    fig.update_layout(
        title=dict(text="🗺️ 関東エリア別 月間需要・売上見込み（色=担当拠点）", x=0.5, xanchor="center", font=dict(size=14)),
        height=360,
        margin=dict(t=70, b=60, l=60, r=80),
        legend=dict(orientation="h", y=-0.2),
        plot_bgcolor="#fafafa",
        xaxis=dict(tickangle=-25),
    )
    fig.update_yaxes(title_text="月間需要（パレット）", secondary_y=False)
    fig.update_yaxes(title_text="月間売上見込（円）", tickformat=",.0f", secondary_y=True)
    return fig


def build_vs_competitor_radar() -> go.Figure:
    """サラダボウル vs 舞台ファーム 差別化レーダーチャート。"""
    categories = [
        "リードタイム（速さ）", "小ロット対応", "OEM対応力", "鮮度・産地直送",
        "価格競争力", "エリアカバー", "デジタル対応", "顧客サポート"
    ]
    # 5点満点
    saladabowl = [3, 2, 2, 2, 5, 5, 3, 3]
    butai_now  = [4, 4, 5, 5, 3, 2, 2, 4]
    butai_goal = [5, 5, 5, 5, 3, 4, 4, 5]

    fig = go.Figure()
    cats = categories + [categories[0]]  # 閉じる

    fig.add_trace(go.Scatterpolar(
        r=saladabowl + [saladabowl[0]],
        theta=cats,
        fill="toself",
        name="サラダボウル（競合）",
        line=dict(color="#d73027", width=2),
        fillcolor="rgba(215,48,39,0.1)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=butai_now + [butai_now[0]],
        theta=cats,
        fill="toself",
        name="舞台ファーム（現状）",
        line=dict(color="#1565C0", width=2),
        fillcolor="rgba(21,101,192,0.1)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=butai_goal + [butai_goal[0]],
        theta=cats,
        fill="toself",
        name="舞台ファーム（戦略実行後目標）",
        line=dict(color="#4dac26", width=2, dash="dash"),
        fillcolor="rgba(77,172,38,0.08)",
    ))

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 5], dtick=1)),
        title=dict(text="🆚 競合比較レーダー：舞台ファーム vs サラダボウル", x=0.5, xanchor="center", font=dict(size=14)),
        legend=dict(orientation="h", y=-0.15),
        height=460,
        margin=dict(t=70, b=70, l=40, r=40),
    )
    return fig


def build_implementation_timeline() -> go.Figure:
    """戦略実行ロードマップ（ガントチャート風）。"""
    today = datetime.date.today()
    tasks = [
        ("②羽生センター検討・交渉開始",          0,  2, "#fc8d59"),
        ("①3拠点体制の設計・試験運用",            1,  3, "#1565C0"),
        ("②KIFA川越→羽生 段階移行",               2,  4, "#4dac26"),
        ("④混載プラットフォーム設計",             2,  4, "#9C27B0"),
        ("③産直ECサブスク便 PoC",                  3,  6, "#FF9800"),
        ("⑤大田市場サテライト拠点調査",            4,  6, "#607D8B"),
        ("関東全域カバー完成（S/A全エリア）",       5,  8, "#1565C0"),
        ("⑥デジタル受発注プラットフォーム構築",    6, 12, "#d73027"),
    ]

    fig = go.Figure()
    for i, (task, start_m, end_m, color) in enumerate(tasks):
        start_dt = today + datetime.timedelta(days=start_m * 30)
        end_dt   = today + datetime.timedelta(days=end_m * 30)
        fig.add_trace(go.Bar(
            name=task,
            x=[end_dt - start_dt],
            y=[task],
            base=[start_dt],
            orientation="h",
            marker_color=color,
            marker_opacity=0.8,
            text=f"{start_m}M〜{end_m}M",
            textposition="inside",
            textfont=dict(size=11, color="white"),
            showlegend=False,
        ))

    fig.add_vline(
        x=today,
        line_dash="solid",
        line_color="#333",
        annotation_text="TODAY",
        annotation_position="top",
    )

    fig.update_layout(
        title=dict(text="📅 戦略実行ロードマップ（今月〜12ヶ月）", x=0.5, xanchor="center", font=dict(size=14)),
        barmode="overlay",
        xaxis=dict(type="date", title="実行時期"),
        yaxis=dict(title=""),
        height=380,
        margin=dict(t=70, b=50, l=280, r=40),
        plot_bgcolor="#fafafa",
    )
    return fig
