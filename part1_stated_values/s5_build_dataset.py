"""Part 1, step 5 - Assemble the deliverable dataset, coverage report, figures and digest.

Output (outputs/part1/):
  stated_values.csv     one row per company-year (all 450, including gaps) - required columns
                        [ticker, company_name, sector, year, page_text_clean, changed_from_prior,
                         theme_categories, analyst_notes] plus provenance and coding columns
  coverage_report.csv   per company: years captured, years missing and why
  theme_prevalence.png  share of firms stating each theme (salience>=2), by year
  digest.md             auto-generated key numbers to paste into SUMMARY.md
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
from authenticity.textutils import linguistic_features
from authenticity.themes import taxonomy, theme_ids

TIDS = theme_ids()


def read(name: str) -> pd.DataFrame:
    p = interim_dir("part1") / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["ticker", "year"])


def analyst_note(r: pd.Series) -> str:
    """Row-level notes: provenance caveats first (they condition every other column), then the
    LLM's change description and linguistic shifts."""
    notes = []
    if r.status != "ok":
        return f"MISSING: {r.missing_reason}. No snapshot satisfied the selection rules."
    if str(r.get("url_switched")) == "True":
        notes.append(f"Fallback URL used ({r.page_url}); comparisons with adjacent years may reflect a page switch.")
    if r.get("n_redirects", 0) and r.n_redirects > 0:
        notes.append(f"Reached via {int(r.n_redirects)} redirect(s).")
    if r.get("quality_flag") not in ("ok", None) and pd.notna(r.get("quality_flag")):
        notes.append(f"Text quality: {r.quality_flag}.")
    if r.get("page_type") == "not_an_about_page":
        notes.append("LLM judged this is not an About/values page - treat codes with caution.")
    if pd.notna(r.get("gap_years")) and r.gap_years > 1:
        notes.append(f"Compared with {int(r.prior_year_compared)} (intervening year missing).")
    if pd.isna(r.get("change_type")):
        notes.append("First usable snapshot for this firm - no prior year to compare.")
    elif r.change_type == "none":
        notes.append(f"Text unchanged from {int(r.prior_year_compared)} (similarity {r.similarity_prior:.2f}).")
    else:
        notes.append(f"Change vs {int(r.prior_year_compared)} ({r.change_type}, similarity "
                     f"{r.similarity_prior:.2f}): {r.change_description}")
    if isinstance(r.get("linguistic_shifts"), str) and r.linguistic_shifts:
        notes.append(f"Shifts: {r.linguistic_shifts}")
    return " ".join(notes)


