"""Part 2, step 5 - LLM-assisted measures of LIVED values in proxy statements.

Two questions a dictionary cannot answer, so an LLM is used for them:

A. Is the disclosure SUBSTANTIVE or SYMBOLIC?
   Theme words appear in both "we are committed to diversity" (symbolic) and "women hold 38% of
   VP+ roles, up from 31%; 10% of the bonus is tied to representation goals" (substantive).
   Organisation theory distinguishes symbolic from substantive adoption (Meyer & Rowan 1977;
   Westphal & Zajac 1998; Bromley & Powell 2012). We sample, per theme, the passages with the most
   theme keywords and have the LLM label each passage's evidence type. The per-theme share of
   substantive passages is an estimate of disclosure quality for that theme.
   Sampling up to `--per-theme` passages for EACH theme (rather than the top-N overall) is
   deliberate: it gives every theme an estimate, while theme EMPHASIS is measured on the full
   document by the dictionary (step 4), so the sample design does not bias emphasis.

B. What are executives PAID for?
   The incentive metrics and weights in the CD&A are the most behavioural signal in a proxy:
   they reveal what the board actually rewards. The LLM extracts each metric, its plan, weight and
   maps it to the shared taxonomy.

Input : data/interim/part2/parsed/*.json
Output: data/interim/part2/llm_passages.csv   one row per labelled passage
        data/interim/part2/llm_pay_metrics.csv one row per extracted incentive metric
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import interim_dir
from authenticity.llm import LLM, parallel_map
from authenticity.themes import compiled, theme_hits, theme_ids, themes_prompt_block

TIDS = theme_ids()
EVIDENCE = ["quantified_outcome", "concrete_action", "governance_mechanism",
            "aspirational_statement", "boilerplate_or_legal"]
SUBSTANTIVE = {"quantified_outcome", "concrete_action", "governance_mechanism"}
BATCH = 8
PAY_KW = re.compile(r"\b(metric|metrics|scorecard|weight(ed|ing)?|modifier|performance (goals?|measures?|"
                    r"objectives?)|payout|annual (cash )?incentive|bonus|psu|performance share|"
                    r"strategic (objectives|priorities)|esg|individual performance)\b", re.I)

# ------------------------------------------------------------------ A. passages
PASSAGE_SYSTEM = f"""You label passages from US corporate proxy statements (DEF 14A) for a study of
whether firms' disclosures back up their stated values.

THEMES:
{themes_prompt_block()}

EVIDENCE TYPES (choose exactly one per passage):
- quantified_outcome: reports numbers, targets, results, percentages, amounts tied to the theme
- concrete_action: describes a specific program, policy, decision or action actually taken
- governance_mechanism: assigns oversight/accountability (committee charter, pay linkage, clawback,
  reporting line, audit) for the theme
- aspirational_statement: values, beliefs, commitments or intentions without specifics
- boilerplate_or_legal: standard legal/procedural text, definitions, voting mechanics

