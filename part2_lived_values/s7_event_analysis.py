"""Part 2, step 7 - Do shifts in disclosure coincide with external events?

Input : outputs/part2/lived_values.csv, config/events.yaml
Output: outputs/part2/event_shifts.csv, outputs/part2/event_digest.md

Design: within-firm before/after comparison around each event.
  For each event E with first affected proxy year F (event mid-year E -> proxies filed F=E+1),
  each firm i and each outcome Y (theme density, substantive density, pay weight):
      pre_i  = mean of Y over filing years F-3 .. F-1
      post_i = mean of Y over filing years F   .. F+2      (truncated to 2016-2024)
      shift_i = post_i - pre_i       (firm fixed effect differenced out)
  We report the mean shift, a firm-bootstrap 95% CI, the share of firms that increased, and the
  same statistics for a PLACEBO event dated two years earlier. A real event effect should exceed
  the placebo (which captures pre-existing trend); this guards against reading a smooth secular
  trend as an event response. This is descriptive coincidence, not causal identification - many
  events cluster in 2020-21 and cannot be separated with annual data.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from authenticity.config import YEARS, load_yaml, out_dir

OUTCOMES = {"dens": "theme density", "subst_dens": "substantive density", "pay_w": "pay weight"}


def shift_stats(df: pd.DataFrame, col: str, F: int, n_boot: int = 2000, seed: int = 0) -> dict:
    pre_years = [y for y in range(F - 3, F) if y in YEARS]
    post_years = [y for y in range(F, F + 3) if y in YEARS]
    if not pre_years or not post_years or col not in df:
        return {}
    w = df.pivot_table(index="ticker", columns="year", values=col)
    pre = w.reindex(columns=pre_years).mean(axis=1)
    post = w.reindex(columns=post_years).mean(axis=1)
    d = (post - pre).dropna()
    if len(d) < 3:
        return {}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(d.values, len(d), replace=True).mean() for _ in range(n_boot)]
    base = pre[d.index].mean()
    return dict(n_firms=len(d), pre_mean=round(base, 4), mean_shift=round(d.mean(), 4),
                pct_change=round(d.mean() / base, 3) if base else np.nan,
                ci_low=round(np.percentile(boots, 2.5), 4), ci_high=round(np.percentile(boots, 97.5), 4),
                share_increasing=round((d > 0).mean(), 2))


def main():
    df = pd.read_csv(out_dir("part2") / "lived_values.csv")
    df = df[df.status == "ok"]
    rows = []
    for ev in load_yaml("events.yaml")["market_events"]:
        F = ev["first_proxy_year"]
        for theme in ev["themes"]:
            for pre, label in OUTCOMES.items():
                col = f"{pre}_{theme}"
                for kind, year in (("event", F), ("placebo_minus2", F - 2)):
                    s = shift_stats(df, col, year)
                    if s:
                        rows.append(dict(event=ev["id"], first_proxy_year=F, theme=theme,
                                         outcome=label, test=kind, **s))
                # sector breakdown for the real event only
                for sec, g in df.groupby("sector"):
                    s = shift_stats(g, col, F, n_boot=500)
                    if s:
                        rows.append(dict(event=ev["id"], first_proxy_year=F, theme=theme,
                                         outcome=label, test=f"event|{sec}", **s))
    res = pd.DataFrame(rows)
    res.to_csv(out_dir("part2") / "event_shifts.csv", index=False)
    if len(res):
        main_tbl = res[res.test.isin(["event", "placebo_minus2"])]
        print(main_tbl.to_string(index=False))
        (out_dir("part2") / "event_digest.md").write_text(
            "# Event-window shifts (event vs placebo two years earlier)\n\n"
            + main_tbl.to_markdown(index=False), encoding="utf-8")


if __name__ == "__main__":
    main()
