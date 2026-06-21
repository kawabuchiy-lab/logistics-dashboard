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
import capacity_simulator
import logistics_strategy
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

tab_sakai, tab_sim, tab_strategy, tab_route, tab_heat, tab_rev, tab_opt = st.tabs([
    "🏭 境町拠点 スケジュール最適化",
    "📦 容量・収益シミュレーション",
    "🚀 物流プラットフォーム戦略",
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
# Tab 2: 容量・収益シミュレーション
# ══════════════════════════════════════════════
with tab_sim:
    st.subheader("📦 GS境拠点 容量・収益シミュレーション")
    st.caption("冷蔵庫3棟（計364パレット）をフル活用した場合の月別・日別取り扱いパレット数と売上見込みを算出します。")

    # ── パラメータ設定 ──
    with st.expander("⚙️ シミュレーション設定（クリックして展開）", expanded=True):
        sim_c1, sim_c2 = st.columns(2)
        with sim_c1:
            rev_per_pallet = st.slider(
                "1パレットあたり売上単価（円）",
                min_value=10000, max_value=200000, value=55000, step=5000,
                help="パレット1つを出荷した際の平均売上（運賃・保管料等含む）",
            )
        with sim_c2:
            turnover = st.slider(
                "月間パレット回転数（回/月）",
                min_value=1.0, max_value=10.0, value=4.0, step=0.5,
                help="1パレットが月に何回入出庫するか（回転数が高いほどスループットが増える）",
            )

    # ── 計算実行 ──
    df_sim = capacity_simulator.calc_monthly_capacity(
        revenue_per_pallet=rev_per_pallet,
        turnover_per_month=turnover,
    )
    annual_total = df_sim["売上見込(円)"].sum()
    annual_throughput = df_sim["月間取扱数"].sum()

    # ── 年間サマリー KPI ──
    st.markdown("---")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("📦 年間取り扱いパレット数", f"{annual_throughput:,}P")
    with k2:
        st.metric("💰 年間売上見込み", f"¥{annual_total/1e6:.1f}M")
    with k3:
        peak_row = df_sim.loc[df_sim["使用パレット"].idxmax()]
        st.metric("🔴 繁忙期ピーク月", peak_row["月"], f"占有率 {peak_row['占有率(%)']:.0f}%")
    with k4:
        st.metric("🏭 総容量", "364パレット", "第一120P＋第二120P＋第三124P")

    st.markdown("---")

    # ── チャート ──
    st.markdown("#### 📊 月別 パレット取り扱い数（占有率・空き容量）")
    cap_fig = capacity_simulator.build_monthly_capacity_chart(df_sim)
    st.plotly_chart(cap_fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### 💰 月別 売上見込み")
    rev_fig = capacity_simulator.build_revenue_chart(df_sim)
    st.plotly_chart(rev_fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### 🔄 月間・日別 取り扱いパレット数")
    tp_fig = capacity_simulator.build_throughput_chart(df_sim)
    st.plotly_chart(tp_fig, use_container_width=True, config={"displayModeBar": False})

    # ── シーズン別サマリーテーブル ──
    st.markdown("---")
    st.markdown("#### 🗓️ シーズン別 集計サマリー")
    season_table = capacity_simulator.build_season_comparison_table(df_sim)
    season_order = {"繁忙期": 0, "通常期": 1, "閑散期": 2}
    season_table["__order"] = season_table["シーズン"].map(season_order)
    season_table = season_table.sort_values("__order").drop(columns=["__order"])
    st.dataframe(season_table, use_container_width=True, hide_index=True)

    # ── 月別詳細テーブル ──
    st.markdown("---")
    st.markdown("#### 📋 月別 詳細データ")
    display_cols = ["月", "シーズン", "占有率(%)", "使用パレット", "空きパレット",
                    "稼働日数", "月間取扱数", "日別取扱数", "売上見込(円)"]
    df_display = df_sim[display_cols].copy()
    df_display["売上見込(円)"] = df_display["売上見込(円)"].apply(lambda x: f"¥{int(x):,}")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── 特定日の詳細計算 ──
    st.markdown("---")
    st.markdown("#### 🔍 特定日の詳細容量チェック")
    st.caption("今日の冷蔵庫占有率を入力して、その日の日別取り扱い可能数と売上見込みを確認できます。")
    day_c1, day_c2, day_c3, day_c4 = st.columns(4)
    with day_c1:
        day_month = st.selectbox("月", list(range(1, 13)), index=datetime.date.today().month - 1,
                                  format_func=lambda m: f"{m}月")
    with day_c2:
        day_ref1 = st.number_input("第一冷蔵庫(%)", 0, 100, 65, 5, key="day_ref1")
    with day_c3:
        day_ref2 = st.number_input("第二冷蔵庫(%)", 0, 100, 78, 5, key="day_ref2")
    with day_c4:
        day_ref3 = st.number_input("第三冷蔵庫(%)", 0, 100, 42, 5, key="day_ref3")

    day_result = capacity_simulator.calc_daily_capacity(
        month=day_month, ref1_pct=day_ref1, ref2_pct=day_ref2, ref3_pct=day_ref3,
        revenue_per_pallet=rev_per_pallet, turnover_per_month=turnover,
    )
    dr1, dr2, dr3, dr4 = st.columns(4)
    with dr1:
        st.metric("使用パレット", f"{day_result['使用パレット']}P", f"稼働率 {day_result['稼働率']}%")
    with dr2:
        st.metric("空きパレット", f"{day_result['空きパレット']}P", f"満杯まで {day_result['満杯まで']}P")
    with dr3:
        st.metric("日別取り扱い可能数", f"{day_result['日別取扱数']}P/日")
    with dr4:
        st.metric("日別売上見込み", f"¥{day_result['日別売上見込']:,}")


# ══════════════════════════════════════════════
# Tab 3: 物流プラットフォーム戦略
# ══════════════════════════════════════════════
with tab_strategy:
    st.subheader("🚀 物流プラットフォーム戦略｜対サラダボウル・関東全域カバー")
    st.caption("GS境 × KIFA川越 × 中越通運（羽生）3拠点体制でリード2タイム配送・関東全域制覇を目指す戦略設計シート")

    # ── 戦略コンセプトバナー
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1565C0,#0d47a1);color:white;
         padding:16px 24px;border-radius:10px;margin-bottom:16px">
      <div style="font-size:20px;font-weight:bold;margin-bottom:6px">
        🎯 舞台ファーム プラットフォーム戦略コンセプト
      </div>
      <div style="font-size:14px;opacity:0.92;line-height:1.8">
        「産地直結・OEM対応・48h以内配送」でサラダボウルが取れないニッチ高付加価値市場を独占する<br>
        ▶ 小・中規模外食チェーン / 高級スーパー / 給食センター / 食品メーカー（OEM原料）<br>
        ▶ 3拠点クロスドッキングで関東全域2h以内着荷を実現
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── タブ内サブタブ
    sub_map, sub_cost, sub_kanto, sub_vs, sub_strategy_list, sub_kpi, sub_roadmap = st.tabs([
        "🗺️ 拠点戦略マップ",
        "💴 拠点コスト比較",
        "📊 関東エリア分析",
        "🆚 vs サラダボウル",
        "💡 戦略オプション提案",
        "📋 KPI管理シート",
        "📅 実行ロードマップ",
    ])

    # ── 拠点戦略マップ ──────────────────────────
    with sub_map:
        st.markdown("#### 🗺️ 3拠点カバレッジマップ（関東全域）")
        st.caption("円＝各拠点のカバー圏（点線）。エリアマーカーの大きさ＝月間需要量。色＝担当拠点")
        hub_map = logistics_strategy.build_hub_strategy_map()
        st_folium(hub_map, width="100%", height=560, returned_objects=[])

        st.markdown("---")
        st.markdown("#### 🏭 拠点サマリー")
        for hub_name, hub in logistics_strategy.HUBS.items():
            icon = hub["icon"]
            color = hub["color"]
            with st.expander(f"{icon} **{hub_name}**　ステータス: {hub['status']}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("容量", f"{hub['capacity_pallets']}P")
                    st.metric("月額コスト", f"¥{hub['monthly_cost_yen']:,}")
                with c2:
                    st.metric("1P単価", f"¥{hub['cost_per_pallet']:,}")
                    st.metric("標準リード", f"{hub['lead_time_h']}h〜")
                with c3:
                    st.success(f"**強み：** {hub['strength']}")
                    st.error(f"**課題：** {hub['weakness']}")

    # ── コスト比較 ──────────────────────────────
    with sub_cost:
        st.markdown("#### 💴 3拠点 コスト比較分析")

        cost_fig = logistics_strategy.build_cost_comparison_chart()
        st.plotly_chart(cost_fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("---")
        st.markdown("#### 📊 シナリオ別 年間コスト比較")
        st.caption("3つのシナリオで年間拠点コストを比較。シナリオBが最推奨。")
        df_scenario = logistics_strategy.calc_scenario_comparison()
        scenario_fig = logistics_strategy.build_scenario_chart(df_scenario)
        st.plotly_chart(scenario_fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("---")
        st.markdown("#### 📋 シナリオ詳細比較表")
        display_scenario = df_scenario.copy()
        display_scenario["年間拠点コスト(円)"] = display_scenario["年間拠点コスト(円)"].apply(lambda x: f"¥{x:,}")
        display_scenario["現状比コスト削減(円)"] = display_scenario["現状比コスト削減(円)"].apply(lambda x: f"▲¥{x:,}" if x > 0 else "基準")
        display_scenario["現状比削減率(%)"] = display_scenario["現状比削減率(%)"].apply(lambda x: f"{x}%" if x != 0 else "基準")
        st.dataframe(display_scenario, use_container_width=True, hide_index=True)

        # 川越コストシミュレーター
        st.markdown("---")
        st.markdown("#### 🎛️ KIFA川越コスト削減シミュレーター")
        kifa_current = st.slider("KIFA川越 現状月額コスト（万円）", 50, 300, 180, 10)
        kifa_reduction = st.slider("削減目標率（%）", 0, 80, 60, 5)
        kifa_target = int(kifa_current * (1 - kifa_reduction / 100))
        hanyu_cost  = st.slider("中越通運（羽生）月額コスト（万円）", 50, 200, 90, 10)
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("現状KIFA月額", f"¥{kifa_current*10000:,}", "現在")
        with k2:
            st.metric("目標KIFA月額", f"¥{kifa_target*10000:,}", f"▲{kifa_reduction}%削減")
        with k3:
            net_saving = (kifa_current - kifa_target - hanyu_cost) * 10000
            st.metric("羽生追加後 月間純節約", f"¥{net_saving:,}", f"年間 ¥{net_saving*12:,}")

    # ── 関東エリア分析 ──────────────────────────
    with sub_kanto:
        st.markdown("#### 📊 関東エリア別 需要・担当拠点マトリクス")
        demand_fig = logistics_strategy.build_kanto_demand_chart()
        st.plotly_chart(demand_fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("---")
        st.markdown("#### 📋 エリア別 詳細データ")
        df_kanto = logistics_strategy.calc_kanto_coverage_table()
        total_demand = df_kanto["月間需要(パレット)"].sum()
        total_rev = df_kanto["月間売上見込(円)"].sum()

        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("関東エリア合計月間需要", f"{total_demand}P/月")
        with k2:
            st.metric("月間売上見込み合計", f"¥{total_rev/1e6:.1f}M")
        with k3:
            st.metric("年間売上見込み合計", f"¥{total_rev*12/1e6:.1f}M")

        df_kanto_disp = df_kanto.copy()
        df_kanto_disp["月間売上見込(円)"] = df_kanto_disp["月間売上見込(円)"].apply(lambda x: f"¥{int(x):,}")
        df_kanto_disp["年間売上見込(円)"] = df_kanto_disp["年間売上見込(円)"].apply(lambda x: f"¥{int(x):,}")
        st.dataframe(df_kanto_disp, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 🔍 拠点-エリア 担当割当詳細")
        df_assign = logistics_strategy.calc_zone_hub_assignment()
        df_main = df_assign[df_assign["主担当"] == True][["エリア","拠点","直線距離(km)","推定リードタイム(h)","優先度"]]
        st.dataframe(df_main.sort_values("優先度"), use_container_width=True, hide_index=True)

    # ── vs サラダボウル ──────────────────────────
    with sub_vs:
        st.markdown("#### 🆚 サラダボウル vs 舞台ファーム 差別化分析")
        radar_fig = logistics_strategy.build_vs_competitor_radar()
        st.plotly_chart(radar_fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("---")
        col_comp, col_butai = st.columns(2)
        with col_comp:
            st.markdown("##### ⚠️ サラダボウル（競合）")
            cp = logistics_strategy.COMPETITOR_PROFILE
            st.markdown(f"**ターゲット：** {cp['target_segment']}")
            st.markdown("**強み：**")
            for s in cp["strength"]:
                st.markdown(f"　✅ {s}")
            st.markdown("**弱み（舞台ファームが攻めるポイント）：**")
            for w in cp["weakness"]:
                st.markdown(f"　🎯 **{w}**")

        with col_butai:
            st.markdown("##### 🏆 舞台ファーム 差別化戦略")
            bd = logistics_strategy.BUTAI_DIFFERENTIATION
            st.info(f"**コンセプト：** {bd['戦略コンセプト']}")
            st.markdown("**狙うセグメント（サラダボウルが苦手な市場）：**")
            for seg in bd["ターゲットセグメント"]:
                st.markdown(f"　🎯 {seg}")
            st.markdown("**差別化ポイント：**")
            for pt in bd["差別化ポイント"]:
                st.markdown(f"　⚡ {pt}")

    # ── 戦略オプション提案 ──────────────────────
    with sub_strategy_list:
        st.markdown("#### 💡 戦略オプション一覧（優先度順）")
        priority_order = {"最優先": 0, "高": 1, "中": 2, "低（中長期）": 3}
        sorted_opts = sorted(
            logistics_strategy.STRATEGY_OPTIONS,
            key=lambda x: priority_order.get(x["priority"], 9),
        )

        priority_colors = {
            "最優先": ("🔴", "#ffcdd2"),
            "高":     ("🟠", "#fff3e0"),
            "中":     ("🟡", "#fffde7"),
            "低（中長期）": ("🟢", "#e8f5e9"),
        }

        for opt in sorted_opts:
            icon, bg = priority_colors.get(opt["priority"], ("⚪", "#f5f5f5"))
            with st.expander(f"{icon} **{opt['name']}**　[{opt['category']}] 優先度：{opt['priority']}"):
                st.markdown(f"**概要：** {opt['summary']}")
                st.markdown(f"**詳細：** {opt['detail']}")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.success(f"**期待効果：** {opt['expected_cost_reduction']}")
                with c2:
                    st.info(f"**実行期間：** {opt['timeline']}")
                with c3:
                    st.warning(f"**KPI：** {opt['kpi']}")

    # ── KPI管理シート ────────────────────────────
    with sub_kpi:
        st.markdown("#### 📋 プラットフォームKPI管理シート")
        st.caption("目標値はシステム設定値です。実績列に数値を入力することで達成率が自動計算されます。")

        kifa_act = st.number_input("KIFA川越 今月実績コスト（円）", 0, 5_000_000, 1_800_000, 100_000, key="kifa_act")
        df_kpi = logistics_strategy.calc_platform_kpi_sheet(kifa_cost_actual=kifa_act)
        st.dataframe(df_kpi, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 📊 月次アクション管理")
        action_data = {
            "アクション": [
                "KIFA川越 コスト交渉・見直し",
                "中越通運（羽生）現地視察・見積取得",
                "埼玉北部エリア 新規顧客開拓",
                "東京都心圏 サラダボウル切替営業",
                "OEM提案書の新規送付",
                "混載パートナー農家へのヒアリング",
            ],
            "担当者": ["営業/経営", "物流", "営業", "営業", "営業", "物流"],
            "期限": ["今月末", "2週間以内", "今月中", "今月中", "今月中", "来月"],
            "ステータス": ["未着手", "未着手", "未着手", "未着手", "未着手", "未着手"],
            "優先度": ["最優先", "最優先", "高", "高", "中", "中"],
        }
        st.data_editor(
            pd.DataFrame(action_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ステータス": st.column_config.SelectboxColumn(
                    "ステータス", options=["未着手", "進行中", "完了", "保留"], required=True
                ),
                "優先度": st.column_config.SelectboxColumn(
                    "優先度", options=["最優先", "高", "中", "低"], required=True
                ),
            },
        )

    # ── 実行ロードマップ ─────────────────────────
    with sub_roadmap:
        st.markdown("#### 📅 戦略実行ロードマップ（今後12ヶ月）")
        roadmap_fig = logistics_strategy.build_implementation_timeline()
        st.plotly_chart(roadmap_fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("---")
        st.markdown("""
        #### 🎯 フェーズ別 実行計画

        | フェーズ | 時期 | 主要アクション | 目標 |
        |---------|------|---------------|------|
        | **Phase 1**<br>リスクヘッジ | 今月〜2ヶ月 | 中越通運（羽生）視察・契約交渉 | KIFA川越コスト▲30%削減 |
        | **Phase 2**<br>3拠点確立 | 2〜4ヶ月 | GS境→羽生→川越チェーン試験運用 | リード2タイム達成率80%以上 |
        | **Phase 3**<br>関東拡張 | 3〜6ヶ月 | 千葉・神奈川エリア営業開始 | S/A優先エリア全カバー |
        | **Phase 4**<br>差別化加速 | 4〜8ヶ月 | 産直EC・混載PF・OEM営業強化 | 月間新規3社獲得 |
        | **Phase 5**<br>DX化 | 6〜12ヶ月 | デジタル受発注PF構築 | 受注工数▲40%・顧客LTV+10% |
        """)

        st.markdown("---")
        st.info("""
        **💡 今すぐできる最優先アクション（今週中）**

        1. **中越通運（羽生センター）への問い合わせ** → 月額見積・契約条件・容量確認
        2. **KIFA川越との再交渉** → 現状コストの根拠確認・削減交渉
        3. **埼玉北部〜群馬方面の既存顧客リスト整備** → 羽生センター移行時の配送見直し準備
        4. **対サラダボウル トークスクリプト作成** → 「小ロット・OEM・産地直送」の強みを明文化
        """)


# ══════════════════════════════════════════════
# Tab 4: ルートマップ
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
