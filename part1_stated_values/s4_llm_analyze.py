"""Part 1, step 4 - LLM analysis of each snapshot: (a) change vs prior year, (b) value themes,
(c) linguistic shifts over time.

Input : data/interim/part1/texts.csv
Output: data/interim/part1/llm_themes.csv        one row per company-year (theme salience etc.)
        data/interim/part1/llm_changes.csv       one row per company-year with a prior snapshot
        data/interim/part1/llm_trajectories.csv  one row per company (2016-2024 narrative)
        outputs/part1/llm_reliability.csv        (with --reliability N) agreement diagnostics

Pipeline design (why it looks like this)
  (a) CHANGE. A cheap deterministic gate first: text similarity (avg. of word-level sequence ratio
      and 5-shingle Jaccard) >= 0.98 => unchanged, no LLM call. Below that the LLM sees BOTH texts
      plus a sentence-level diff and classifies the change as cosmetic / minor_substantive /
      major_rewrite / page_replaced. This separates "the page changed" (any text edit - often
      layout, dates, CMS migrations) from "the stated values changed", which is what matters.
  (b) THEMES. Each snapshot is coded independently (no peeking at other years, so codes are not
      anchored on history) for salience 0-3 on the 12 shared themes in config/themes.yaml, plus
      page type (to catch wrong pages), primary stakeholder, framing and register.
  (c) SHIFTS. Per-pair linguistic shifts come from (a); a stronger model then reads the whole
      2016-2024 sequence of codes and change notes per company and writes the trajectory.
  All calls use forced tool use (schema-valid JSON), a disk cache, and temperature 0 where the
  SDK/model accepts it (otherwise the provider default - hence the reliability check).
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from authenticity.config import interim_dir, load_companies, out_dir
from authenticity.llm import LLM, MODEL_STRONG, parallel_map
from authenticity.textutils import diff_summary, text_similarity, words
from authenticity.themes import (salience_scale_block, theme_hits, theme_ids,
                                 themes_prompt_block)

UNCHANGED_SIM = 0.98
MAX_WORDS = 3000
TIDS = theme_ids()

PAGE_TYPES = ["values_or_principles", "mission_or_purpose", "about_overview",
              "business_description", "not_an_about_page"]
STAKEHOLDERS = ["customers", "employees", "shareholders", "communities_society", "planet",
                "multiple_balanced", "none_explicit"]
FRAMINGS = ["purpose_driven", "values_list", "performance_driven", "heritage_history",
            "business_description", "mixed"]
CHANGE_TYPES = ["cosmetic", "minor_substantive", "major_rewrite", "page_replaced"]


def _int03(x) -> int:
    """Coerce an LLM salience value to an int in 0..3 (tolerates "2", 2.0, None)."""
    try:
        return max(0, min(3, int(round(float(x)))))
    except (TypeError, ValueError):
        return 0


def truncate(t: str, n: int = MAX_WORDS) -> str:
    w = t.split()
    return t if len(w) <= n else " ".join(w[:n]) + " [...truncated]"


# ============================================================== (b) theme coding
THEME_SYSTEM = f"""You are a careful research coder for an academic study of corporate values.
You read the visible text of a company's archived "About us" / mission / values web page and
code which value themes it expresses.

THEMES (code every one):
{themes_prompt_block()}

SALIENCE SCALE:
{salience_scale_block()}

RULES
- Code only what THIS text says. Do not use outside knowledge of the company.
- A theme counts when the company presents it as something it values, stands for or commits to;
  incidental words (e.g. "customers" in a product description) are at most 1.
