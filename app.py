"""
配送運行「見える化」ダッシュボード
舞台ファーム 境町拠点（GS境）対応版
Streamlit + Folium + Plotly（完全無料・コスト¥0）
"""
import datetime
import streamlit as st
import pandas as pd
import numpy as np
from streamlit_folium import st_folium
import plotly.graph_objects as go

import map_view
import optimization
import refrigerator_ui
import sakai_scheduler
from geocode import build_facility_lookup

# ──────────────────────────────────────────────
# ページ設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="配送運行ダッシュボード｜舞台ファーム境町拠点",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("""
<style>
  [data-testid="stSidebar"] { min-width: 280px; }
  .stTabs [data-baseweb="tab"] { font-size: 14px; padding: 8px 16px; }
  .alert-high { background:#ffebee; border-left:4px solid #d73027; padding:8px 12px; border-radius:4px; margin:4px 0; }
  .alert-mid  { background:#fff8e1; border-left:4px solid #f9a825; padding:8px 12px; border-radius:4px; margin:4px 0; }
  .alert-low  { background:#e8f5e9; border-left:4px solid #4dac26; padding:8px 12px; border-radius:4px; margin:4px 0; }
</style>
""", unsafe_allow_html=True)

SAKAI_SHEET_URL = "https://docs.google.com/spreadsheets/d/1TS-XQsP3k_GZFslv2tkAQ4kl1iVTAjIJ4OjCJcudsFI/edit?gid=1870078201#gid=1870078201"

# ──────────────────────────────────────────────
# サンプルデータ
# ──────────────────────────────────────────────
def make_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    np.random.seed(42)
    routes = [
        ("GS境", "アスカット"), ("GS境", "ヤオコー"), ("GS境", "カネミ食品"),
        ("GS境", "ヨシケイ栃木"), ("GS境", "DIC信濃川上"), ("GS境", "東京シティ"),
        ("GS境", "境町給食"), ("GS境", "マルエツ"), ("GS境", "ロピア"),
        ("GS境", "ピックルス"),
    ]
    categories = ["GS境玉レタス", "GS境サニー", "GS境Gリーフ", "GSキャベツ", "本社原料キャベツ"]
    trucks = ["明信運輸①", "明信運輸②", "明信運輸③", "斎藤良", "大久保誠", "伊藤将真"]
    records = []
    for i in range(80):
        dep, arr = routes[i % len(routes)]
        records.append({
            "便No": f"便{i+1:03d}",
            "日付": pd.Timestamp("2026-05-01") + pd.Timedelta(days=i // 4),
            "出発地": dep, "到着地": arr,
            "積載率": round(max(15, min(100, np.random.normal(63, 22))), 1),
            "売上": int(max(5000, np.random.normal(45000, 15000))),
            "商品カテゴリ": categories[i % len(categories)],
            "担当": trucks[i % len(trucks)],
        })
    df_ops = pd.DataFrame(records)

    from geocode import KNOWN_COORDS
    df_master = pd.DataFrame([
        {"拠点名": k, "住所": "", "緯度": v[0], "経度": v[1]}
        for k, v in KNOWN_COORDS.items()
    ])
    return df_ops, df_master


# ──────────────────────────────────────────────
# サイドバー
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("🚛 舞台ファーム\n配送ダッシュボード")
    st.caption("境町拠点（GS境）最適化対応版")
    st.markdown("---")

    st.subheader("📊 データソース")
    sheet_url = st.text_input(
        "Google スプレッドシート URL",
        value=st.session_state.get("sheet_url", SAKAI_SHEET_URL),
        help="シートの URL を入力してください。",
    )
    if sheet_url != st.session_state.get("sheet_url", ""):
        st.session_state["sheet_url"] = sheet_url
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    df_ops, df_master = make_sample_data()
    facility_lookup = build_facility_lookup(df_master)

    st.subheader("🔍 フィルター")
    if "日付" in df_ops.columns and df_ops["日付"].notna().any():
        dates = df_ops["日付"].dropna()
        d0, d1 = dates.min().date(), dates.max().date()
        dr = st.date_input("日付範囲", value=(d0, d1), min_value=d0, max_value=d1)
        if len(dr) == 2:
            df_ops = df_ops[(df_ops["日付"].dt.date >= dr[0]) & (df_ops["日付"].dt.date <= dr[1])]

    if "到着地" in df_ops.columns:
        areas = sorted(df_ops["到着地"].dropna().unique())
        sel = st.multiselect("エリア（到着地）", areas, default=list(areas))
        if sel:
            df_ops = df_ops[df_ops["到着地"].isin(sel)]

    if "積載率" in df_ops.columns:
        rr = st.slider("積載率フィルター（%）", 0, 100, (0, 100), 5)
        df_ops = df_ops[(df_ops["積載率"] >= rr[0]) & (df_ops["積載率"] <= rr[1])]

    st.markdown("---")
    kpis = optimization.get_summary_kpis(df_ops)
    st.subheader("📈 KPI")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("総便数", f"{kpis['総便数']}便")
        if kpis["平均積載率"]:
            st.metric("平均積載率", f"{kpis['平均積載率']:.1f}%")
    with c2:
        if kpis["低積載便数"] is not None:
            st.metric("低積載（<60%）", f"{kpis['低積載便数']}件")
        if kpis["総売上"]:
            st.metric("総売上", f"¥{int(kpis['総売上']):,}")
    if st.button("🔄 データ更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ──────────────────────────────────────────────
# メインエリア
# ──────────────────────────────────────────────
st.header("🚛 配送運行「見える化」ダッシュボード　｜　舞台ファーム 境町拠点")

tab_sakai, tab_route, tab_heat, tab_rev, tab_opt = st.tabs([
    "🏭 境町拠点 スケジュール最適化",
    "🗺️ ルートマップ",
    "🌡️ 積載率ヒートマップ",
    "💰 エリア別収益マップ",
    "⚡ 最適化提案",
])


# ══════════════════════════════════════════════
# Tab 1: 境町拠点 スケジュール最適化
# ══════════════════════════════════════════════
with tab_sakai:
    st.subheader("🏭 GS境拠点 配送スケジュール最適化")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 📦 冷蔵庫占有率（現在の状況を入力）")
        st.caption("データを入力すると自動でシーズン判定・スケジュール提案が変わります。")

        ref1 = st.slider("第一冷蔵庫 占有率 (%)", 0, 100, 65, 5, key="ref1")
        ref2 = st.slider("第二冷蔵庫 占有率 (%)", 0, 100, 78, 5, key="ref2")
        ref3 = st.slider("第三冷蔵庫 占有率 (%)", 0, 100, 42, 5, key="ref3")

        today = datetime.date.today()
        weekday = today.weekday()
        month = today.month

        special = st.multiselect(
            "特殊イベント（該当あれば）",
            ["棚卸", "訓練日", "事業方針会議", "説明会", "新店追加"],
        )

    # スケジュール生成
    plan = sakai_scheduler.optimize_schedule(ref1, ref2, ref3, weekday=weekday, month=month, special_events=special)

    with col_right:
        st.markdown("#### 🌡️ 冷蔵庫ゲージ")
        gauge_fig = refrigerator_ui.build_gauge_chart(ref1, ref2, ref3)
        st.plotly_chart(gauge_fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")

    # シーズンバナー
    season_colors = {"繁忙期": "#ffcdd2", "通常期": "#fff9c4", "閑散期": "#e8f5e9"}
    season_icons  = {"繁忙期": "🔴", "通常期": "🟡", "閑散期": "🟢"}
    st.markdown(
        f'<div style="background:{season_colors[plan.season]};padding:12px 20px;border-radius:8px;'
        f'font-size:20px;font-weight:bold;text-align:center;">'
        f'{season_icons[plan.season]} 現在のシーズン判定：<span style="font-size:24px">{plan.season}</span>'
        f'　（平均占有率 {plan.avg_occupancy:.1f}%）</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # アラート
    if plan.alerts:
        for alert in plan.alerts:
            alert_class = "alert-high" if "🔴" in alert else "alert-mid" if "🟡" in alert else "alert-low"
            st.markdown(f'<div class="{alert_class}">{alert}</div>', unsafe_allow_html=True)
        st.markdown("")

    # 3カラム：推奨台数 / 出発時刻 / 削減効果
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("🚚 推奨 外注トラック台数", f"{plan.trucks_needed}台", help="明信運輸の必要台数")
    with c2:
        st.metric("⏰ 推奨 積込開始時刻", plan.loading_start, help="宮下リードの積込開始目安")
    with c3:
        st.metric("💡 シーズン戦略", plan.season)

    st.markdown(f"**削減・改善効果：** {plan.estimated_savings}")
    st.markdown("---")

    # スタッフ配置表
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("#### 👷 推奨スタッフ・外注配置")
        sched_df = sakai_scheduler.build_schedule_dataframe(plan)
        st.dataframe(sched_df, use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("#### 🗺️ 優先ルート")
        for route in plan.priority_routes:
            st.markdown(f"✅ **{route}**（必須・削減不可）")
        st.markdown("")
        st.markdown("#### 🔗 統合推奨ルート")
        for cr in plan.combined_routes:
            stops_str = " → ".join(cr["stops"])
            st.markdown(f"📦 **{cr['route_name']}**：{stops_str}")

    # 季節戦略
    st.markdown("---")
    st.markdown("#### 📅 繁忙期・閑散期 戦略サマリー")
    strategy_tabs = st.tabs(["🔴 繁忙期", "🟡 通常期", "🟢 閑散期"])
    for i, (stype, stab) in enumerate(zip(["繁忙期", "通常期", "閑散期"], strategy_tabs)):
        strat = sakai_scheduler.get_seasonal_strategy(stype)
        with stab:
            s1, s2 = st.columns(2)
            with s1:
                st.metric("外注台数", strat["外注台数"])
                st.metric("積込開始", strat["積込開始"])
            with s2:
                st.info(f"**重点施策：**\n{strat['重点施策']}")
            c_k, c_n = st.columns(2)
            with c_k:
                st.success(f"**KPI目標：** {strat['KPI目標']}")
            with c_n:
                st.warning(f"**注意事項：** {strat['注意事項']}")

    # 冷蔵庫詳細グラフ
    st.markdown("---")
    st.markdown("#### 📊 冷蔵庫パレット構成 ＆ 月別占有率")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        bar_fig = refrigerator_ui.build_product_bar(ref1, ref2, ref3)
        st.plotly_chart(bar_fig, use_container_width=True, config={"displayModeBar": False})
    with col_g2:
        heat_fig = refrigerator_ui.build_monthly_heatmap()
        st.plotly_chart(heat_fig, use_container_width=True, config={"displayModeBar": False})

    # GS境拠点地図
    st.markdown("---")
    st.markdown("#### 🗺️ GS境拠点 主要配送ルートマップ")
    st.caption("破線 = 週2〜3回、実線 = 毎日便")
    sakai_map = map_view.build_sakai_route_map(facility_lookup)
    st_folium(sakai_map, width="100%", height=460, returned_objects=[])

    # Google Sheets データ表示
    st.markdown("---")
    with st.expander("📋 Google Sheets 運行・配送費データ（境町拠点）"):
        st.caption(f"データソース: {SAKAI_SHEET_URL[:80]}...")
        try:
            from sheets_client import load_sakai_operation_data
            with st.spinner("Google Sheets 読み込み中..."):
                gs_df = load_sakai_operation_data(SAKAI_SHEET_URL)
            if not gs_df.empty:
                st.dataframe(gs_df, use_container_width=True, hide_index=True)
                st.caption(f"✅ {len(gs_df)} 行 × {len(gs_df.columns)} 列を取得")
            else:
                st.info("データが空か、認証が必要です。")
        except Exception as e:
            st.warning(f"読み込み中にエラーが発生しました：{e}")


# ══════════════════════════════════════════════
# Tab 2: ルートマップ
# ══════════════════════════════════════════════
with tab_route:
    st.subheader("運行ルート × 積載率マップ")
    st.caption("線の色：赤=低積載、緑=高積載　／　線の太さ：積載率に比例")
    route_map, missing = map_view.build_route_map(df_ops, facility_lookup)
    st_folium(route_map, width="100%", height=560, returned_objects=[])
    if missing:
        st.warning(f"拠点マスタ未登録の拠点：{', '.join(set(missing))}")


# ══════════════════════════════════════════════
# Tab 3: ヒートマップ
# ══════════════════════════════════════════════
with tab_heat:
    st.subheader("エリア別 積載率ヒートマップ")
    st.caption("赤いエリア＝低積載（改善優先度高）")
    heat_map = map_view.build_heatmap(df_ops, facility_lookup)
    st_folium(heat_map, width="100%", height=520, returned_objects=[])
    area_table = (
        df_ops.dropna(subset=["到着地","積載率"]).groupby("到着地")["積載率"]
        .agg(["mean","min","max","count"]).round(1)
        .rename(columns={"mean":"平均(%)","min":"最低(%)","max":"最高(%)","count":"便数"})
        .sort_values("平均(%)").reset_index()
    )
    if not area_table.empty:
        st.dataframe(area_table, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# Tab 4: 収益マップ
# ══════════════════════════════════════════════
with tab_rev:
    st.subheader("エリア別 収益マップ")
    st.caption("円の大きさ＝合計売上")
    rev_map = map_view.build_revenue_map(df_ops, facility_lookup)
    st_folium(rev_map, width="100%", height=520, returned_objects=[])
    rev_t = (
        df_ops.dropna(subset=["到着地","売上"]).groupby("到着地")["売上"]
        .agg(合計売上="sum", 便数="count").reset_index()
    )
    if not rev_t.empty:
        rev_t["1便あたり"] = (rev_t["合計売上"] / rev_t["便数"]).round(0).astype(int)
        rev_t["合計売上"] = rev_t["合計売上"].apply(lambda x: f"¥{int(x):,}")
        rev_t["1便あたり"] = rev_t["1便あたり"].apply(lambda x: f"¥{x:,}")
        st.dataframe(rev_t.sort_values("合計売上", ascending=False), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# Tab 5: 最適化提案
# ══════════════════════════════════════════════
with tab_opt:
    st.subheader("⚡ 最適化・改善提案")
    suggestions = optimization.analyze(df_ops)
    if not suggestions:
        st.success("✅ 現在のフィルター範囲では目立った改善点は見つかりませんでした。")
    else:
        picons = {"高":"🔴","中":"🟡","低":"🟢"}
        cicons = {"統合":"🔗","混載":"📦","ルート":"🗺️","収益":"💰"}
        for s in suggestions:
            with st.expander(f"{picons.get(s.priority,'⚪')} [{s.priority}] {cicons.get(s.category,'📌')} {s.title}",
                             expanded=(s.priority == "高")):
                st.write(s.detail)
                st.info(f"💡 **改善効果の見込み：** {s.impact}")

    st.markdown("---")
    st.markdown("#### 運行データ一覧")
    cols = [c for c in ["便No","日付","出発地","到着地","積載率","売上","商品カテゴリ","担当"] if c in df_ops.columns]
    st.dataframe(df_ops[cols].sort_values("日付" if "日付" in df_ops.columns else cols[0]),
                 use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────
st.markdown("---")
st.caption("配送運行「見える化」ダッシュボード　|　地図 © OpenStreetMap　|　舞台ファーム GS境拠点対応版")
