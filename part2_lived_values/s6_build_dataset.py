"""Part 2, step 6 - Aggregate all measures into the company-year dataset.

Output (outputs/part2/):
  lived_values.csv        one row per company-year (450 rows incl. gaps); columns in CODEBOOK.md
  pay_metrics_long.csv    every extracted incentive metric (one row per metric)
  theme_trends.png        mean theme density by year (full document), 6 focal themes
  digest.md               auto-generated numbers for SUMMARY.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from authenticity.config import YEARS, interim_dir, load_companies, out_dir
from authenticity.themes import taxonomy, theme_ids

TIDS = theme_ids()
NONFIN_THEMES = {"environment_climate", "diversity_inclusion", "health_safety", "community_society",
                 "employees_people", "customer_focus", "integrity_ethics"}


def read(name):
    p = interim_dir("part2") / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["ticker", "year"])


def passage_measures(ps: pd.DataFrame) -> pd.DataFrame:
    """Per company-year: number of passages labelled with each theme and the share substantive."""
    if ps.empty:
        return pd.DataFrame(columns=["ticker", "year"])
    ps = ps.dropna(subset=["evidence_type"]).copy()
    ps["themes"] = ps["themes"].fillna("")
    long = ps.assign(theme=ps.themes.str.split(";")).explode("theme")
    long = long[long.theme.isin(TIDS)]
    agg = long.groupby(["ticker", "year", "theme"]).agg(n=("substantive", "size"),
                                                        sub=("substantive", "mean")).reset_index()
    n = agg.pivot_table(index=["ticker", "year"], columns="theme", values="n", fill_value=0)
    s = agg.pivot_table(index=["ticker", "year"], columns="theme", values="sub")
    n = n.reindex(columns=TIDS, fill_value=0).add_prefix("npass_")
    s = s.reindex(columns=TIDS).add_prefix("subst_ratio_")
    overall = ps.groupby(["ticker", "year"]).substantive.mean().rename("subst_ratio_all")
    return pd.concat([n, s, overall], axis=1).reset_index()


def pay_measures(pm: pd.DataFrame) -> pd.DataFrame:
    """Per company-year incentive-pay weight on each theme (sums to 1 across themes).
    Within each plan: stated weights normalised; if any non-modifier weight is missing the plan
    falls back to equal weights. Annual and long-term plans are averaged with equal weight.
    Modifiers are recorded separately (presence flags), not in the weights."""
    if pm.empty or "metric" not in pm:
        return pd.DataFrame(columns=["ticker", "year"])
    out = []
    for (tk, y), g in pm.groupby(["ticker", "year"]):
        g = g.dropna(subset=["metric"])
        row = dict(ticker=tk, year=y, pay_n_metrics=len(g),
                   pay_n_nonfinancial=int((g.get("kind") != "financial").sum()) if len(g) else 0,
                   pay_has_strategic=bool(g["has_strategic"].fillna(False).astype(bool).any()) if len(g) else False)
        plan_vecs = []
        core = g[~g.is_modifier.fillna(False).astype(bool)] if len(g) else g
        for plan, gp in core.groupby("plan") if len(core) else []:
            w = pd.to_numeric(gp.weight_pct, errors="coerce")
            w = w if w.notna().all() and w.sum() > 0 else pd.Series(1.0, index=gp.index)
            v = (w / w.sum()).groupby(gp.theme).sum()
            plan_vecs.append(v.reindex(TIDS, fill_value=0))
        if plan_vecs:
            vec = sum(plan_vecs) / len(plan_vecs)
            row.update({f"pay_w_{t}": round(float(vec[t]), 4) for t in TIDS})
        else:
            row.update({f"pay_w_{t}": 0.0 for t in TIDS})
        mods = g[g.is_modifier.fillna(False).astype(bool)] if len(g) else g
        row.update({f"pay_mod_{t}": int(t in set(mods.theme)) for t in TIDS})
        row["pay_has_nonfin_metric"] = bool(set(core.theme) & NONFIN_THEMES) if len(core) else False
        out.append(row)
    return pd.DataFrame(out)


def main():
    cos = load_companies()[["ticker", "company_name", "sector"]]
    grid = cos.merge(pd.DataFrame({"year": YEARS}), how="cross")
    man = read("proxy_manifest.csv")
    keep = ["ticker", "year", "status", "missing_reason", "filing_date", "accession", "url", "cik",
            "is_predecessor_cik", "annual_meeting_detected", "download_note", "n_def14a_in_year"]
    man = man[[c for c in keep if c in man.columns]]
    df = (grid.merge(man, on=["ticker", "year"], how="left")
              .merge(read("docs.csv"), on=["ticker", "year"], how="left")
              .merge(read("classical.csv"), on=["ticker", "year"], how="left")
              .merge(passage_measures(read("llm_passages.csv")), on=["ticker", "year"], how="left")
              .merge(pay_measures(read("llm_pay_metrics.csv")), on=["ticker", "year"], how="left"))
    df["status"] = df["status"].fillna("missing")
    if "missing_reason" not in df:  # absent when every company-year has a proxy
        df["missing_reason"] = pd.NA
    df.loc[(df.status != "ok") & df.missing_reason.isna(), "missing_reason"] = "not_attempted"
    df["fiscal_year_described"] = df["year"] - 1  # proxies filed in Y describe FY Y-1 (approx.)

    # Substantive disclosure intensity: emphasis (dictionary density) x quality (LLM substantive
    # share). Where the LLM sample had no passage for a theme, fall back to the document's
    # overall substantive share (documented assumption).
    # If the document had no labelled passage at all, use the corpus-wide share for that theme.
    # A theme with zero density has zero substantive density by definition.
    for t in TIDS:
        if f"dens_{t}" in df:
            if f"subst_ratio_{t}" not in df:
                df[f"subst_ratio_{t}"] = np.nan
            corpus_ratio = df[f"subst_ratio_{t}"].mean()
            ratio = (df[f"subst_ratio_{t}"].fillna(df.get("subst_ratio_all", np.nan))
                     .fillna(corpus_ratio if pd.notna(corpus_ratio) else 0.5))
            df[f"subst_dens_{t}"] = np.where(df[f"dens_{t}"] == 0, 0.0,
                                             (df[f"dens_{t}"] * ratio).round(4))
            df.loc[df[f"dens_{t}"].isna(), f"subst_dens_{t}"] = np.nan

    od = out_dir("part2")
    df.sort_values(["ticker", "year"]).to_csv(od / "lived_values.csv", index=False)
    pm = read("llm_pay_metrics.csv")
    if len(pm):
        pm.to_csv(od / "pay_metrics_long.csv", index=False)

    # Figure ----------------------------------------------------------------
    focal = ["diversity_inclusion", "environment_climate", "employees_people", "health_safety",
             "community_society", "integrity_ethics"]
    ok = df[df.status == "ok"]
    if len(ok) and "dens_diversity_inclusion" in ok:
        fig, axes = plt.subplots(2, 3, figsize=(12, 6), sharex=True)
        for ax, t in zip(axes.flat, focal):
            for sec, g in ok.groupby("sector"):
                ax.plot(g.groupby("year")[f"dens_{t}"].mean(), marker="o", ms=3, label=sec)
            ax.set_title(taxonomy()["themes"][t]["label"], fontsize=10)
            ax.axvline(2021, color="grey", ls=":", lw=1)  # first proxies after mid-2020 events
            ax.axvline(2024, color="grey", ls="--", lw=1)  # first proxies after SFFA / backlash
        axes.flat[0].legend(fontsize=7)
        fig.suptitle("Theme density in proxy statements (hits per 1,000 words), by filing year and sector")
        fig.tight_layout()
        fig.savefig(od / "theme_trends.png", dpi=160)
        plt.close(fig)

    # Digest ----------------------------------------------------------------
    lines = ["# Part 2 digest (auto-generated)\n",
             f"- Company-years with a proxy: {(df.status == 'ok').sum()} / {len(df)}",
             f"- Gaps: {df.loc[df.status != 'ok', 'missing_reason'].value_counts().to_dict()}",
             f"- CD&A located: {df.cda_found.mean():.0%} of downloaded proxies" if "cda_found" in df else "",
             (f"- CD&A with unusual length (<2.5k or >30k words, check boundaries): "
              f"{', '.join(f'{t} {y}' for t, y in df.loc[df.cda_suspect.fillna(False).astype(bool), ['ticker', 'year']].values)}")
             if "cda_suspect" in df else "",
             (f"- Layout-repaired documents (layout tables / lost line breaks): "
              f"{', '.join(f'{t} {y}' for t, y in df.loc[df.layout_repaired.fillna(False).astype(bool), ['ticker', 'year']].values) or 'none'}")
             if "layout_repaired" in df else ""]
    if len(ok) and "dens_diversity_inclusion" in ok:
        lines += ["\n## Mean theme density (per 1,000 words) by filing year\n",
                  ok.groupby("year")[[f"dens_{t}" for t in TIDS]].mean().round(2).T.to_markdown(),
                  "\n## Mean theme density by sector\n",
                  ok.groupby("sector")[[f"dens_{t}" for t in TIDS]].mean().round(2).T.to_markdown()]
    if "subst_ratio_all" in ok:
        lines += ["\n## Share of theme passages that are substantive, by year\n",
                  ok.groupby("year")["subst_ratio_all"].mean().round(3).to_markdown()]
    if "pay_has_nonfin_metric" in ok:
        lines += ["\n## Share of firms with >=1 non-financial incentive metric, by year\n",
                  ok.groupby("year")["pay_has_nonfin_metric"].mean().round(2).to_markdown(),
                  "\n## Mean incentive-pay weight by theme and year\n",
                  ok.groupby("year")[[f"pay_w_{t}" for t in TIDS]].mean().round(3).T.to_markdown()]
    if "sim_prior_year" in ok:
        lines += ["\n## Year-over-year document similarity (boilerplate stickiness), by sector\n",
                  ok.groupby("sector")["sim_prior_year"].describe()[["mean", "50%", "min"]].round(3).to_markdown()]
    (od / "digest.md").write_text("\n".join(l for l in lines if l is not None), encoding="utf-8")
    print(f"wrote {od}/lived_values.csv ({len(df)} rows, {df.shape[1]} cols)")


if __name__ == "__main__":
    main()
