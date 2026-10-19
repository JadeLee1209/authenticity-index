# Part 2 — Lived values: proxy statements (DEF 14A), 2016–2024

## Document choice: why proxy statements

| Criterion | Proxy statement (chosen) | ESG / sustainability / DEI report |
|---|---|---|
| Coverage 2016–24 for all 50 firms | Mandatory annually → near-complete panel | Voluntary; many start 2018–2020; formats and names change |
| Source | One authoritative source (SEC EDGAR), machine-readable | Scattered across IR sites, often PDFs that moved or vanished |
| Talk vs. behaviour | CD&A shows what executives are **paid for**; governance sections show which board committee **oversees** what | Mostly self-curated narrative — the same genre as the About page we want to test |
| Comparability / incentive to embellish | Legally mandated content, Rule 14a-9 liability | Marketing documents with no standard content |

The last row is the key argument: the "lived" side should be a document **less** under the firm's
narrative control than the "stated" side, otherwise Part 3 compares talk with talk. Trade-off: proxies
are governance documents, so some values (collaboration, innovation) appear only faintly — handled
in Part 3 by peer-relative scoring, and discussed as a limitation.

## What I did

| Step | Script | Does |
|---|---|---|
| 1 | `s1_edgar_index.py` | Lists every DEF 14A / DEFC14A 2016–24 via the EDGAR submissions API (incl. predecessor CIKs) |
| 2 | `s2_download_proxies.py` | One annual-meeting proxy per firm-year (rule below) |
| 3 | `s3_parse_proxies.py` | HTML → prose paragraphs / table rows / headings; strips running headers; repairs broken layouts; finds the CD&A |
| 4 | `s4_classical_nlp.py` | Theme-dictionary density, Loughran-McDonald tone, hedging/commitment/specificity, NMF topics, year-over-year similarity |
| 5 | `s5_llm_analyze.py` | LLM: substantive vs. symbolic passages per theme; incentive-pay metrics and weights |
| 6 | `s6_build_dataset.py` | `lived_values.csv` (see [CODEBOOK.md](CODEBOOK.md)), figures, digest |
| 7 | `s7_event_analysis.py` | Within-firm pre/post shifts around external events, with placebo dates |

**Selection rule.** Forms `DEF 14A` and `DEFC14A` (the definitive proxy in a contested election
is still the annual-meeting proxy); not DEFA14A additional materials or DEFM14A merger proxies.
**Proxy year** = filing year, except that proxies filed in November–December count toward the
next year: firms with autumn fiscal year-ends (Apple, Medtronic, Oracle, Nike…) file in December
for an early-year meeting, and calendar assignment would give them two proxies in one year and
none in the next. If several proxies fall in a year: the one whose opening text mentions an
"annual meeting", ties → largest. If the primary document is < 150 KB (cover/notice only), the
largest `.htm` in the filing is used.

**Registrant changes.** BlackRock (2024) and ExxonMobil (2025) moved to new holding-company CIKs
that have no historical filings; their 2016–24 proxies are retrieved under the predecessor CIKs
listed in `config/companies.csv` (`predecessor_ciks`), as is Broadcom Ltd. for its early years.

**Coverage (final run).** 450 / 450 firm-years have a proxy.

## Parsing and locating the CD&A

* EDGAR HTML is typeset for print. Table rows become `cell | cell` lines (incentive weights live
  in tables), prose is re-assembled into paragraphs, and lines repeated ≥ 4 times (running
  headers/footers) are dropped. Each paragraph is tagged prose / table / heading.
* **Layout repair** (only for broken documents, so normal parses and their LLM caches are
  unchanged): when prose is < 15% of words (the whole document typeset inside layout tables -
  IBM 2019, Marathon 2022–24), single-cell table rows are turned back into text; when the average
  prose "paragraph" exceeds 150 words (line breaks lost - Alphabet 2020), it is split at sentence
  boundaries. Repaired documents are flagged `layout_repaired`.
