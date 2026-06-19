"""Folium ベースのインタラクティブマップ生成（ルート / ヒートマップ / 収益）。"""
import folium
from folium.plugins import HeatMap
import pandas as pd
import numpy as np


def _load_rate_color(rate: float) -> str:
    if pd.isna(rate): return "#888888"
    if rate < 40:  return "#d73027"
    if rate < 60:  return "#fc8d59"
    if rate < 80:  return "#fee090"
    return "#4dac26"


def _load_rate_weight(rate: float) -> int:
    if pd.isna(rate): return 3
    return max(2, min(8, int(rate / 12)))


def _center(facility_lookup: dict) -> tuple[float, float]:
    coords = list(facility_lookup.values())
    if not coords:
        return 36.2, 139.5
    return float(np.mean([c[0] for c in coords])), float(np.mean([c[1] for c in coords]))


def _add_legend(m: folium.Map, html: str):
    m.get_root().html.add_child(folium.Element(html))


_ROUTE_LEGEND = """
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
    padding:10px;border-radius:8px;border:1px solid #ccc;font-size:12px;">
  <b>積載率</b><br>
  <span style="color:#d73027">■</span> ～40%（要改善）<br>
  <span style="color:#fc8d59">■</span> 40～60%（注意）<br>
  <span style="color:#fee090">■</span> 60～80%（普通）<br>
  <span style="color:#4dac26">■</span> 80%以上（良好）
</div>"""


def build_route_map(df: pd.DataFrame, facility_lookup: dict) -> tuple[folium.Map, list]:
    clat, clng = _center(facility_lookup)
    m = folium.Map(location=[clat, clng], zoom_start=9, tiles="CartoDB positron")
    _add_legend(m, _ROUTE_LEGEND)
    missing = []

    for _, row in df.iterrows():
        dep = str(row.get("出発地", "")).strip()
        arr = str(row.get("到着地", "")).strip()
        rate = row.get("積載率")
        rev = row.get("売上", "—")
        bn  = row.get("便No", "—")

        dc = facility_lookup.get(dep)
        ac = facility_lookup.get(arr)
        if not dc or not ac:
            missing += [x for x in [dep, arr] if x and not facility_lookup.get(x)]
            continue

        color  = _load_rate_color(rate)
        weight = _load_rate_weight(rate)
        rate_s = f"{rate:.1f}%" if not pd.isna(rate) else "不明"
        rev_s  = f"¥{int(rev):,}" if not pd.isna(rev) else "—"

        folium.PolyLine(
            [dc, ac], color=color, weight=weight, opacity=0.85,
            tooltip=f"{dep}→{arr}  積載率:{rate_s}",
            popup=folium.Popup(
                f"<b>便No：{bn}</b><br>{dep}→{arr}<br>積載率：<b style='color:{color}'>{rate_s}</b><br>売上：{rev_s}",
                max_width=220),
        ).add_to(m)

    for name, coord in facility_lookup.items():
        folium.CircleMarker(coord, radius=6, color="#333", fill=True,
                            fill_color="#fff", fill_opacity=0.9,
                            tooltip=name, popup=name).add_to(m)
    return m, list(set(missing))


def build_heatmap(df: pd.DataFrame, facility_lookup: dict) -> folium.Map:
    clat, clng = _center(facility_lookup)
    m = folium.Map(location=[clat, clng], zoom_start=9, tiles="CartoDB positron")

    area_avg = df.dropna(subset=["到着地", "積載率"]).groupby("到着地")["積載率"].mean()
    heat = []
    for name, avg in area_avg.items():
        c = facility_lookup.get(str(name).strip())
        if c:
            heat.append([c[0], c[1], max(0, 100 - avg) / 100])
    if heat:
        HeatMap(heat, radius=35, blur=20,
                gradient={0.2: "#4dac26", 0.5: "#fee090", 0.8: "#fc8d59", 1.0: "#d73027"},
                min_opacity=0.4).add_to(m)
    for name, coord in facility_lookup.items():
        avg = area_avg.get(name)
        label = f"{name}" + (f"\n平均積載率: {avg:.1f}%" if avg else "")
        folium.Marker(coord, icon=folium.DivIcon(
            html=f'<div style="font-size:10px;background:rgba(255,255,255,.7);padding:2px 4px;border-radius:3px;">{name}</div>',
            icon_size=(100, 20)), tooltip=label).add_to(m)
    _add_legend(m, """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
        padding:10px;border-radius:8px;border:1px solid #ccc;font-size:12px;">
      <b>平均積載率（低いほど赤）</b><br>
      <span style="color:#d73027">■</span> 低積載エリア<br>
      <span style="color:#4dac26">■</span> 高積載エリア
    </div>""")
    return m


