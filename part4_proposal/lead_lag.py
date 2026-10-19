"""Part 4 - Does talk lead walk, or walk lead talk?  (with the 2019-2024 DEI cycle as a case)

Question
  A static OAI says how aligned a firm is; it does not say how alignment is PRODUCED. Two
  competing accounts from organisation theory make opposite predictions:
    * "Aspirational talk" (Christensen, Morsing & Thyssen 2013): public value statements are
      commitments that later pull practice toward them  -> changes in stated emphasis PRECEDE
      changes in lived backing.
    * Decoupling / impression management (Meyer & Rowan 1977; Bromley & Powell 2012): firms adjust
      rhetoric to the institutional mood while practice moves slowly or not at all -> stated
      emphasis moves with the environment and does not predict practice; if anything practice
      leads (firms talk about what they already do).
  With a firm x theme x year panel we can test which direction the data favour.

Design
  Theme-level panel from Part 3 (oai_theme_long.csv): salience_ikt (0-3) and backing b_ikt.
  First differences remove every firm x theme fixed effect (e.g. energy firms always stress safety).
    (A) talk -> walk :  db_ik,t+1  = beta  * dsal_ikt + gamma * db_ikt   + year FE + theme FE
    (B) walk -> talk :  dsal_ik,t+1 = delta * db_ikt  + phi   * dsal_ikt + year FE + theme FE
  Standard errors clustered by firm (CR1). beta > 0 supports aspirational talk; delta > 0 supports
  "talk follows walk". Including the own lag (gamma, phi) absorbs mean reversion.
  Preliminary by construction: ~50 firms x 12 themes x <=7 usable transitions, and backing is
  peer-relative, so these are associations in relative positions, not causal effects.

DEI case
  The 2020 surge and post-2023 retreat of DEI language is a natural stress test. For each firm
  whose stated DEI salience peaked >= 2, we date the first decline after the peak in (i) stated
  DEI salience and (ii) lived DEI backing, and classify the retreat as talk-first, walk-first or
  simultaneous. "Talk-first" = quietly dropping words while practice persists ("DEI-hushing",
  the analogue of greenhushing); "walk-first" = practice erodes behind unchanged rhetoric
  (window-dressing).

Outputs (outputs/part4/): lead_lag_results.csv, dei_retreat.csv, dei_series.png, findings.md
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

from authenticity.config import out_dir


def ols_cluster(y: np.ndarray, X: np.ndarray, clusters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS with cluster-robust (CR1, Stata-style small-sample corrected) standard errors."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    u = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    uniq = np.unique(clusters)
    for c in uniq:
        idx = clusters == c
        sc = X[idx].T @ u[idx]
        meat += np.outer(sc, sc)
    n, k, G = len(y), X.shape[1], len(uniq)
    corr = (G / max(G - 1, 1)) * ((n - 1) / max(n - k, 1))
    V = corr * XtX_inv @ meat @ XtX_inv
    return beta, np.sqrt(np.clip(np.diag(V), 0, None))


def build_panel(long: pd.DataFrame) -> pd.DataFrame:
    p = long.dropna(subset=["salience", "b"]).sort_values(["ticker", "theme", "year"]).copy()
    g = p.groupby(["ticker", "theme"])
    # Only consecutive years count as transitions (gaps break the chain).
    p["consec"] = g.year.diff() == 1
    p["d_sal"] = g.salience.diff().where(p.consec)
    p["d_b"] = g.b.diff().where(p.consec)
    p["d_sal_next"] = g.d_sal.shift(-1)
    p["d_b_next"] = g.d_b.shift(-1)
    return p


def regress(p: pd.DataFrame, y: str, x_main: str, x_own: str) -> dict:
    d = p.dropna(subset=[y, x_main, x_own])
    if len(d) < 30:
        return dict(n=len(d), note="too few transitions")
    fe = pd.get_dummies(d[["year", "theme"]].astype(str), drop_first=True, dtype=float)
    X = np.column_stack([np.ones(len(d)), d[x_main], d[x_own], fe.values])
    b, se = ols_cluster(d[y].values.astype(float), X, d.ticker.values)
    return dict(n=len(d), n_firms=d.ticker.nunique(), coef=round(b[1], 4), se=round(se[1], 4),
                t=round(b[1] / se[1], 2) if se[1] else np.nan,
                own_lag_coef=round(b[2], 4),
                # standardised effect: SD change in outcome per SD change in predictor
                std_effect=round(b[1] * d[x_main].std() / d[y].std(), 3) if d[y].std() else np.nan)


def dei_retreat(long: pd.DataFrame, lived: str = "b") -> pd.DataFrame:
    """lived="b": peer-relative backing; a drop = 0.15 below its peak (percentile scale).
    lived="lived_raw_disc": ABSOLUTE substantive DEI disclosure density; a drop = below 80% of its
    peak. The absolute version matters because b is relative to peers: when every firm cuts DEI
    disclosure at once (as in 2023-24), b barely moves and the retreat would be misread as
    'talk first'."""
    d = long[long.theme == "diversity_inclusion"].dropna(subset=["salience", lived]).copy()
    d["b"] = d[lived]
    rows = []
    for tk, g in d.sort_values("year").groupby("ticker"):
        g = g.set_index("year")
        if g.salience.max() < 2:
            continue
        peak_s = int(g.salience.idxmax())                     # first year at max stated salience
        after = g.loc[g.index > peak_s]
        drop_s = next((y for y in after.index if g.loc[y, "salience"] < g.salience.max()), None)
        peak_b_val = g.loc[g.index >= peak_s - 1, "b"].max()   # lived peak around stated peak
        peak_b = int(g.loc[g.index >= peak_s - 1, "b"].idxmax())
        thresh = peak_b_val - 0.15 if lived == "b" else 0.8 * peak_b_val
        drop_b = next((y for y in g.index if y > peak_b and g.loc[y, "b"] < thresh), None)
        if drop_s is None and drop_b is None:
            kind = "no_retreat"
        elif drop_b is None:
            kind = "talk_first"
        elif drop_s is None:
            kind = "walk_first"
        else:
            kind = "talk_first" if drop_s < drop_b else "walk_first" if drop_b < drop_s else "simultaneous"
        rows.append(dict(ticker=tk, sector=g.sector.iloc[0], stated_peak_year=peak_s,
                         stated_first_decline=drop_s, lived_peak_year=peak_b,
                         lived_first_decline=drop_b, retreat_pattern=kind))
    return pd.DataFrame(rows)


def main():
    long = pd.read_csv(out_dir("part3") / "oai_theme_long.csv")
    od = out_dir("part4")
    p = build_panel(long)
    res = pd.DataFrame([
        dict(model="A: talk -> walk (d_backing[t+1] ~ d_salience[t])",
             **regress(p, "d_b_next", "d_sal", "d_b")),
        dict(model="B: walk -> talk (d_salience[t+1] ~ d_backing[t])",
             **regress(p, "d_sal_next", "d_b", "d_sal")),
    ])
    # Heterogeneity: do "hot-button" themes (DEI, climate) behave differently from core values?
    hot = p.theme.isin(["diversity_inclusion", "environment_climate"])
    for lab, sub in (("hot-button themes only", p[hot]), ("other themes", p[~hot])):
        res = pd.concat([res, pd.DataFrame([
            dict(model=f"A [{lab}]", **regress(sub, "d_b_next", "d_sal", "d_b")),
            dict(model=f"B [{lab}]", **regress(sub, "d_sal_next", "d_b", "d_sal"))])], ignore_index=True)
    res.to_csv(od / "lead_lag_results.csv", index=False)

    dr = dei_retreat(long)
    dr.to_csv(od / "dei_retreat.csv", index=False)
    has_abs = "lived_raw_disc" in long and long.lived_raw_disc.notna().any()
    dr_abs = dei_retreat(long, "lived_raw_disc") if has_abs else pd.DataFrame()
    if len(dr_abs):
        dr_abs.to_csv(od / "dei_retreat_absolute.csv", index=False)

    def sign_test(dr_: pd.DataFrame) -> str:
        """Two-sided exact binomial test of talk-first vs walk-first (ties and no-retreat dropped)."""
        from math import comb
        k = int((dr_.retreat_pattern == "talk_first").sum())
        n = k + int((dr_.retreat_pattern == "walk_first").sum())
        if n == 0:
            return "n/a"
        tail = sum(comb(n, i) for i in range(max(k, n - k), n + 1)) / 2 ** n
        return f"talk-first {k} vs walk-first {n - k}: two-sided exact binomial p = {min(1, 2 * tail):.3f}"

    dei = long[long.theme == "diversity_inclusion"].dropna(subset=["salience"])
    if len(dei):
        ser = dei.groupby("year").agg(stated_salience=("salience", "mean"),
                                      raw_disclosure=("lived_raw_disc", "mean"),
                                      firms_with_dei_pay=("lived_raw_pay", lambda x: (x > 0).mean()))
        # Each series indexed to its own peak (= 100): the three are on different scales, and
        # the question is WHEN each peaks and declines, not their levels.
        idx = ser / ser.max().replace(0, np.nan) * 100
        fig, ax = plt.subplots(figsize=(7, 4))
        for c, lab in [("stated_salience", "Stated DEI salience (About pages)"),
                       ("raw_disclosure", "Substantive DEI disclosure (proxies)"),
                       ("firms_with_dei_pay", "Share of firms paying on DEI metrics")]:
            ax.plot(idx.index, idx[c], marker="o", label=lab)
        ax.axhline(100, color="grey", lw=0.8)
        ax.set_ylabel("Index, series peak = 100")
        ax.set_title("DEI: talk vs. walk, 2016-2024")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(od / "dei_series.png", dpi=160)
        plt.close(fig)
    else:
        idx = pd.DataFrame()

    lines = ["# Part 4 findings (auto-generated - interpret in SUMMARY.md)\n",
             "## Lead-lag regressions (first differences, year+theme FE, firm-clustered SE)\n",
             res.to_markdown(index=False),
             "\n## DEI retreat sequencing (firms whose stated DEI salience peaked >= 2)\n",
             "Lived side = peer-relative backing (drop = 0.15 below peak):\n",
             dr.retreat_pattern.value_counts().to_markdown() if len(dr) else "(none)",
             "\n" + (sign_test(dr) if len(dr) else ""),
             "\nRobustness - lived side = ABSOLUTE substantive DEI disclosure (drop = below 80% of peak):\n",
             dr_abs.retreat_pattern.value_counts().to_markdown() if len(dr_abs) else "(n/a)",
             "\n" + (sign_test(dr_abs) if len(dr_abs) else ""),
             "\n## DEI series (index, each series' peak = 100)\n", idx.round(1).to_markdown() if len(idx) else ""]
    (od / "findings.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