* **CD&A**: starts at the latest "Compensation Discussion and Analysis" heading before the section
  end; ends at the next heading that *starts* with "Summary Compensation Table" or names the
  compensation committee report, or at the SCT column-header row. Cross-references inside the CD&A
  ("see the Summary Compensation Table") are deliberately not treated as ends. Located in 442/450
  proxies. Spans < 2.5k or > 30k words are flagged `cda_suspect` (26) and listed in the digest.
* Pay metrics are read from the start of the CD&A, or from the whole document when no CD&A is
  found or the located one is < 2,500 words (an end marker that fired too early). Over-long spans
  are harmless for this purpose because reading starts at the correct heading.

## Methods and why this mix

* **Classical NLP where transparency matters.** Theme density uses the *same* dictionaries as
  Part 1, so emphasis is measured identically on both sides and is fully reproducible over
  450 long documents (a proxy is typically tens of thousands of words; reading all of them in full with an LLM would mean tens of millions of tokens).
  Keywords were chosen to avoid known proxy false positives ("equity" awards, "for the purpose of",
  oil "pipeline", legal "trust") — see comments in `themes.yaml`.
* **Finance-specific tone.** Loughran-McDonald rather than general sentiment lexicons, which
  misread words like "liability" or "tax" in filings.
* **Topic model as a check on the taxonomy.** NMF on prose paragraphs surfaces emphasis the
  12 themes might miss (e.g. human-capital or cybersecurity oversight sections that arrived mid-period).
  Topic labels are added by hand after reading the top terms.
* **LLM only where meaning is needed and on targeted samples.** (A) up to 4 passages per theme per
  document labelled as quantified outcome / concrete action / governance mechanism (= substantive) vs.
  aspirational / boilerplate (symbolic adoption vs. substantive adoption, Meyer & Rowan 1977;
  Westphal & Zajac 1998). Emphasis comes from the full-document dictionary; the sample only estimates
  quality, so sampling a fixed number per theme does not bias emphasis. (B) the CD&A excerpt goes to
  the LLM to extract every incentive metric, its plan, weight, modifier status and theme.
* **Events.** Within-firm pre (F−3…F−1) vs. post (F…F+2) means around each event's first affected
  filing year F, firm-bootstrap CIs, and a **placebo** event two years earlier to separate event
  timing from pre-existing trends. Events and dates in `config/events.yaml`.

## Assumptions

* Proxy filed in year Y ≈ firm's practices in fiscal Y−1; firms with off-calendar fiscal years
  (MDT, ORCL, NKE, TJX…) are approximately aligned.
* What a firm rewards in executive pay is a valid signal of what it prioritises (standard in
  the compensation and ESG-contracting literature) — it is a signal of intent, not of outcomes.
* Dictionary hit density is an adequate measure of emphasis when combined with a quality check.

## Known limitations

* Proxies under-represent values that live in operations rather than governance (innovation,
  collaboration, customer focus outside banks/insurers).
* Disclosure ≠ behaviour: the 2021 SEC human-capital rule and investor pressure raised disclosure
  across the board; peer-relative scoring in Part 3 absorbs common trends but not firm-specific
  "disclosure management".
* CD&A metric extraction depends on how clearly weights are stated; missing weights fall back to
  equal weights within a plan.
* Event analysis is descriptive: events in the same year overlap (COVID, Floyd and the SEC
  human-capital rule in 2020; the affirmative-action ruling and the anti-ESG backlash in 2023), and
  annual data cannot separate them - for the same theme they produce identical estimates.

## With more time

* Add the 10-K human-capital section (from FY2020) and actual outcomes (EEO-1 data, EPA GHGRP
  emissions, OSHA injury logs, enforcement actions from Violation Tracker) as **behavioural**
  rather than disclosure evidence.
* Validate the substantive/symbolic labels against 300 human-coded passages.
* Use the Message Batches API for the LLM stage (≈50% cheaper, no rate-limit handling).