def build_revenue_map(df: pd.DataFrame, facility_lookup: dict) -> folium.Map:
    clat, clng = _center(facility_lookup)
    m = folium.Map(location=[clat, clng], zoom_start=9, tiles="CartoDB positron")

    area_rev = df.dropna(subset=["到着地", "売上"]).groupby("到着地")["売上"].sum()
    if area_rev.empty:
        return m

    max_rev = area_rev.max()
    for name, rev in area_rev.items():
        c = facility_lookup.get(str(name).strip())
        if not c:
            continue
        r = max(8, min(40, int(40 * (rev / max_rev) ** 0.5)))
        folium.CircleMarker(c, radius=r, color="#1a1a2e", weight=1.5,
                            fill=True, fill_color="#3a86ff", fill_opacity=0.65,
                            tooltip=f"{name}  ¥{int(rev):,}",
                            popup=folium.Popup(f"<b>{name}</b><br>合計売上：¥{int(rev):,}", max_width=200)
                            ).add_to(m)
    return m


def build_sakai_route_map(facility_lookup: dict) -> folium.Map:
    """GS境拠点を中心とした配送ルートマップ（固定ルート表示）。"""
    sakai = facility_lookup.get("GS境", (36.2215, 139.8340))
    m = folium.Map(location=sakai, zoom_start=8, tiles="CartoDB positron")

    # 境町拠点マーカー
    folium.Marker(
        sakai,
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        tooltip="GS境拠点（境町）",
        popup="<b>GS境拠点</b><br>第一・第二・第三冷蔵庫<br>総容量 364パレット",
    ).add_to(m)

    # 主要ルート
    routes = [
        ("GS境", "アスカット",     "#d73027", 4, "埼玉北ルート（毎日）"),
        ("GS境", "ヤオコー",       "#d73027", 3, "ヤオコー便（週3回）"),
        ("GS境", "カネミ食品",     "#fc8d59", 3, "カネミ食品（週4回）"),
        ("GS境", "ヨシケイ栃木",   "#4dac26", 4, "栃木ルート（週3回）"),
        ("GS境", "DIC信濃川上",    "#2196F3", 5, "長野便（週5回・固定）"),
        ("GS境", "東京シティ",     "#9c27b0", 3, "東京ルート（週2回）"),
        ("GS境", "境町給食",       "#795548", 4, "境町給食（毎日・斎藤担当）"),
    ]

    for dep, arr, color, weight, label in routes:
        dc = facility_lookup.get(dep)
        ac = facility_lookup.get(arr)
        if dc and ac:
            folium.PolyLine([dc, ac], color=color, weight=weight, opacity=0.8,
                            tooltip=label, dash_array="5 5" if "週" in label else None).add_to(m)
            folium.CircleMarker(ac, radius=7, color=color, fill=True,
                                fill_color=color, fill_opacity=0.7,
                                tooltip=arr, popup=label).add_to(m)

    _add_legend(m, """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
        padding:10px;border-radius:8px;border:1px solid #ccc;font-size:12px;">
      <b>GS境 主要配送ルート</b><br>
      <span style="color:#d73027">━━</span> 埼玉北（毎日）<br>
      <span style="color:#4dac26">━━</span> 栃木ルート<br>
      <span style="color:#2196F3">━━</span> 長野（固定）<br>
      <span style="color:#9c27b0">━━</span> 東京ルート<br>
      <span style="color:#795548">━━</span> 境町給食
    </div>""")
    return m
