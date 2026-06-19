"""
GS境 冷蔵庫占有率 可視化モジュール。
Plotly Gauge + Bar + Heatmap で冷蔵庫状態を直感的に表示する。
"""
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np


# ───────────────────────────────────────────
# 色定義
# ───────────────────────────────────────────
def _occ_color(pct: float) -> str:
    if pct < 30:  return "#4dac26"   # 緑（余裕）
    if pct < 50:  return "#a1d99b"   # 薄緑
    if pct < 70:  return "#fee090"   # 黄
    if pct < 90:  return "#fc8d59"   # オレンジ
    return "#d73027"                  # 赤（危険）

def _occ_label(pct: float) -> str:
    if pct < 30:  return "余裕"
    if pct < 50:  return "低"
    if pct < 70:  return "普通"
    if pct < 90:  return "高"
    return "満杯近し"


# ───────────────────────────────────────────
# ゲージ3連（メイン表示）
# ───────────────────────────────────────────
def build_gauge_chart(
    ref1_pct: float, ref2_pct: float, ref3_pct: float,
) -> go.Figure:
    """3冷蔵庫の占有率をゲージで横並び表示。"""
    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
        subplot_titles=["第一冷蔵庫（120P）", "第二冷蔵庫（120P）", "第三冷蔵庫（124P・バッファ）"],
    )

    for col, (name, pct) in enumerate([
        ("第一", ref1_pct),
        ("第二", ref2_pct),
        ("第三", ref3_pct),
    ], start=1):
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=pct,
                number={"suffix": "%", "font": {"size": 32}},
                delta={"reference": 70, "valueformat": ".1f",
                       "increasing": {"color": "#d73027"},
                       "decreasing": {"color": "#4dac26"}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": _occ_color(pct), "thickness": 0.7},
                    "bgcolor": "#f5f5f5",
                    "borderwidth": 1,
                    "threshold": {
                        "line": {"color": "#333", "width": 3},
                        "thickness": 0.75,
                        "value": 90,
                    },
                    "steps": [
                        {"range": [0, 50],  "color": "#e8f5e9"},
                        {"range": [50, 70], "color": "#fff9c4"},
                        {"range": [70, 90], "color": "#ffe0b2"},
                        {"range": [90, 100],"color": "#ffcdd2"},
                    ],
                },
                title={"text": f"<b>{name}</b><br><span style='font-size:12px'>{_occ_label(pct)}</span>"},
            ),
            row=1, col=col,
        )

    total_used = (ref1_pct/100 * 120 + ref2_pct/100 * 120 + ref3_pct/100 * 124)
    total_pct = total_used / 364 * 100

    fig.update_layout(
        height=280,
        margin=dict(t=60, b=10, l=20, r=20),
        paper_bgcolor="#ffffff",
        title={
            "text": f"<b>冷蔵庫総合占有率：{total_pct:.1f}%</b>　（使用 {total_used:.0f}P / 364P）",
            "x": 0.5, "xanchor": "center", "font": {"size": 16},
        },
    )
    return fig


# ───────────────────────────────────────────
# パレット在庫バー（商品別）
# ───────────────────────────────────────────
def build_product_bar(
    ref1_pct: float, ref2_pct: float, ref3_pct: float,
    product_mix: dict | None = None,
) -> go.Figure:
    """
    各冷蔵庫のパレット使用状況を商品カテゴリ別に表示する棒グラフ。
    product_mix = {"第一冷蔵庫": {"GS境玉レタス": 40, ...}, ...}
    """
    # デフォルトの商品配分（実データがない場合）
    default_mix = {
        "第一冷蔵庫": {
            "GS境玉レタス": 0.35, "GS境サニー": 0.20, "GS境Gリーフ": 0.20,
            "本社原料キャベツ": 0.15, "GS経由商品保管": 0.10,
        },
        "第二冷蔵庫": {
            "GS境玉レタス": 0.30, "GSキャベツ": 0.25, "GS境サニー": 0.20,
            "GS境Gリーフ": 0.15, "GS経由商品保管": 0.10,
        },
        "第三冷蔵庫": {
            "本社原料キャベツ": 0.40, "GS境玉レタス": 0.30,
            "お米": 0.15, "GS経由商品保管": 0.15,
        },
    }
    if product_mix is None:
        product_mix = default_mix

    caps = {"第一冷蔵庫": 120, "第二冷蔵庫": 120, "第三冷蔵庫": 124}
    occ  = {"第一冷蔵庫": ref1_pct/100, "第二冷蔵庫": ref2_pct/100, "第三冷蔵庫": ref3_pct/100}

    products = ["GS境玉レタス", "GS境サニー", "GS境Gリーフ", "GSキャベツ",
                "本社原料キャベツ", "GS経由商品保管", "お米"]
    colors   = ["#2196F3", "#4CAF50", "#8BC34A", "#FF5722",
                "#9C27B0", "#FF9800", "#795548"]

    figs = []
    for prod, color in zip(products, colors):
        x_vals = []
        for ref in ["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"]:
            used = caps[ref] * occ[ref]
            ratio = product_mix.get(ref, {}).get(prod, 0)
            x_vals.append(used * ratio)
        figs.append(go.Bar(
            name=prod, x=["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"],
            y=x_vals, marker_color=color,
        ))

    # 空き容量
    empty_vals = []
    for ref, pct_val in [("第一冷蔵庫", ref1_pct), ("第二冷蔵庫", ref2_pct), ("第三冷蔵庫", ref3_pct)]:
        empty_vals.append(caps[ref] * (1 - pct_val/100))
    figs.append(go.Bar(
        name="空き", x=["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"],
        y=empty_vals, marker_color="#e0e0e0", marker_line_color="#bdbdbd",
        marker_line_width=1, opacity=0.7,
    ))

    fig = go.Figure(data=figs)
    fig.update_layout(
        barmode="stack",
        title={"text": "冷蔵庫別 パレット在庫構成", "x": 0.5, "xanchor": "center"},
        yaxis_title="パレット数",
        height=320,
        legend={"orientation": "h", "y": -0.2},
        margin=dict(t=50, b=60, l=50, r=20),
    )
    # 容量ライン
    for cap, x_pos in zip([120, 120, 124], [0, 1, 2]):
        fig.add_hline(y=cap, line_dash="dot", line_color="#e53935",
                      annotation_text="最大容量", annotation_position="top right")
    return fig


