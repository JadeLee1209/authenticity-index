"""Part 3 - Validity and robustness checks for the OAI.

1. DISCRIMINANT / PERMUTATION TEST  (main validity check)
   If OAI measures how well a firm's OWN conduct backs its OWN words, then a firm's stated profile
   should be better backed by its own proxy than by a randomly chosen peer's proxy. We shuffle the
   lived side across firms within each year (and, as a harder test, within sector-year), recompute
   mean OAI 1,000 times, and report where the true mean falls. If the true mean is no higher than
   shuffled means, OAI mostly reflects generic disclosure levels, not firm-specific alignment.

2. KNOWN-GROUPS  (face validity, config/events.yaml firm_events)
   Firms with well-documented say-do controversies (e.g. Wells Fargo 2016-18 on integrity/customer)
   should show LOW backing on the implicated themes relative to (a) sector peers in the same years
   and (b) their own other years. Reported transparently, hit or miss.

3. ROBUSTNESS  rank correlation of the main OAI with variants: disclosure-only, pay-only,
   sector peers, one-year lag, no imputation.

4. CONVERGENT (optional)  if data/external/esg_scores.csv exists with columns ticker,year,score
   (e.g. an MSCI/Refinitiv/Sustainalytics score from WRDS), correlate. A moderate positive
   correlation is expected - ESG ratings measure performance, not alignment, so a very high
   correlation would actually be a warning that OAI is just an ESG proxy.

Output: outputs/part3/validity.md, validity_permutation.csv, validity_known_groups.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from authenticity.config import DATA_DIR, load_yaml, out_dir

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import compute  # noqa: E402


def mean_oai(long: pd.DataFrame) -> float:
    g = long.dropna(subset=["s_share", "b"]).assign(c=lambda d: d.s_share * d.b)
    return 100 * g.groupby(["ticker", "year"]).c.sum().mean()


def permutation_test(long: pd.DataFrame, within: list[str], n: int = 1000, seed: int = 1) -> dict:
    """Shuffle the lived side (theme vector b of firm j) across firms within `within` cells."""
    rng = np.random.default_rng(seed)
    base = long.dropna(subset=["s_share", "b"])
    keys = base[["ticker", "year", "sector"]].drop_duplicates()
    bwide = base.pivot_table(index=["ticker", "year"], columns="theme", values="b")
    swide = base.pivot_table(index=["ticker", "year"], columns="theme", values="s_share")
    swide = swide.loc[bwide.index]
    true = 100 * (swide * bwide).sum(axis=1).mean()
    cells = keys.set_index(["ticker", "year"]).loc[bwide.index].reset_index()
    groups = cells.groupby(within).indices
    null = []
    for _ in range(n):
        perm = np.arange(len(cells))
        for idx in groups.values():
            perm[idx] = rng.permutation(idx)
        null.append(100 * (swide.values * bwide.values[perm]).sum(axis=1).mean())
    null = np.array(null)
    return dict(shuffle_within="+".join(within), true_mean_oai=round(true, 2),
                null_mean=round(null.mean(), 2), null_sd=round(null.std(), 3),
                z=round((true - null.mean()) / null.std(), 2) if null.std() else np.nan,
                p_one_sided=round(((null >= true).sum() + 1) / (n + 1), 4))


def known_groups(long: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ev in load_yaml("events.yaml").get("firm_events", []):
        for theme in ev["themes"]:
            t = long[long.theme == theme].dropna(subset=["b"])
            firm = t[t.ticker == ev["ticker"]]
            if firm.empty:
                continue
            sector = firm.sector.iloc[0]
            in_win = firm[firm.year.isin(ev["years"])]
            out_win = firm[~firm.year.isin(ev["years"])]
            peers = t[(t.sector == sector) & (t.ticker != ev["ticker"]) & t.year.isin(ev["years"])]
            b_ev, b_peer, b_own = in_win.b.mean(), peers.b.mean(), out_win.b.mean()
            sal = in_win.salience.mean()
            low = ev["expectation"] == "low"
            met_peer = (b_ev < b_peer) if low else (b_ev > b_peer)
            met_own = (b_ev < b_own) if low else (b_ev > b_own)
            rows.append(dict(ticker=ev["ticker"], theme=theme, years=f"{min(ev['years'])}-{max(ev['years'])}",
                             expectation=ev["expectation"], stated_salience=round(sal, 2),
                             backing_event=round(b_ev, 3), backing_sector_peers=round(b_peer, 3),
                             backing_own_other_years=round(b_own, 3) if pd.notna(b_own) else np.nan,
                             met_vs_peers=bool(met_peer) if pd.notna(b_ev) and pd.notna(b_peer) else None,
                             met_vs_own_history=bool(met_own) if pd.notna(b_ev) and pd.notna(b_own) else None,
                             description=ev["description"]))
    return pd.DataFrame(rows)


def robustness(main_fy: pd.DataFrame) -> pd.DataFrame:
    variants = {"disclosure_only": dict(w_disc=1.0), "pay_only": dict(w_disc=0.0),
                "sector_peers": dict(peer="sector"), "lag_1": dict(lag=1),
                "no_imputation": dict(carry_forward=0)}
    base = main_fy.set_index(["ticker", "year"]).oai
    rows = []
    for name, kw in variants.items():
        fy, _ = compute(**kw)
        v = fy.set_index(["ticker", "year"]).oai
        j = pd.concat([base, v], axis=1, keys=["main", "variant"]).dropna()
        rows.append(dict(variant=name, n=len(j),
                         spearman_firm_year=round(j.main.corr(j.variant, method="spearman"), 3),
                         spearman_firm_mean=round(j.groupby(level=0).mean().pipe(
                             lambda d: d.main.corr(d.variant, method="spearman")), 3)))
    return pd.DataFrame(rows)


def main():
    fy, long = compute()
    od = out_dir("part3")
    perm = pd.DataFrame([permutation_test(long, ["year"]),
                         permutation_test(long, ["year", "sector"])])
    perm.to_csv(od / "validity_permutation.csv", index=False)
    kg = known_groups(long)
    kg.to_csv(od / "validity_known_groups.csv", index=False)
    rob = robustness(fy)
    rob.to_csv(od / "validity_robustness.csv", index=False)

    lines = ["# OAI validity checks (auto-generated)\n",
             "## 1. Permutation test (own proxy vs. a random peer's proxy)\n", perm.to_markdown(index=False),
             "\nInterpretation: z > 2 and small p mean firms' words are backed by their OWN disclosures more "
             "than by peers' - OAI captures firm-specific alignment rather than generic disclosure volume.",
             "\n## 2. Known groups\n", kg.drop(columns="description").to_markdown(index=False) if len(kg) else "(no matching firm-years)",
             "\n## 3. Robustness: rank correlation with variants\n", rob.to_markdown(index=False)]
    ext = DATA_DIR / "external" / "esg_scores.csv"
    if ext.exists():
        e = pd.read_csv(ext)
        j = fy.merge(e, on=["ticker", "year"]).dropna(subset=["oai", "score"])
        lines += ["\n## 4. Convergent: correlation with external ESG score\n",
                  f"n={len(j)}, Spearman={j.oai.corr(j.score, method='spearman'):.2f}"]
    (od / "validity.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
