"""Part 3 - Organizational Authenticity Index (OAI).

Concept
  Authenticity = the degree to which what a firm SAYS it values (About page, Part 1) is BACKED by
  what its mandated disclosures show it does and rewards (proxy statement, Part 2).

Operationalisation ("alignment" as weighted backing)
  For firm i, year t, theme k:
    s_ikt  stated emphasis  = LLM salience_k / sum_k salience_k            (Part 1; sums to 1)
    b_ikt  lived backing in [0,1], relative to peers in the same filing year:
             b = w_d * Pctl_t(substantive disclosure density_k)   [Part 2: dictionary density x LLM substantive share]
               + w_p * PayScore_t(incentive-pay weight_k)          [Part 2: CD&A metric weights]
           PayScore = 0 if no pay linkage; else 0.5 + 0.5 * pct-rank among firms WITH a linkage
           (any real pay linkage puts a firm at least at the midpoint of the pay scale).
    OAI_it = sum_k s_ikt * b_ikt                     in [0,1]; reported x100
  Read: "Of the things this firm says it values, weighted by how loudly it says them, how strongly
  - relative to its peers that year - do its disclosures and pay back them up?" 50 = typical.

Why this and not cosine(stated, lived)?
  * Asymmetry. Authenticity is about claims being backed, not about saying everything one does.
    Doing more than one says (quiet practice) should not be penalised as inauthentic; cosine would.
    The converse - "walking without talking" - is reported separately (silent_strengths).
  * Base-rate neutrality. Proxies are governance documents: performance and governance words
    saturate every proxy while "collaboration" barely appears. Raw shares would mechanically
    reward firms that claim performance values. Within-year peer percentiles put every theme on the
    same footing and also absorb year-wide disclosure trends (e.g. 2021 human-capital rules).
  * Interpretability. OAI decomposes additively into theme contributions s_k * b_k, so a low score
    can be traced to specific unbacked claims (say_do_gaps).

Companion measures (same file): congruence (Spearman of s and b across themes), say_do_gaps
(themes with salience >= 2 but backing < 1/3), silent_strengths (salience 0 but backing > 3/4),
n_themes_stated, stated_imputed flag.

Timing: stated year t is paired with the proxy FILED in year t (both describe the firm around
mid-year t; the proxy reports on fiscal t-1). --lag 1 pairs stated t with proxy t+1 instead.

Outputs (outputs/part3/): oai_firm_year.csv, oai_theme_long.csv, distribution.md, oai_distribution.png
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from authenticity.config import out_dir
from authenticity.themes import theme_ids

TIDS = theme_ids()
# Spearman on a firm whose backing is identical across themes is undefined -> NaN, not a problem.
warnings.filterwarnings("ignore", message="An input array is constant")


def load_stated(carry_forward: int) -> pd.DataFrame:
    s = pd.read_csv(out_dir("part1") / "stated_values.csv")
    # Eligibility rules are defined (and documented per row) in Part 1, step 5.
    if "index_eligible" in s:
        usable = s["index_eligible"].astype(str).str.lower() == "true"
    else:
        usable = s["sal_integrity_ethics"].notna() & (s.get("page_type") != "not_an_about_page")
    s = s[["ticker", "company_name", "sector", "year"] + [f"sal_{t}" for t in TIDS]].copy()
    s.loc[~usable, [f"sal_{t}" for t in TIDS]] = np.nan
    s = s.sort_values(["ticker", "year"])
    s["stated_imputed"] = False
    if carry_forward:
        # Fill a missing year from the most recent observed year, at most `carry_forward` years
        # back. Flagged, and excluded in the robustness check, because pages DO change.
        cols = [f"sal_{t}" for t in TIDS]
        filled = s.groupby("ticker")[cols].ffill(limit=carry_forward)
        s["stated_imputed"] = s[cols[0]].isna() & filled[cols[0]].notna()
        s[cols] = filled
    return s


def pct_rank(x: pd.Series) -> pd.Series:
    return x.rank(pct=True, method="average")


def pay_score(x: pd.Series) -> pd.Series:
    out = pd.Series(0.0, index=x.index)
    pos = x > 0
    if pos.sum():
        out[pos] = 0.5 + 0.5 * x[pos].rank(pct=True, method="average")
    out[x.isna()] = np.nan
    return out


def lived_backing(peer: str, w_disc: float) -> pd.DataFrame:
    """Long table (ticker, year, theme, b_disc, b_pay, b) with peer-relative scores."""
    l = pd.read_csv(out_dir("part2") / "lived_values.csv")
    l = l[l.status == "ok"]
    groups = ["year"] if peer == "all" else ["year", "sector"]
    rows = []
    for t in TIDS:
        d = l[["ticker", "sector", "year"]].copy()
        d["theme"] = t
        d["lived_raw_disc"] = l[f"subst_dens_{t}"] if f"subst_dens_{t}" in l else np.nan
        d["lived_raw_pay"] = l[f"pay_w_{t}"] if f"pay_w_{t}" in l else 0.0
        d["b_disc"] = d.groupby(groups)["lived_raw_disc"].transform(pct_rank)
        d["b_pay"] = d.groupby(groups)["lived_raw_pay"].transform(pay_score)
        rows.append(d)
    out = pd.concat(rows, ignore_index=True)
    out["b_pay"] = out["b_pay"].fillna(0)
    out["b"] = w_disc * out["b_disc"] + (1 - w_disc) * out["b_pay"]
    return out.drop(columns="sector")


def compute(peer: str = "all", w_disc: float = 0.6, lag: int = 0, carry_forward: int = 1,
            drop_imputed: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = load_stated(carry_forward)
    if drop_imputed:
        s.loc[s.stated_imputed, [f"sal_{t}" for t in TIDS]] = np.nan
    long_s = s.melt(id_vars=["ticker", "company_name", "sector", "year", "stated_imputed"],
                    value_vars=[f"sal_{t}" for t in TIDS], var_name="theme", value_name="salience")
    long_s["theme"] = long_s.theme.str[4:]
    tot = long_s.groupby(["ticker", "year"]).salience.transform("sum")
    long_s["s_share"] = np.where(tot > 0, long_s.salience / tot, np.nan)
    lb = lived_backing(peer, w_disc)
    lb["year"] = lb["year"] - lag  # proxy filed t+lag is matched to stated year t
    long = long_s.merge(lb, on=["ticker", "year", "theme"], how="left")
    long["contrib"] = long.s_share * long.b

    keys = ["oai", "congruence", "n_themes_stated", "mean_backing_all_themes", "say_do_gaps",
            "silent_strengths", "top_backed_claims"]

    def firm_year(g):
        ok = g.dropna(subset=["s_share", "b"])
        if ok.empty or len(ok) < len(TIDS):  # need both sides for every theme
            return pd.Series({k: np.nan for k in keys}, dtype=object)
        cong = ok.salience.corr(ok.b, method="spearman") if ok.salience.nunique() > 1 else np.nan
        gaps = ok[(ok.salience >= 2) & (ok.b < 1 / 3)].theme
        silent = ok[(ok.salience == 0) & (ok.b > 0.75)].theme
        top = ok.sort_values("contrib", ascending=False).theme.head(3)
        return pd.Series({"oai": 100 * ok.contrib.sum(), "congruence": cong,
                          "n_themes_stated": int((ok.salience >= 2).sum()),
                          "mean_backing_all_themes": ok.b.mean(),
                          "say_do_gaps": ";".join(gaps), "silent_strengths": ";".join(silent),
                          "top_backed_claims": ";".join(top)}, dtype=object)

    fy = (long.groupby(["ticker", "company_name", "sector", "year", "stated_imputed"])
              .apply(firm_year, include_groups=False).reset_index())
    for c in ("oai", "congruence", "n_themes_stated", "mean_backing_all_themes"):
        fy[c] = pd.to_numeric(fy[c], errors="coerce")
    # Simple benchmark: what OAI would be if the firm's stated emphasis were uniform. The
    # difference isolates the contribution of WHICH themes the firm chooses to claim.
    fy = fy.merge(long.groupby(["ticker", "year"]).b.mean().rename("oai_uniform_claims")
                  .mul(100).reset_index(), on=["ticker", "year"], how="left")
    fy["claim_selection_effect"] = fy.oai - fy.oai_uniform_claims
    return fy, long


def distribution_report(fy: pd.DataFrame) -> str:
    x = fy.dropna(subset=["oai"])
    if x.empty:
        return "No firm-years with both stated and lived data."
    # Variance decomposition: how much of OAI variation is stable between-firm vs. over time.
    firm_means = x.groupby("ticker").oai.transform("mean")
    between = firm_means.var()
    within = (x.oai - firm_means).var()
    yr = x.groupby("year").oai.agg(["count", "mean", "std", "min", "max"]).round(2)
    unscored = sorted(set(fy.ticker) - set(x.ticker))
    lines = ["# OAI distribution (auto-generated)\n",
             f"- Firm-years scored: {len(x)} of {len(fy)}; firms: {x.ticker.nunique()}"
             + (f" (never scored: {', '.join(unscored)})" if unscored else ""),
             f"- Overall: mean {x.oai.mean():.1f}, sd {x.oai.std():.1f}, median {x.oai.median():.1f}, "
             f"IQR {x.oai.quantile(.25):.1f}-{x.oai.quantile(.75):.1f}, range {x.oai.min():.1f}-{x.oai.max():.1f}, "
             f"skew {x.oai.skew():.2f}",
             f"- Variance share between firms: {between / (between + within):.0%} "
             f"(within-firm over time: {within / (between + within):.0%})",
             f"- Mean |year-over-year change| within firm: "
             f"{x.sort_values('year').groupby('ticker').oai.diff().abs().mean():.1f} points",
             f"- Correlation OAI vs congruence: {x.oai.corr(x.congruence):.2f}",
             "\n## By sector\n", x.groupby("sector").oai.describe()[["count", "mean", "std", "min", "max"]].round(1).to_markdown(),
             "\n## By year\n", yr.to_markdown(),
             "\n## Highest and lowest firm averages\n",
             x.groupby(["ticker", "company_name"]).oai.mean().sort_values().round(1).to_frame()
              .pipe(lambda d: pd.concat([d.head(5), d.tail(5)])).to_markdown(),
             "\n## Most frequent say-do gaps (themes claimed but weakly backed)\n",
             x.say_do_gaps.str.split(";").explode().replace("", np.nan).dropna()
              .value_counts().head(8).to_markdown(),
             "\n## Most frequent silent strengths (backed but not claimed)\n",
             x.silent_strengths.str.split(";").explode().replace("", np.nan).dropna()
              .value_counts().head(8).to_markdown() if "silent_strengths" in x else "(n/a)",
             "\n## Each firm's average and its most frequent say-do gap\n",
             x.groupby(["ticker", "sector"]).agg(
                 oai=("oai", "mean"), years=("oai", "size"),
                 top_gap=("say_do_gaps", lambda s_: s_.str.split(";").explode().replace("", np.nan)
                          .dropna().mode().iat[0] if s_.str.len().fillna(0).gt(0).any() else "")
             ).round(1).sort_values("oai").to_markdown()]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--peer", choices=["all", "sector"], default="all")
    ap.add_argument("--w-disc", type=float, default=0.6, help="weight on disclosure vs pay backing")
    ap.add_argument("--lag", type=int, default=0)
    ap.add_argument("--carry-forward", type=int, default=1)
    args = ap.parse_args(argv)

    fy, long = compute(args.peer, args.w_disc, args.lag, args.carry_forward)
    od = out_dir("part3")
    fy.sort_values(["ticker", "year"]).to_csv(od / "oai_firm_year.csv", index=False)
    long.sort_values(["ticker", "year", "theme"]).to_csv(od / "oai_theme_long.csv", index=False)
    (od / "distribution.md").write_text(distribution_report(fy), encoding="utf-8")

    x = fy.dropna(subset=["oai"])
    if len(x):
        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        axes[0].hist(x.oai, bins=25, color="#4C72B0")
        axes[0].set_title("OAI, all firm-years")
        axes[0].set_xlabel("OAI (0-100)")
        secs = sorted(x.sector.unique())
        axes[1].boxplot([x[x.sector == s].oai for s in secs])
        axes[1].set_xticks(range(1, len(secs) + 1), [s.replace(" ", "\n") for s in secs], fontsize=7)
        axes[1].set_title("By sector")
        for s in secs:
            axes[2].plot(x[x.sector == s].groupby("year").oai.mean(), marker="o", ms=3, label=s)
        axes[2].legend(fontsize=7)
        axes[2].set_title("Sector mean over time")
        fig.tight_layout()
        fig.savefig(od / "oai_distribution.png", dpi=160)
        plt.close(fig)
    print((od / "distribution.md").read_text(encoding="utf-8")[:1500])


if __name__ == "__main__":
    main()