- Ignore leftover navigation, legal or cookie text.
- Evidence: for every theme with salience >= 2 give a short verbatim phrase (<= 12 words).
- If the text is not an About/mission/values page (error page, product page, login wall),
  set page_type = not_an_about_page and code themes from whatever text exists."""

THEME_ALT_SYSTEM = THEME_SYSTEM.replace(
    "You are a careful research coder for an academic study of corporate values.",
    "Act as an independent second coder in a content-analysis project on how firms describe "
    "their values.")  # paraphrased prompt for test-retest reliability

THEME_SCHEMA = {
    "type": "object",
    "properties": {
        "page_type": {"type": "string", "enum": PAGE_TYPES},
        "salience": {"type": "object",
                     "properties": {t: {"type": "integer", "minimum": 0, "maximum": 3} for t in TIDS},
                     "required": TIDS},
        "evidence": {"type": "object", "properties": {t: {"type": "string"} for t in TIDS},
                     "description": "verbatim phrase for themes with salience>=2 (omit others)"},
        "primary_stakeholder": {"type": "string", "enum": STAKEHOLDERS},
        "framing": {"type": "string", "enum": FRAMINGS},
        "register": {"type": "string", "enum": ["aspirational", "operational", "mixed"],
                     "description": "aspirational = ideals/beliefs; operational = concrete activities, facts, numbers"},
        "summary": {"type": "string", "description": "one sentence: what the page says the company values"},
    },
    "required": ["page_type", "salience", "primary_stakeholder", "framing", "register", "summary"],
}


def mock_themes(text: str) -> dict:
    """Dictionary stand-in: keyword hits mapped onto the 0-3 scale."""
    h = theme_hits(text)
    sal = {t: (0 if c == 0 else 1 if c == 1 else 2 if c <= 3 else 3) for t, c in h.items()}
    return {"page_type": "about_overview", "salience": sal, "evidence": {},
            "primary_stakeholder": "multiple_balanced", "framing": "mixed", "register": "mixed",
            "summary": "mock coding (keyword dictionary)"}


def code_themes(llm: LLM, row: dict, alt: bool = False) -> dict:
    user = (f"Company page text ({row['n_words']} words, archived {row['year']}):\n"
            f"<page>\n{truncate(row['text'])}\n</page>")
    return llm.call_tool(system=THEME_ALT_SYSTEM if alt else THEME_SYSTEM, user=user,
                         tool_name="record_value_themes",
                         tool_description="Record the value-theme coding for one page.",
                         schema=THEME_SCHEMA, mock=lambda: mock_themes(row["text"]),
                         cache_tag="alt" if alt else "")


# ============================================================== (a) change analysis
CHANGE_SYSTEM = f"""You compare two archived versions of the same company's About/values web page
(an earlier and a later year) for a study of how corporate stated values evolve.

Classify the change:
- cosmetic: layout, dates, links, typos, reordering, CMS migration; stated values unchanged
- minor_substantive: some wording about what the company values/stands for was added, removed or reworded
- major_rewrite: the values message was substantially rewritten
- page_replaced: the later text is effectively a different page (different purpose/content)

Then list concrete LINGUISTIC SHIFTS, each phrased "from <earlier wording/emphasis> to <later>"
(e.g. "from 'shareholder value' to 'all stakeholders'", "from lists of values to purpose statement",
"adds DEI language: 'belonging', 'equity'"). Report themes gained/lost using these ids:
{', '.join(TIDS)}"""

CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "change_type": {"type": "string", "enum": CHANGE_TYPES},
        "description": {"type": "string", "description": "one or two sentences"},
        "linguistic_shifts": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "themes_gained": {"type": "array", "items": {"type": "string", "enum": TIDS}},
        "themes_lost": {"type": "array", "items": {"type": "string", "enum": TIDS}},
    },
    "required": ["change_type", "description", "linguistic_shifts", "themes_gained", "themes_lost"],
}


def mock_change(prev: str, cur: str, sim: float) -> dict:
    hp, hc = theme_hits(prev), theme_hits(cur)
    return {"change_type": "major_rewrite" if sim < 0.5 else "minor_substantive" if sim < 0.9
            else "cosmetic",
            "description": f"mock: similarity {sim:.2f}", "linguistic_shifts": [],
            "themes_gained": [t for t in TIDS if hp[t] == 0 and hc[t] > 1],
            "themes_lost": [t for t in TIDS if hp[t] > 1 and hc[t] == 0]}


def analyze_change(llm: LLM, prev: dict, cur: dict, sim: float) -> dict:
    user = (f"EARLIER ({prev['year']}):\n<earlier>\n{truncate(prev['text'], 1500)}\n</earlier>\n\n"
            f"LATER ({cur['year']}):\n<later>\n{truncate(cur['text'], 1500)}\n</later>\n\n"
            f"Sentence-level diff (- removed, + added):\n<diff>\n{diff_summary(prev['text'], cur['text'])}\n</diff>")
    return llm.call_tool(system=CHANGE_SYSTEM, user=user, tool_name="record_page_change",
                         tool_description="Record how the page changed between two years.",
                         schema=CHANGE_SCHEMA, mock=lambda: mock_change(prev["text"], cur["text"], sim))


# ============================================================== (c) trajectory synthesis
TRAJ_SYSTEM = """You are writing analyst notes for a study of how large US firms' stated values
evolved 2016-2024. You receive year-by-year structured codes (theme salience 0-3, framing,
stakeholder emphasis, register) and change notes for ONE company's About/values page.
Describe the trajectory precisely, citing years. Distinguish genuine shifts in stated values from
artefacts (page switches, thin captures, missing years) which are flagged in the input."""

TRAJ_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "enum": ["stable", "incremental", "punctuated", "volatile",
                                               "insufficient_data"]},
        "trajectory_summary": {"type": "string", "description": "3-5 sentences"},
        "notable_shifts": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"years": {"type": "string"}, "shift": {"type": "string"}},
            "required": ["years", "shift"]}},
        "data_caveats": {"type": "string"},
    },
    "required": ["pattern", "trajectory_summary", "notable_shifts", "data_caveats"],
}


def synthesize(llm: LLM, ticker: str, name: str, table: str) -> dict:
    return llm.call_tool(
        system=TRAJ_SYSTEM, user=f"Company: {name} ({ticker})\n\n{table}",
        tool_name="record_trajectory", tool_description="Record the company's 2016-2024 trajectory.",
        schema=TRAJ_SCHEMA, max_tokens=1500,
        mock=lambda: {"pattern": "insufficient_data", "trajectory_summary": "mock",
                      "notable_shifts": [], "data_caveats": "mock backend"})


# ============================================================== reliability
def weighted_kappa(a, b, k: int = 4) -> float:
    """Quadratic-weighted Cohen's kappa for ordinal 0..k-1 codes."""
    a, b = np.asarray(a, int), np.asarray(b, int)
    if len(a) == 0:
        return float("nan")
    O = np.zeros((k, k))
    for i, j in zip(a, b):
        O[i, j] += 1
    W = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    den = (W * E).sum()
    return float(1 - (W * O).sum() / den) if den else float("nan")