def main():
    cos = load_companies()[["ticker", "company_name", "sector"]]
    grid = cos.merge(pd.DataFrame({"year": YEARS}), how="cross")
    man = read("snapshot_manifest.csv")
    texts = read("texts.csv")
    codes = read("llm_themes.csv")
    chg = read("llm_changes.csv")

    df = (grid.merge(man, on=["ticker", "year"], how="left")
              .merge(texts, on=["ticker", "year"], how="left")
              .merge(codes, on=["ticker", "year"], how="left")
              .merge(chg, on=["ticker", "year"], how="left"))
    df["status"] = df["status"].fillna("missing")
    df["missing_reason"] = df["missing_reason"].fillna("not_attempted")
    df["page_text_clean"] = df["text"]

    # changed_from_prior: True/False when a prior snapshot exists; NA for the first available
    # year of each firm and for missing years. Text-level change and substantive change are
    # separated because most edits are cosmetic.
    df["changed_from_prior"] = df["changed_from_prior"].astype("boolean")
    df["substantive_change"] = df["change_type"].isin(
        ["minor_substantive", "major_rewrite", "page_replaced"]).astype("boolean")
    df.loc[df["change_type"].isna(), "substantive_change"] = pd.NA

    # theme_categories: themes with salience >= 2 (clearly present), ordered by salience
    def cats(r):
        if pd.isna(r.get("sal_integrity_ethics")):
            return pd.NA
        s = sorted(((r[f"sal_{t}"], t) for t in TIDS if r[f"sal_{t}"] >= 2), reverse=True)
        return ";".join(t for _, t in s)
    df["theme_categories"] = df.apply(cats, axis=1)

    feats = df["page_text_clean"].fillna("").apply(
        lambda t: linguistic_features(t) if t else {})
    feat_df = pd.DataFrame(list(feats)).add_prefix("ling_")
    df = pd.concat([df.reset_index(drop=True), feat_df], axis=1)
    df["analyst_notes"] = df.apply(analyst_note, axis=1)

    # Index eligibility (used by Part 3). A row is kept unless:
    #  - there is no coded text (missing snapshot, unusable text, LLM failure);
    #  - the LLM judged it not an About page AND it states no theme at salience >= 2
    #    (navigation menus, error pages, ads): nothing to compare against conduct;
    #  - the firm has no real About page at all (>= 2/3 of its coded years judged
    #    not_an_about_page, e.g. Apple's navigation hub, Berkshire's static homepage).
    # About pages that ARE the company's page but say little about values (timelines, promo
    # copy) stay in: "says little about values" is a legitimate observation, not missing data.
    sal_cols = [f"sal_{t}" for t in TIDS]
    coded = df["sal_integrity_ethics"].notna() if "sal_integrity_ethics" in df else pd.Series(False, index=df.index)
    not_about = df.get("page_type", pd.Series(index=df.index, dtype=object)) == "not_an_about_page"
    n_strong = (df[sal_cols] >= 2).sum(axis=1) if coded.any() else 0
    share_not_about = (not_about & coded).groupby(df.ticker).transform("sum") / \
        coded.groupby(df.ticker).transform("sum").replace(0, np.nan)
    reason = pd.Series("", index=df.index)
    reason[~coded] = "no_coded_text"
    reason[coded & not_about & (n_strong == 0)] = "page_states_no_values"
    reason[coded & (share_not_about >= 2 / 3)] = "firm_has_no_about_page"
    df["index_exclusion_reason"] = reason
    df["index_eligible"] = reason == ""

    required = ["ticker", "company_name", "sector", "year", "page_text_clean", "changed_from_prior",
                "theme_categories", "analyst_notes"]
    extra = ["status", "missing_reason", "page_url", "capture_ts", "final_url", "url_switched",
             "n_redirects", "redirect_chain", "extraction_method", "n_words", "quality_flag",
             "page_type", "similarity_prior", "prior_year_compared", "change_type",
             "substantive_change", "themes_gained", "themes_lost", "linguistic_shifts",
             "primary_stakeholder", "framing", "register", "llm_summary", "evidence",
             "index_eligible", "index_exclusion_reason"] + \
            [f"sal_{t}" for t in TIDS] + list(feat_df.columns)
    extra = [c for c in extra if c in df.columns]
    od = out_dir("part1")
    df[required + extra].sort_values(["ticker", "year"]).to_csv(od / "stated_values.csv", index=False)

    # Coverage report -----------------------------------------------------------
    cov = (df.groupby(["ticker", "company_name", "sector"])
             .apply(lambda g: pd.Series({
                 "years_ok": int((g.status == "ok").sum()),
                 "years_usable_text": int(g.quality_flag.isin(["ok", "thin"]).sum()),
                 "missing_years": ";".join(f"{y}({r})" for y, r, s in
                                           zip(g.year, g.missing_reason, g.status) if s != "ok"),
                 "n_url_switches": int((g.url_switched.astype(str) == "True").sum()),
                 "bad_quality_years": ";".join(f"{y}({q})" for y, q in zip(g.year, g.quality_flag)
                                               if isinstance(q, str) and q not in ("ok",))}),
                    include_groups=False)
             .reset_index())
    cov.to_csv(od / "coverage_report.csv", index=False)

    # Figure: theme prevalence by year ---------------------------------------------
    coded = df.dropna(subset=["sal_integrity_ethics"])
    if len(coded):
        prev = pd.DataFrame({t: coded.groupby("year")[f"sal_{t}"].apply(lambda s: (s >= 2).mean())
                             for t in TIDS})
        fig, ax = plt.subplots(figsize=(10, 5))
        im = ax.imshow(prev.T.values, aspect="auto", cmap="Blues", vmin=0, vmax=1)
        ax.set_yticks(range(len(TIDS)), [taxonomy()["themes"][t]["label"] for t in TIDS])
        ax.set_xticks(range(len(prev.index)), prev.index)
        for i in range(len(TIDS)):
            for j in range(len(prev.index)):
                v = prev.T.values[i, j]
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7,
                        color="white" if v > 0.6 else "black")
        ax.set_title("Share of firms whose About page clearly states each theme (salience ≥ 2)")
        fig.colorbar(im, ax=ax, fraction=0.025)
        fig.tight_layout()
        fig.savefig(od / "theme_prevalence.png", dpi=160)
        plt.close(fig)

    # Digest -----------------------------------------------------------------------
    ok = df.status == "ok"
    usable_t = df.quality_flag.isin(["ok", "thin"])
    lines = ["# Part 1 digest (auto-generated - numbers for SUMMARY.md)\n",
             f"- Company-years attempted: {len(df)}; snapshot found: {ok.sum()} ({ok.mean():.0%}); "
             f"usable text: {usable_t.sum()} ({usable_t.mean():.0%})",
             f"- Missing reasons: {df.loc[~ok, 'missing_reason'].value_counts().to_dict()}",
             f"- Quality flags: {df.quality_flag.value_counts().to_dict()}",
             f"- Firms with a URL switch in at least one year: {(cov.n_url_switches > 0).sum()}",
             f"- Index-eligible firm-years: {int(df.index_eligible.sum())}; exclusions: "
             f"{df.loc[~df.index_eligible, 'index_exclusion_reason'].value_counts().to_dict()}"]
    if df.changed_from_prior.notna().any():
        by_year = df.groupby("year")[["changed_from_prior", "substantive_change"]].mean().round(2)
        lines += ["\n## Change rates by year (share of firms with a comparable prior snapshot)\n",
                  by_year.to_markdown()]
        # Finer breakdown. "substantive_change" includes minor rewording; the headline measure of
        # a real change in stated values is a major rewrite or page replacement on the SAME URL
        # (a fallback-URL switch can masquerade as a rewrite).
        sw = df.url_switched.astype(str) == "True"
        same_url = ~sw & ~sw.groupby(df.ticker).shift(1, fill_value=False)
        ct = df[df.change_type.notna()]
        lines += ["\n## Change type by year (counts)\n",
                  pd.crosstab(ct.year, ct.change_type).to_markdown()]
        major = df.change_type.isin(["major_rewrite", "page_replaced"]) & same_url
        comparable = df.change_type.notna() & same_url
        lines += ["\n## Headline: share of firms with a major rewrite on the same URL, by year\n",
                  (major[comparable].groupby(df.year[comparable]).mean().round(2)
                   .rename("major_change_rate").to_frame().to_markdown()),
                  f"\nOverall: {major[comparable].mean():.0%} of {int(comparable.sum())} "
                  f"same-URL year-pairs."]
    if len(coded):
        lines += ["\n## Theme prevalence (salience>=2) by sector, all years\n",
                  pd.DataFrame({t: coded.groupby("sector")[f"sal_{t}"].apply(lambda s: (s >= 2).mean())
                                for t in TIDS}).round(2).T.to_markdown(),
                  "\n## Theme prevalence by year\n", prev.round(2).T.to_markdown()]
    traj = read("llm_trajectories.csv")
    if len(traj) and "pattern" in traj:
        lines += ["\n## Trajectory patterns\n", traj.pattern.value_counts().to_markdown()]
    (od / "digest.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {od}/stated_values.csv ({len(df)} rows), coverage_report.csv, digest.md")


if __name__ == "__main__":
    main()
