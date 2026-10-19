# Organizational Authenticity: Stated vs. Lived Corporate Values (50 S&P 500 firms, 2016–2024)

Proof-of-concept pipeline that measures how far what large US firms **say** they value (archived
"About us" / values pages) is **backed** by what their mandated disclosures show they **do and pay
for** (proxy statements, DEF 14A). Built to scale from 50 to 500 firms without code changes:
the firm list is a CSV, every network step is cached and resumable, and every LLM call is
schema-constrained, cached and parallel.

| Part | Question | Main output |
|---|---|---|
| [1 Stated values](part1_stated_values/README.md) | What does each firm say it values, and how did that change? | `outputs/part1/stated_values.csv` (450 company-years) |
| [2 Lived values](part2_lived_values/README.md) | What do proxies show firms disclose substantively and reward in pay? | `outputs/part2/lived_values.csv` + [CODEBOOK](part2_lived_values/CODEBOOK.md) |
| [3 Authenticity index](part3_authenticity_index/README.md) | How well are claims backed? | `outputs/part3/oai_firm_year.csv` |
| [4 Proposal](part4_proposal/README.md) | Does talk lead walk, or walk lead talk? (DEI 2019–24 case) | `outputs/part4/findings.md` |

## The one design decision everything hangs on

All three measurement stages share **one theme taxonomy** ([`config/themes.yaml`](config/themes.yaml),
12 themes from the corporate-values and stakeholder literatures). Part 1 codes About pages on it,
Part 2 codes proxy statements on it, and Part 3 compares the two theme-by-theme. Without a
shared coding frame, "alignment" between two very different document types is not defined.

## Repository layout

```
config/                 companies.csv (sample, seed URLs, CIK fixes) · themes.yaml · events.yaml
src/authenticity/       shared code: paths, polite cached HTTP, Wayback CDX, LLM client, text utils
part1_stated_values/    s1 discover pages → s2 collect snapshots → s3 extract text → s4 LLM → s5 dataset
part2_lived_values/     s1 EDGAR index → s2 download → s3 parse → s4 classical NLP → s5 LLM → s6 dataset → s7 events
part3_authenticity_index/ build_index.py · validity.py
part4_proposal/         lead_lag.py
tests/                  synthetic fixtures + offline end-to-end run (mock LLM, no network)
data/  (git-ignored)    raw/ downloads · interim/ caches and intermediate files
outputs/                deliverable datasets, figures, auto-generated digests
```

## Running it

Works the same on Windows, macOS and Linux (e.g. in PyCharm's Terminal):

```bash
pip install -r requirements.txt
# copy .env.example to .env and fill in ANTHROPIC_API_KEY and SEC_USER_AGENT ("Name email")

python run.py test     # offline end-to-end check on synthetic data (~1 min, no network, no API cost)
python run.py check    # verifies .env, the API key, and access to Wayback / EDGAR
python run.py part1    # Wayback scrape is rate-limited: expect a few hours on first run
#   -> review data/interim/part1/page_selection.csv; add config/page_overrides.csv if needed; re-run
python run.py part2
python run.py part3
python run.py part4
python run.py part2 --from 5   # resume a part from step N after an error
python run.py part1 --tickers EOG   # re-collect only some firms after editing page_overrides.csv
```

(`make test`, `make part1` … do the same on macOS/Linux after `set -a && source .env && set +a`.)

Each step can be re-run independently; finished downloads and LLM answers come from cache.
Optional inputs: Loughran-McDonald dictionary CSV in `data/external/` (tone measures);
`data/external/esg_scores.csv` (ticker, year, score) for the convergent-validity check.

**LLM choice.** Bulk coding uses `claude-haiku-5-5` by default (set `LLM_MODEL`); the 50 per-company
trajectory syntheses use `claude-sonnet-5-5` (`LLM_MODEL_STRONG`). Every call asks for output through a
JSON-schema tool; where a model or SDK rejects a setting (temperature 0, forced tool choice, cached
system prompt) the client learns this from the error and retries without it, falling back to parsing
JSON from text if needed. Because temperature 0 is not always available, coding reliability is
measured directly: a paraphrased-prompt re-code of 60 pages (`s4_llm_analyze.py --reliability 60`)
gives weighted kappa 0.93–0.99 per theme.
`LLM_BACKEND=mock` swaps in a keyword-dictionary coder, which doubles as a transparent baseline.

## Global assumptions (detailed per part)

* Sample: the 50 firms listed in the assignment (top 10 by market cap in 5 GICS sectors, S&P 500
  as of Jan 2024). Survivorship: these are 2024 winners observed back to 2016.
* "Year" = calendar year. About-page snapshot targets 1 July; proxy year = filing year, except that
  November–December filings count toward the next year (proxies filed in spring Y mostly describe
  fiscal Y-1). Part 3 pairs both at Y and tests a one-year lag.
* No silent imputation anywhere in the raw datasets; every gap carries a reason code. The only
  imputation is Part 3's flagged one-year carry-forward of stated values (`stated_imputed`).
* Human decisions are kept in files, not in code: `config/page_overrides.csv` (3 firms) and
  `config/url_blocklist.csv` (6 fallback pages) record every manual correction to page selection.

## Coverage and headline results of the final run

| | |
|---|---|
| Part 1 | 409 / 450 firm-years with usable About-page text; 384 enter the index |
| Part 2 | 450 / 450 proxies; CD&A located in 442; 16,170 passages labelled; 2,799 incentive metrics |
| Part 3 | 390 firm-years / 47 firms scored; permutation test z = 5.4 (within sector-year 1.8); known-groups mostly fail - scandal firms document remediation, so OAI measures documented commitment, not conduct |
| Part 4 | Talk leads walk only on hot-button themes (DEI, climate; t = 2.95); DEI retreat shows no talk-first pattern once measured in absolute terms (12 vs 12) |

Each part's `SUMMARY.md` is the non-technical write-up; its `README.md` documents methods, choices
and limitations.