def reliability(llm: LLM, texts: pd.DataFrame, codes: pd.DataFrame, n: int) -> pd.DataFrame:
    sample = texts.sample(min(n, len(texts)), random_state=7).to_dict("records")
    alt = parallel_map(lambda r: code_themes(llm, r, alt=True), sample, desc="reliability")
    base = codes.set_index(["ticker", "year"])
    rows = []
    for t in TIDS:
        a = [base.loc[(r["ticker"], r["year"]), f"sal_{t}"] for r in sample]
        b = [x["salience"][t] if "salience" in x else 0 for x in alt]
        dens = [theme_hits(r["text"])[t] / max(1, r["n_words"]) for r in sample]
        rows.append(dict(theme=t, n=len(a), exact_agreement=float(np.mean(np.equal(a, b))),
                         weighted_kappa=weighted_kappa(a, b),
                         # convergent validity: LLM salience vs. keyword density
                         spearman_vs_dictionary=pd.Series(a).corr(pd.Series(dens), method="spearman")))
    return pd.DataFrame(rows)


# ============================================================== main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reliability", type=int, default=0,
                    help="re-code N random snapshots with a paraphrased prompt and report agreement")
    ap.add_argument("--skip-trajectories", action="store_true")
    args = ap.parse_args(argv)

    texts = pd.read_csv(interim_dir("part1") / "texts.csv").fillna({"text": ""})
    texts = texts.sort_values(["ticker", "year"]).reset_index(drop=True)
    usable = texts[texts.quality_flag.isin(["ok", "thin"])].copy()
    llm = LLM()

    # (b) themes ---------------------------------------------------------------
    recs = usable.to_dict("records")
    outs = parallel_map(lambda r: code_themes(llm, r), recs, desc="themes")
    theme_rows = []
    for r, o in zip(recs, outs):
        row = dict(ticker=r["ticker"], year=r["year"])
        if "_error" in o:
            row["llm_error"] = o["_error"]
        else:
            sal = o.get("salience") or {}
            row.update({f"sal_{t}": _int03(sal.get(t, 0)) for t in TIDS})
            ev = o.get("evidence") or {}
            row.update(page_type=o.get("page_type"), primary_stakeholder=o.get("primary_stakeholder"),
                       framing=o.get("framing"), register=o.get("register"),
                       llm_summary=o.get("summary", ""),
                       evidence="; ".join(f"{t}: {ev[t]}" for t in TIDS if ev.get(t)))
        theme_rows.append(row)
    codes = pd.DataFrame(theme_rows)
    codes.to_csv(interim_dir("part1") / "llm_themes.csv", index=False)
    n_err = int(codes["llm_error"].notna().sum()) if "llm_error" in codes else 0
    if n_err:
        print(f"  WARNING: {n_err}/{len(codes)} theme codings failed; first error: "
              f"{codes['llm_error'].dropna().iloc[0][:400]}")
    if n_err > 0.2 * len(codes):
        sys.exit("Too many LLM failures - fix the error above and re-run with --from 4 "
                 "(successful calls are cached and will not be paid for again).")

    # (a) changes ---------------------------------------------------------------
    pairs = []
    for tk, g in usable.groupby("ticker"):
        g = g.sort_values("year").to_dict("records")
        for prev, cur in zip(g[:-1], g[1:]):
            pairs.append((prev, cur, text_similarity(prev["text"], cur["text"])))

    def do_pair(p):
        prev, cur, sim = p
        base = dict(ticker=cur["ticker"], year=cur["year"], prior_year_compared=prev["year"],
                    gap_years=cur["year"] - prev["year"], similarity_prior=round(sim, 4))
        if sim >= UNCHANGED_SIM:
            return {**base, "changed_from_prior": False, "change_type": "none",
                    "change_description": "text identical or near-identical", "linguistic_shifts": "",
                    "themes_gained": "", "themes_lost": ""}
        o = analyze_change(llm, prev, cur, sim)
        # .get with defaults: models occasionally omit a "required" field; a missing list
        # should not discard the rest of an otherwise valid answer.
        return {**base, "changed_from_prior": True, "change_type": o.get("change_type", "unclassified"),
                "change_description": o.get("description", ""),
                "linguistic_shifts": " | ".join(map(str, o.get("linguistic_shifts") or [])),
                "themes_gained": ";".join(t for t in (o.get("themes_gained") or []) if t in TIDS),
                "themes_lost": ";".join(t for t in (o.get("themes_lost") or []) if t in TIDS)}

    changes = pd.DataFrame(parallel_map(do_pair, pairs, desc="changes"))
    changes.to_csv(interim_dir("part1") / "llm_changes.csv", index=False)

    # (c) trajectories ------------------------------------------------------------
    if not args.skip_trajectories:
        strong = LLM(model=MODEL_STRONG)
        man = pd.read_csv(interim_dir("part1") / "snapshot_manifest.csv")
        names = load_companies().set_index("ticker").company_name
        jobs = []
        for tk in sorted(man.ticker.unique()):
            m = man[man.ticker == tk].set_index("year")
            c = codes[codes.ticker == tk].set_index("year") if "sal_integrity_ethics" in codes else pd.DataFrame()
            ch = changes[changes.ticker == tk].set_index("year") if len(changes) else pd.DataFrame()
            lines = []
            for y in m.index:
                if m.loc[y, "status"] != "ok":
                    lines.append(f"{y}: MISSING ({m.loc[y, 'missing_reason']})")
                    continue
                if y not in c.index:
                    lines.append(f"{y}: snapshot unusable (thin/JS shell)")
                    continue
                cr = c.loc[y]
                sal = ", ".join(f"{t}={int(cr[f'sal_{t}'])}" for t in TIDS if cr.get(f"sal_{t}", 0) > 0)
                flag = " [DIFFERENT URL]" if str(m.loc[y].get("url_switched")) == "True" else ""
                chg = f" | change: {ch.loc[y, 'change_type']} - {ch.loc[y, 'change_description']}" \
                      if y in ch.index else ""
                lines.append(f"{y}{flag}: {cr.framing}/{cr.register}/{cr.primary_stakeholder}; "
                             f"{sal}; summary: {cr.llm_summary}{chg}")
            jobs.append((tk, names.get(tk, tk), "\n".join(lines)))
        trajs = parallel_map(lambda j: synthesize(strong, *j), jobs, desc="trajectories")
        pd.DataFrame([dict(ticker=j[0], pattern=t.get("pattern"),
                           trajectory_summary=t.get("trajectory_summary"),
                           notable_shifts=" | ".join(f"{s.get('years', '?')}: {s['shift']}"
                                                     for s in (t.get("notable_shifts") or [])
                                                     if isinstance(s, dict) and "shift" in s),
                           data_caveats=t.get("data_caveats"), llm_error=t.get("_error"))
                      for j, t in zip(jobs, trajs)]).to_csv(
            interim_dir("part1") / "llm_trajectories.csv", index=False)

    if args.reliability:
        rel = reliability(llm, usable, codes, args.reliability)
        rel.to_csv(out_dir("part1") / "llm_reliability.csv", index=False)
        print(rel.round(3).to_string(index=False))
    print("done: llm_themes.csv, llm_changes.csv, llm_trajectories.csv")


if __name__ == "__main__":
    main()
