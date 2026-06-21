"""
境町拠点（GS境）容量・収益シミュレーター

冷蔵庫3棟（計364パレット）をフル活用した場合の
月別・日別取り扱いパレット数と売上見込みを算出する。
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─────────────────────────────────
# 定数
# ─────────────────────────────────
TOTAL_CAPACITY = 364          # 総パレット数（第一120+第二120+第三124）
WORKING_DAYS_PER_MONTH = {    # 月別稼働日数（土日・祝日考慮）
    1: 20, 2: 19, 3: 22, 4: 21, 5: 20, 6: 21,
    7: 23, 8: 21, 9: 21, 10: 23, 11: 20, 12: 19,
}

# 季節別 平均占有率（実データから推定）
SEASONAL_OCCUPANCY = {
    1: 42, 2: 38, 3: 45,   # 冬・閑散期
    4: 55, 5: 62, 6: 68,   # 春・通常期
    7: 83, 8: 87, 9: 79,   # 夏・繁忙期
    10: 65, 11: 55, 12: 47  # 秋・通常→閑散
}

MONTH_JP = {
    1:"1月", 2:"2月", 3:"3月", 4:"4月", 5:"5月", 6:"6月",
    7:"7月", 8:"8月", 9:"9月", 10:"10月", 11:"11月", 12:"12月"
}

SEASON_LABEL = {
    1:"閑散期", 2:"閑散期", 3:"閑散期",
    4:"通常期", 5:"通常期", 6:"通常期",
    7:"繁忙期", 8:"繁忙期", 9:"繁忙期",
    10:"通常期", 11:"通常期", 12:"閑散期"
}

SEASON_COLOR = {"繁忙期": "#d73027", "通常期": "#fc8d59", "閑散期": "#4dac26"}


# ─────────────────────────────────
# コア計算
# ─────────────────────────────────

def calc_monthly_capacity(
    revenue_per_pallet: float = 55000,   # 1パレットあたり平均売上（円）
    turnover_per_month: float = 4.0,     # 月間パレット回転数
    custom_occupancy: dict | None = None, # ユーザーカスタム占有率
) -> pd.DataFrame:
    """
    月別の取り扱いパレット数・売上見込みを計算する。

    turnover_per_month: 1パレットが月に何回入出庫するか
    """
    occ = custom_occupancy or SEASONAL_OCCUPANCY
    rows = []
    for m in range(1, 13):
        occ_pct   = occ.get(m, 60)
        active    = round(TOTAL_CAPACITY * occ_pct / 100)   # 使用中パレット
        available = TOTAL_CAPACITY - active                   # 空きパレット
        w_days    = WORKING_DAYS_PER_MONTH[m]

        # 月間スループット = 使用パレット × 回転数
        monthly_throughput = round(active * turnover_per_month)
        # 日別スループット
        daily_throughput   = round(monthly_throughput / w_days)
        # 売上見込み
        monthly_revenue    = monthly_throughput * revenue_per_pallet

        rows.append({
            "月":           MONTH_JP[m],
            "月番号":       m,
            "シーズン":     SEASON_LABEL[m],
            "占有率(%)":    occ_pct,
            "使用パレット": active,
            "空きパレット": available,
            "稼働日数":     w_days,
            "月間取扱数":   monthly_throughput,
            "日別取扱数":   daily_throughput,
            "売上見込(円)": monthly_revenue,
        })
    return pd.DataFrame(rows)


def calc_daily_capacity(
    month: int,
    ref1_pct: float,
    ref2_pct: float,
    ref3_pct: float,
    revenue_per_pallet: float = 55000,
    turnover_per_month: float = 4.0,
) -> dict:
    """特定日の詳細容量を計算する。"""
    active = round(120*ref1_pct/100 + 120*ref2_pct/100 + 124*ref3_pct/100)
    available = TOTAL_CAPACITY - active
    w_days = WORKING_DAYS_PER_MONTH[month]
    daily_throughput = round(active * turnover_per_month / w_days)
    daily_revenue = daily_throughput * revenue_per_pallet
    return {
        "使用パレット": active,
        "空きパレット": available,
        "満杯まで": TOTAL_CAPACITY - active,
        "日別取扱数": daily_throughput,
        "日別売上見込": daily_revenue,
        "稼働率": round(active / TOTAL_CAPACITY * 100, 1),
    }


# ─────────────────────────────────
# チャート生成
# ─────────────────────────────────

def build_monthly_capacity_chart(df: pd.DataFrame) -> go.Figure:
    """月別 パレット数と占有率を2軸グラフで表示。"""
    season_colors = [SEASON_COLOR[s] for s in df["シーズン"]]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        subplot_titles=["月別 取り扱いパレット数（積み上げ）", "月別 占有率 (%)"],
    )

    # 上段：積み上げ棒グラフ（使用 + 空き）
    fig.add_trace(go.Bar(
        name="使用パレット",
        x=df["月"], y=df["使用パレット"],
        marker_color=season_colors,
        text=df["使用パレット"].astype(str) + "P",
        textposition="inside",
        textfont=dict(size=12, color="white"),
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        name="空きパレット",
        x=df["月"], y=df["空きパレット"],
        marker_color="#e0e0e0",
        text=df["空きパレット"].astype(str) + "P 空き",
        textposition="inside",
        textfont=dict(size=11, color="#666"),
    ), row=1, col=1)

    # 総容量ライン
    fig.add_hline(y=TOTAL_CAPACITY, line_dash="dot", line_color="#333",
                  annotation_text=f"総容量 {TOTAL_CAPACITY}P", row=1, col=1)

    # 下段：占有率折れ線
    fig.add_trace(go.Scatter(
        name="占有率",
        x=df["月"], y=df["占有率(%)"],
        mode="lines+markers+text",
        line=dict(color="#1565C0", width=3),
        marker=dict(size=10, color=season_colors, line=dict(width=2, color="white")),
        text=df["占有率(%)"].astype(str) + "%",
        textposition="top center",
        textfont=dict(size=12),
    ), row=2, col=1)

    # 閾値ライン
    fig.add_hline(y=70, line_dash="dash", line_color="#d73027",
                  annotation_text="繁忙期ライン(70%)", row=2, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="#4dac26",
                  annotation_text="閑散期ライン(50%)", row=2, col=1)

    fig.update_layout(
        barmode="stack",
        height=520,
        margin=dict(t=60, b=40, l=60, r=40),
        legend=dict(orientation="h", y=-0.05),
        plot_bgcolor="#fafafa",
    )
    fig.update_yaxes(title_text="パレット数", row=1, col=1)
    fig.update_yaxes(title_text="占有率(%)", range=[0, 105], row=2, col=1)

    return fig


def build_revenue_chart(df: pd.DataFrame) -> go.Figure:
    """月別 売上見込み棒グラフ。"""
    season_colors = [SEASON_COLOR[s] for s in df["シーズン"]]
    annual_total = df["売上見込(円)"].sum()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["月"],
        y=df["売上見込(円)"],
        marker_color=season_colors,
        text=df["売上見込(円)"].apply(lambda x: f"¥{x/1e6:.1f}M"),
        textposition="outside",
        textfont=dict(size=13),
    ))

    fig.update_layout(
        title=dict(
            text=f"月別 売上見込み　（年間合計：<b>¥{annual_total/1e6:.1f}M</b>）",
            x=0.5, xanchor="center", font=dict(size=15),
        ),
        yaxis=dict(title="売上見込（円）", tickformat=",.0f"),
        height=360,
        margin=dict(t=70, b=40, l=80, r=40),
        plot_bgcolor="#fafafa",
        showlegend=False,
    )
    return fig


def build_throughput_chart(df: pd.DataFrame) -> go.Figure:
    """月間取扱数と日別取扱数の2軸グラフ。"""
    season_colors = [SEASON_COLOR[s] for s in df["シーズン"]]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        name="月間取扱数（パレット）",
        x=df["月"], y=df["月間取扱数"],
        marker_color=season_colors,
        opacity=0.8,
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        name="日別取扱数（パレット/日）",
        x=df["月"], y=df["日別取扱数"],
        mode="lines+markers",
        line=dict(color="#1565C0", width=3),
        marker=dict(size=9),
    ), secondary_y=True)

    fig.update_layout(
        title=dict(text="月間・日別 取り扱いパレット数", x=0.5, xanchor="center", font=dict(size=15)),
        height=340,
        margin=dict(t=60, b=40, l=60, r=60),
        legend=dict(orientation="h", y=-0.1),
        plot_bgcolor="#fafafa",
    )
    fig.update_yaxes(title_text="月間取扱数（パレット）", secondary_y=False)
    fig.update_yaxes(title_text="日別取扱数（パレット/日）", secondary_y=True)

    return fig


def build_season_comparison_table(df: pd.DataFrame) -> pd.DataFrame:
    """シーズン別の集計サマリーテーブルを返す。"""
    summary = df.groupby("シーズン").agg(
        対象月数=("月", "count"),
        平均占有率=("占有率(%)", "mean"),
        平均使用パレット=("使用パレット", "mean"),
        月平均取扱数=("月間取扱数", "mean"),
        月平均売上見込=("売上見込(円)", "mean"),
        合計売上見込=("売上見込(円)", "sum"),
    ).round(0).reset_index()

    summary["平均占有率"] = summary["平均占有率"].round(1).astype(str) + "%"
    summary["平均使用パレット"] = summary["平均使用パレット"].astype(int).astype(str) + "P"
    summary["月平均取扱数"] = summary["月平均取扱数"].astype(int).astype(str) + "P/月"
    summary["月平均売上見込"] = summary["月平均売上見込"].apply(lambda x: f"¥{int(x):,}")
    summary["合計売上見込"] = summary["合計売上見込"].apply(lambda x: f"¥{int(x):,}")

    return summary
