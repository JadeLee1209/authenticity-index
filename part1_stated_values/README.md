# Part 1 — Stated values: archived "About us" pages, 2016–2024

## What I did

| Step | Script | Does |
|---|---|---|
| 1 | `s1_discover_pages.py` | Builds and scores candidate URLs per firm (curated seeds + automatic discovery over the Wayback CDX index) |
| 2 | `s2_collect_snapshots.py` | Picks one capture per firm-year, follows/validates redirects, saves original bytes |
| 3 | `s3_extract_text.py` | Strips navigation, footer and boilerplate; flags thin / JS-only captures |
| 4 | `s4_llm_analyze.py` | Codes value themes, classifies year-over-year change, synthesises each firm's trajectory |
| 5 | `s5_build_dataset.py` | Builds `stated_values.csv`, `coverage_report.csv`, figure and digest |

Run: `python run.py part1` (or `make part1`, or the five scripts in order). After step 1, **read
`data/interim/part1/page_selection.csv`**; any wrong pick is fixed by adding a line to
`config/page_overrides.csv` (`ticker,url`) and re-running steps 1–2. Page identification is the
one step where a human check pays off most, and the override file keeps that check auditable.

## Which page counts? (identification criteria)

The target is the page on which the firm states **who it is and what it values**: a values /
principles / credo page if one exists, else mission/purpose, else the general About page. Two
principles drive the rules:

1. **Same page across years.** A switch of page would show up as a change in values. So one
   primary URL is chosen per firm and fallbacks are used only in years where the primary has no
   valid capture; those years carry `url_switched=True` and an analyst note.
2. **Transparent scoring, human override.** Candidates = hand-curated seeds (from the live sites,
   marked as unverified in `companies.csv`) plus URLs discovered in the CDX index in the same
   directory as each seed whose path contains about/values/mission/purpose/credo/… (whole-domain
   scans time out on large sites) Score = keyword tier (values,
   credo, principles, mission, purpose = 3; about/who-we-are = 2; company/culture = 1) + seed bonus 2
   + coverage (4 × share of 2016–24 years with a capture) − penalties (careers/news/investor/
   leadership/history pages −3, non-English locale −5, query strings −2, deep paths −1 per level).

Firms without a conventional page are kept and documented rather than forced:
Berkshire Hathaway's site is a single static homepage (homepage allowed, Owner's Manual is a PDF);
Apple has no corporate About page; Tesla and Nike are heavily JavaScript-rendered.

## Snapshot, redirect and missing-data rules

* **Target date** 1 July of each year; captures tried in order of distance from it (status 200
  and WARC revisits before redirects), at most 5 per URL (`--tries`).
* **Redirect chains**: followed up to 5 hops. Accepted only if the final URL (a) stays on the
  firm's own domains (listed in `companies.csv`, e.g. `google.com → about.google`,
  `newsroom.fb.com → about.fb.com → about.meta.com`), (b) is not a homepage/locale root (a
  retired page bouncing to `/` is `redirect_to_homepage`), and (c) the capture actually served is
  from the same calendar year (Wayback serves the nearest capture of the target, which can be
  years away → `capture_outside_year`).
* **Missing**: if nothing passes, the row stays in the dataset with `status=missing` and a reason
  (`no_capture_in_year`, `no_extractable_text`, `redirect_to_homepage`, `redirect_to_other_language`,
  `redirect_offsite`, `redirect_chain_too_long`, `capture_outside_year`, `soft_404`, `empty_body`,
  `http_4xx/5xx`, `network_error`). Nothing is borrowed from adjacent years at this stage; the only
  imputation in the project is an explicit, flagged one-year carry-forward in Part 3.

## Human review loop (overrides and blocklist)

Automatic selection is followed by a documented human review, because a wrong page silently
corrupts every downstream measure:

* `config/page_overrides.csv` (`ticker,url`): forces the primary page after checking Wayback
  calendars. Used for three firms (the file is included in the repository):
  WFC (the dedicated *Vision & Values* page, 2016-2020, falling back to `/about` after it was
  retired), NVDA (`/en-us/about-nvidia`) and EOG (`/company/history`, the only company page
  with archived text; see below).
* `config/url_blocklist.csv` (`ticker,url_prefix,reason`): fallback pages that are not
  About/values pages (legal pages, press releases, product pages, CSR reports). A year whose
  only remaining capture is blocklisted stays missing rather than being filled off-topic.
* Additional capture rules added after review: reject redirects into another language
  version (`/about` -> `/es/about/`), reject "soft 404" error pages served with HTTP 200
  (detected in the title, first heading or opening text), reject captures with no extractable
  text (JavaScript shells), and always strip cookie-consent and language-switch notices, so
  another capture or fallback can fill the year.