# ───────────────────────────────────────────
# 月次推移ヒートマップ
# ───────────────────────────────────────────
def build_monthly_heatmap(monthly_data: pd.DataFrame | None = None) -> go.Figure:
    """
    月別 × 冷蔵庫別 の占有率ヒートマップ。
    monthly_data columns: ['月', '第一冷蔵庫', '第二冷蔵庫', '第三冷蔵庫']
    """
    if monthly_data is None or monthly_data.empty:
        # サンプルデータ（実データ接続までのデフォルト）
        months = [f"{m}月" for m in range(1, 13)]
        # 実データから推測した占有率パターン（夏=繁忙、冬=閑散）
        np.random.seed(0)
        base = [45, 40, 45, 55, 65, 70, 85, 88, 80, 65, 55, 45]
        monthly_data = pd.DataFrame({
            "月": months,
            "第一冷蔵庫": np.clip([b + np.random.randint(-5, 10) for b in base], 20, 100),
            "第二冷蔵庫": np.clip([b + np.random.randint(-8, 15) for b in base], 20, 100),
            "第三冷蔵庫": np.clip([b - 15 + np.random.randint(-5, 10) for b in base], 5, 95),
        })

    z = monthly_data[["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"]].values.T.tolist()
    text = [[f"{v:.0f}%" for v in row] for row in z]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=monthly_data["月"].tolist(),
        y=["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"],
        text=text,
        texttemplate="%{text}",
        textfont={"size": 11},
        colorscale=[
            [0.0,  "#4dac26"],
            [0.3,  "#a1d99b"],
            [0.5,  "#fee090"],
            [0.7,  "#fc8d59"],
            [0.9,  "#d73027"],
            [1.0,  "#a50026"],
        ],
        zmin=0, zmax=100,
        colorbar=dict(title="占有率(%)", ticksuffix="%"),
    ))

    fig.update_layout(
        title={"text": "月別 冷蔵庫占有率（繁忙期・閑散期の把握）", "x": 0.5, "xanchor": "center"},
        height=220,
        margin=dict(t=50, b=30, l=120, r=60),
        xaxis={"side": "bottom"},
    )
    # 繁忙期マーカー
    for i, month in enumerate(monthly_data["月"]):
        avg = np.mean([monthly_data.iloc[i][col] for col in ["第一冷蔵庫", "第二冷蔵庫", "第三冷蔵庫"]])
        if avg >= 70:
            fig.add_vline(x=month, line_dash="dot", line_color="#c62828", line_width=1.5)

    return fig


# ───────────────────────────────────────────
# トラック台数推奨チャート
# ───────────────────────────────────────────
def build_truck_recommendation_chart(plans: list) -> go.Figure:
    """週間スケジュールプランからトラック台数推奨を棒グラフ表示。"""
    days = ["月", "火", "水", "木", "金"]
    trucks_list = [p.trucks_needed for p in plans]
    seasons = [p.season for p in plans]
    colors_map = {"繁忙期": "#d73027", "通常期": "#fc8d59", "閑散期": "#4dac26"}
    bar_colors = [colors_map.get(s, "#888") for s in seasons]

    fig = go.Figure(go.Bar(
        x=days[:len(trucks_list)],
        y=trucks_list,
        marker_color=bar_colors,
        text=[f"{t}台<br>{s}" for t, s in zip(trucks_list, seasons)],
        textposition="outside",
    ))
    fig.update_layout(
        title={"text": "推奨 外注トラック台数（週間）", "x": 0.5, "xanchor": "center"},
        yaxis=dict(title="台数", range=[0, 5], dtick=1),
        height=260,
        margin=dict(t=50, b=30),
        showlegend=False,
    )
    return fig