Label each passage with up to 3 themes it substantively concerns (empty list if none) and one
evidence type. Judge only the passage text."""

PASSAGE_SCHEMA = {
    "type": "object",
    "properties": {"labels": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "themes": {"type": "array", "items": {"type": "string", "enum": TIDS}, "maxItems": 3},
            "evidence_type": {"type": "string", "enum": EVIDENCE},
        },
        "required": ["id", "themes", "evidence_type"]}}},
    "required": ["labels"],
}


def select_passages(paras, kinds, per_theme: int) -> list[str]:
    """Up to `per_theme` prose paragraphs (20-350 words) with the most hits for each theme."""
    cand = [(i, p) for i, (p, k) in enumerate(zip(paras, kinds))
            if k == "prose" and 20 <= len(p.split()) <= 350]
    chosen: dict[int, str] = {}
    pats = compiled()
    for t in TIDS:
        scored = sorted(((len(pats[t].findall(p)), i, p) for i, p in cand), reverse=True)
        for hits, i, p in scored[:per_theme]:
            if hits > 0:
                chosen[i] = p
    return [chosen[i] for i in sorted(chosen)]


def mock_passages(batch: list[str]) -> dict:
    labels = []
    for j, p in enumerate(batch):
        h = theme_hits(p)
        th = [t for t, c in sorted(h.items(), key=lambda x: -x[1]) if c > 0][:3]
        ev = "quantified_outcome" if re.search(r"\d+(\.\d+)?\s?%|\$\s?\d", p) else \
             "governance_mechanism" if re.search(r"committee|oversee|oversight|tied to", p, re.I) else \
             "aspirational_statement"
        labels.append({"id": j, "themes": th, "evidence_type": ev})
    return {"labels": labels}


def label_batch(llm: LLM, job: tuple) -> list[dict]:
    ticker, year, batch = job
    user = "\n\n".join(f"<passage id={j}>\n{p}\n</passage>" for j, p in enumerate(batch))
    o = llm.call_tool(system=PASSAGE_SYSTEM, user=user, tool_name="label_passages",
                      tool_description="Record theme and evidence-type labels for each passage.",
                      schema=PASSAGE_SCHEMA, max_tokens=1500, mock=lambda: mock_passages(batch))
    by_id = {}
    for l in o.get("labels") or []:
        try:
            by_id[int(l.get("id"))] = l
        except (TypeError, ValueError, AttributeError):
            continue
    rows = []
    for j, p in enumerate(batch):
        l = by_id.get(j, {"themes": [], "evidence_type": None})
        ev = l.get("evidence_type") if l.get("evidence_type") in EVIDENCE else None
        th = [t for t in (l.get("themes") or []) if t in TIDS]
        rows.append(dict(ticker=ticker, year=year, passage=p, themes=";".join(th),
                         evidence_type=ev, substantive=(ev in SUBSTANTIVE) if ev else None))
    return rows


# ------------------------------------------------------------------ B. pay metrics
PAY_SYSTEM = f"""You extract executive INCENTIVE-COMPENSATION METRICS from the Compensation
Discussion & Analysis (CD&A) of a US proxy statement. Extract every performance metric used to
determine annual incentive (bonus) or long-term incentive (e.g. PSU) payouts for the fiscal year
described. For each metric give: its name, plan (annual or long_term), its weight in percent if
stated (null if not stated or if it is a modifier), whether it is a modifier (+/- adjustment),
its kind (financial, operational, strategic_nonfinancial), and the ONE best-matching theme:
{themes_prompt_block()}
Financial metrics (EPS, revenue, ROE, TSR, cash flow) map to performance_excellence (or
governance_shareholders for TSR/relative shareholder return). Do not invent metrics; if none are
described, return an empty list."""

PAY_SCHEMA = {
    "type": "object",
    "properties": {
        "metrics": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "plan": {"type": "string", "enum": ["annual", "long_term"]},
                "weight_pct": {"type": ["number", "null"]},
                "is_modifier": {"type": "boolean"},
                "kind": {"type": "string", "enum": ["financial", "operational", "strategic_nonfinancial"]},
                "theme": {"type": "string", "enum": TIDS},
            },
            "required": ["metric", "plan", "weight_pct", "is_modifier", "kind", "theme"]}},
        "has_individual_or_strategic_component": {"type": "boolean"},
    },
    "required": ["metrics", "has_individual_or_strategic_component"],
}


def pay_context(d: dict, max_words: int = 6000) -> str:
    paras, kinds = d["paragraphs"], d["kinds"]
    # A located CD&A shorter than 2,500 words almost always means the end marker fired too early
    # (typical CD&As run 4k-25k words); then the whole document is searched instead, as when no
    # CD&A is found. An over-long span is harmless here: we read from its (correct) start.
    span_ok = d["cda"] and sum(len(paras[i].split()) for i in range(*d["cda"])) >= 2500
    rng = range(*d["cda"]) if span_ok else range(len(paras))
    keep, n = [], 0
    for i in rng:
        p = paras[i]
        if PAY_KW.search(p) or (kinds[i] == "table" and "%" in p):
            keep.append(p)
            n += len(p.split())
            if n > max_words:
                break
    return "\n".join(keep)


def mock_pay(ctx: str) -> dict:
    found = []
    for name, theme, kind in [("earnings per share", "performance_excellence", "financial"),
                              ("total shareholder return", "governance_shareholders", "financial"),
                              ("safety", "health_safety", "operational"),
                              ("diversity", "diversity_inclusion", "strategic_nonfinancial"),
                              ("emissions", "environment_climate", "operational"),
                              ("customer satisfaction", "customer_focus", "operational")]:
        if re.search(name, ctx, re.I):
            found.append({"metric": name, "plan": "annual", "weight_pct": None, "is_modifier": False,
                          "kind": kind, "theme": theme})
    return {"metrics": found, "has_individual_or_strategic_component": bool(re.search("strategic", ctx, re.I))}


def extract_pay(llm: LLM, d: dict) -> list[dict]:
    ctx = pay_context(d)
    if not ctx:
        return [dict(ticker=d["ticker"], year=d["year"], metric=None, note="no_cda_context")]
    o = llm.call_tool(system=PAY_SYSTEM, user=f"<cda_excerpt>\n{ctx}\n</cda_excerpt>",
                      tool_name="record_incentive_metrics",
                      tool_description="Record the incentive metrics described in this CD&A.",
                      schema=PAY_SCHEMA, max_tokens=2500, mock=lambda: mock_pay(ctx))
    keys = ("metric", "plan", "weight_pct", "is_modifier", "kind", "theme")
    ms = [{k: m.get(k) for k in keys} for m in (o.get("metrics") or [])
          if isinstance(m, dict) and m.get("metric")]
    for m in ms:  # keep the dataset clean if the model strays outside the enums
        m["theme"] = m["theme"] if m["theme"] in TIDS else None  # unmapped, excluded from weights
        m["is_modifier"] = bool(m["is_modifier"])
        try:
            m["weight_pct"] = float(m["weight_pct"]) if m["weight_pct"] is not None else None
        except (TypeError, ValueError):
            m["weight_pct"] = None
    if not ms:
        return [dict(ticker=d["ticker"], year=d["year"], metric=None, note="no_metrics_found",
                     has_strategic=o.get("has_individual_or_strategic_component"))]
    return [dict(ticker=d["ticker"], year=d["year"], **m,
                 has_strategic=o.get("has_individual_or_strategic_component"), note="")
            for m in ms]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-theme", type=int, default=4)
    ap.add_argument("--tickers", nargs="*")
    args = ap.parse_args(argv)
    llm = LLM()

    docs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(interim_dir("part2", "parsed").glob("*.json"))]
    if args.tickers:
        docs = [d for d in docs if d["ticker"] in args.tickers]

    jobs = []
    for d in docs:
        ps = select_passages(d["paragraphs"], d["kinds"], args.per_theme)
        jobs += [(d["ticker"], d["year"], ps[i:i + BATCH]) for i in range(0, len(ps), BATCH)]
    res = parallel_map(lambda j: label_batch(llm, j), jobs, desc="passages")
    rows = [r for x in res if isinstance(x, list) for r in x]
    errs = sum(isinstance(x, dict) and "_error" in x for x in res)
    pd.DataFrame(rows).to_csv(interim_dir("part2") / "llm_passages.csv", index=False)
    print(f"labelled {len(rows)} passages ({errs} failed batches)")

    pay = parallel_map(lambda d: extract_pay(llm, d), docs, desc="pay metrics")
    prow = [r for x in pay if isinstance(x, list) for r in x]
    pd.DataFrame(prow).to_csv(interim_dir("part2") / "llm_pay_metrics.csv", index=False)
    print(f"extracted {sum(r.get('metric') is not None for r in prow)} incentive metrics")


if __name__ == "__main__":
    main()