* Extraction is independent per snapshot (trafilatura's cross-document de-duplication is
  disabled; with it on, a page identical to last year's could lose its text).

Re-run only the affected firms with `python run.py part1 --tickers T1 T2` (overrides) or
`python run.py part1 --from 2` (blocklist / rule changes; downloads come from cache).

## Which rows enter the authenticity index (`index_eligible`)

The LLM's `page_type` flags pages that are not About pages. Rather than dropping all of them,
`index_exclusion_reason` separates three cases:

* `no_coded_text`: no snapshot, unusable text or failed coding.
* `page_states_no_values`: judged not an About page **and** no theme at salience >= 2
  (navigation menus, error pages, executive biographies).
* `firm_has_no_about_page`: at least 2/3 of the firm's coded years are not About pages
  (Apple's navigation hub, Berkshire Hathaway's static homepage, EOG's year-by-year results
  timeline for shareholders) - a structural gap.

Company About pages that say little about values (timelines, promotional copy) remain
eligible: "the page says little about values" is an observation, not missing data.

## Text extraction

Cascade, method recorded per row: trafilatura (precision mode, if installed) → DOM heuristics
(drop nav/header/footer/aside/forms/cookie and consent banners/social/search/modal elements by tag
and by id/class/role; keep `<main>`/`<article>` if substantial; line filter for copyright, privacy,
"skip to content" etc.; de-duplicate lines) → embedded JSON harvesting for JS-rendered pages
(`__NEXT_DATA__`-style blobs). Short lines are kept on purpose: on values pages, one-word headings
("Integrity", "Respect") are the values. Quality flags: `ok`, `thin` (<40 words), `js_shell`,
`not_english`, `error_page`, `empty`. Captures that fail these checks are rejected in step 2 so a
later capture or fallback URL can fill the year; in the final run all 409 retained texts are `ok`.

## Analytical categories and why

12 themes (`config/themes.yaml`), each coded 0–3 for salience:
integrity & ethics · customer focus · innovation · performance & excellence · employees & talent ·
diversity, equity & inclusion · environment & climate · community & social impact · health &
safety · collaboration & respect · governance & long-term ownership · purpose & societal mission.

* **Grounding.** The values most often named by large US firms (Sull et al. 2020 "Culture 500";
  Guiso, Sapienza & Zingales 2015) plus stakeholder categories (Freeman 1984; 2019 Business
  Roundtable statement) and ESG pillars.
* **Built for Part 3.** Every theme has a definable proxy-statement counterpart (`proxy_evidence`
  in the YAML) so stated and lived values can be compared on the same axes.
* **Split where movement differs.** DEI is separate from general employee themes because their
  2016–24 trajectories diverge sharply (surge after 2020, retreat after 2023).
* **Salience, not presence.** A 0–3 scale distinguishes a headline value from a passing mention,
  which matters when nearly every page mentions customers somewhere.

Additional codes: page type (catches wrong pages), primary stakeholder, framing (purpose-driven,
values list, performance-driven, heritage, business description) and register (aspirational vs
operational). Interpretable lexicon rates (`ling_*`: hedging, commitment, first-person plural,
future orientation, numeric specificity, Flesch-Kincaid grade) complement the LLM.

## LLM pipeline

* **Change (a)**: deterministic gate first — similarity (word-sequence ratio + 5-shingle Jaccard)
  ≥ 0.98 ⇒ unchanged, no LLM call. Otherwise the LLM sees both versions plus a sentence-level diff
  and classifies `cosmetic / minor_substantive / major_rewrite / page_replaced`. The dataset keeps
  both `changed_from_prior` (any text change) and `substantive_change` (values wording changed),
  because many edits are CMS redesigns.
* **Themes (b)**: each snapshot coded independently (no access to other years, so codes are not
  anchored on history); short verbatim evidence for salience ≥ 2.
* **Shifts (c)**: per-pair "from X to Y" linguistic shifts, then a stronger model reads each
  firm's 9-year sequence and writes the trajectory (`stable/incremental/punctuated/volatile`).
* **Reliability**: `--reliability N` re-codes N snapshots with a paraphrased prompt and reports
  exact agreement, quadratic-weighted kappa per theme, and Spearman correlation with the keyword
  dictionary (convergent check) → `outputs/part1/llm_reliability.csv`.

## Output dataset — `outputs/part1/stated_values.csv`

Required columns: `ticker, company_name, sector, year, page_text_clean, changed_from_prior,
theme_categories` (themes with salience ≥ 2, strongest first), `analyst_notes` (provenance caveats
first, then the change description and linguistic shifts). Additional: provenance (`page_url,
capture_ts, final_url, redirect_chain, url_switched`), extraction (`extraction_method, n_words,
quality_flag`), change (`similarity_prior, change_type, substantive_change, themes_gained/lost,
linguistic_shifts`), coding (`sal_<theme>` ×12, `page_type, primary_stakeholder, framing,
register, llm_summary, evidence`), and `ling_*` features. Per-firm narratives:
`data/interim/part1/llm_trajectories.csv`.

## Assumptions

* A mid-year capture represents the page "in that year".
* Wayback's archived HTML is what visitors saw; for client-rendered pages it often is not
  (flagged `js_shell`).
* The English US page is the relevant one for US-listed firms.

## Known limitations

* Wayback coverage is uneven and biased toward popular pages; deep values pages of less-visited
  sites have sparser captures, so missingness is not random (more gaps early in the window and for
  JS-heavy sites).
* Seed URLs were curated from knowledge of the live sites and must be verified after step 1.
* About pages are only one channel of stated values (also annual letters, codes of conduct,
  careers pages); a firm with a thin About page is not necessarily silent on values.
* LLM coding of salience is a judgment; reliability statistics bound but do not remove that.

## With more time

* Hand-code a stratified 10% sample with a second human coder to validate the LLM (κ against humans).
* Add the code of conduct and CEO shareholder letter as additional stated-value channels.
* Render JS-only captures with a headless browser against Wayback playback.
* Monthly rather than annual sampling around key events (mid-2020, mid-2023) to date changes precisely.
