"""運行データから最適化・改善提案を自動生成。"""
import pandas as pd
import numpy as np
from typing import NamedTuple


class Suggestion(NamedTuple):
    priority: str
    category: str
    title: str
    detail: str
    impact: str


def analyze(df: pd.DataFrame) -> list[Suggestion]:
    suggestions = []
    if df.empty:
        return suggestions

    if "積載率" in df.columns:
        low = df[df["積載率"] < 60]
        if not low.empty:
            suggestions.append(Suggestion("高", "統合",
                f"積載率60%未満の便が {len(low)}件 あります",
                f"平均積載率 {low['積載率'].mean():.1f}% の低積載便を近隣便と統合することで車両台数を削減できます。",
                f"空走距離 約{len(low)*30:.0f}km/月 削減見込み"))

        empty = df[df["積載率"] < 20]
        if not empty.empty:
            suggestions.append(Suggestion("高", "混載",
                f"ほぼ空荷の便が {len(empty)}件 あります（積載率20%未満）",
                "外部貨物の混載や帰り荷の確保を優先すべき便です。",
                "1便あたり ¥8,000〜¥15,000 の追加収益機会"))

    if "積載率" in df.columns and "到着地" in df.columns:
        area_stats = df.dropna(subset=["到着地","積載率"]).groupby("到着地")["積載率"].agg(["mean","count"])
        chronic = area_stats[(area_stats["mean"]<65) & (area_stats["count"]>=3)].sort_values("mean")
        if not chronic.empty:
            w = chronic.iloc[0]
            suggestions.append(Suggestion("中", "ルート",
                f"「{w.name}」エリアが慢性的な低積載です（平均 {w['mean']:.1f}%）",
                f"直近 {int(w['count'])} 便の平均積載率が {w['mean']:.1f}% です。配送頻度の見直しを検討してください。",
                "週1便削減で 年間 約 ¥100,000〜¥200,000 削減見込み"))

    if "売上" in df.columns and "到着地" in df.columns:
        rev = df.dropna(subset=["到着地","売上"]).groupby("到着地")["売上"].agg(["sum","count"])
        rev["per"] = rev["sum"] / rev["count"]
        low_eff = rev[(rev["per"] < rev["per"].median()*0.6) & (rev["count"]>=2)].sort_values("per")
        if not low_eff.empty:
            w = low_eff.iloc[0]
            suggestions.append(Suggestion("中", "収益",
                f"「{w.name}」の1便あたり売上が低い（¥{int(w['per']):,}/便）",
                f"全エリア中央値 ¥{int(rev['per'].median()):,}/便 に対し低い水準です。値上げ交渉を検討してください。",
                "月間 ¥50,000〜¥100,000 の収益改善余地"))

    return suggestions


def get_summary_kpis(df: pd.DataFrame) -> dict:
    kpis = {"総便数": len(df), "平均積載率": None, "低積載便数": None, "総売上": None}
    if "積載率" in df.columns:
        r = df["積載率"].dropna()
        kpis["平均積載率"] = r.mean() if len(r) else None
        kpis["低積載便数"] = int((r < 60).sum())
    if "売上" in df.columns:
        v = df["売上"].dropna()
        kpis["総売上"] = v.sum() if len(v) else None
    return kpis
