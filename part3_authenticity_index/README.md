# Part 3 — Organizational Authenticity Index (OAI)

## Definition

Authenticity here means **claims backed by conduct**: of the values a firm says it holds,
weighted by how prominently it says them, how strongly do its mandated disclosures and its pay
design back them, relative to peers in the same year?

For firm *i*, year *t*, theme *k* (12 themes):

* **Stated emphasis** `s_ikt = salience_k / Σ salience` (Part 1, LLM salience 0–3; sums to 1).
* **Lived backing** `b_ikt ∈ [0,1]` = 0.6 × percentile of substantive disclosure density among
  the 50 firms that filing year + 0.4 × pay score (0 if no incentive metric on the theme; otherwise
  0.5 + 0.5 × percentile among firms that do pay on it).
* **OAI** `= 100 × Σ_k s_ikt · b_ikt`. 50 ≈ a typical peer's backing; 100 = every claim backed
  at the top of the peer distribution.

Companion columns in `oai_firm_year.csv`: `congruence` (Spearman of salience and backing across
themes), `say_do_gaps` (salience ≥ 2, backing < ⅓), `silent_strengths` (salience 0, backing > ¾),
`top_backed_claims`, `oai_uniform_claims` (OAI if all themes were claimed equally) and
`claim_selection_effect` (OAI minus that benchmark: does the firm claim what it is strong at?).
Theme-level detail: `oai_theme_long.csv`.

## Why this operationalisation (the reasoning)

1. **Asymmetric, not symmetric.** "Alignment" could mean similarity of two profiles (cosine,
   correlation). That treats *doing more than you say* as misalignment. For authenticity the
   failure mode is claims without substance, not substance without claims; quiet practice is
   reported separately (`silent_strengths`) rather than penalised.
2. **Peer-relative per theme and year.** Proxies are governance documents: performance and
   shareholder language saturates every filing while collaboration hardly appears. Raw shares
   would mechanically reward firms that claim financial values. Percentiles put every theme on
   the same footing and remove year-wide disclosure waves (e.g. 2021 human-capital disclosure).
   Cost: OAI is relative — if all firms decouple together, OAI cannot see it.
3. **Two independent kinds of backing.** Disclosure quality (substantive, not aspirational, text)
   and pay (what the board rewards) fail in different ways; combining them reduces dependence on
   either. Weights 0.6/0.4 reflect pay's sparseness for most non-financial themes; the robustness
   check shows how rankings change at 1/0 and 0/1.
4. **Decomposable.** Because OAI is a weighted sum, every score can be traced to the specific
   claims that are backed or unbacked — what a non-technical reader needs to act on it.

Stated side: only Part 1 rows with `index_eligible=True` are used (see Part 1 README; this
drops missing pages and the three firms without a real About page - Apple, Berkshire Hathaway,
EOG). Timing: About page of year *t* with the proxy filed in *t* (both ≈ mid-year *t*); `--lag 1` tests
whether conduct catches up a year later. Missing stated years are carried forward at most one
year (`stated_imputed=True`); `--carry-forward 0` drops them.

## Distribution and validity (generated)

`build_index.py` → `distribution.md`, `oai_distribution.png`: mean/sd/IQR/skew, sector and year
breakdowns, between- vs within-firm variance share, average year-over-year movement.

`validity.py` → `validity.md`:

1. **Permutation (discriminant) test — main check.** If OAI captures *firm-specific* alignment,
   a firm's claims must be better backed by its own proxy than by a random peer's. The lived side is
   shuffled across firms within year (and within sector-year) 1,000 times; true mean OAI vs. null.
2. **Known groups.** Firms with documented say-do controversies (Wells Fargo 2016–18 on integrity
   and customers, Meta 2018–19, J&J 2018–20, ExxonMobil 2020–22 on climate; BlackRock as a
   high-expectation case) should show low backing on the implicated themes vs. sector peers and
   vs. their own other years. Reported hit or miss — misses are informative (see limitations).
3. **Robustness.** Rank correlation with disclosure-only, pay-only, sector-peer, lagged and
   no-imputation variants.
4. **Convergent (optional).** Correlation with an external ESG rating if supplied. Expect a
   moderate positive correlation; a very high one would suggest OAI is just an ESG proxy.

## Results of the final run (details in `outputs/part3/*.md` and `SUMMARY.md`)

* 390 of 450 firm-years scored (47 firms); mean 39.7, sd 12.0; 55% of variance between firms.
* Permutation test passes: z = 5.4 shuffling within year, z = 1.8 (p = 0.035) within sector-year
  - firm-specific alignment is real but modest; much of it is shared within sectors.
* Known groups mostly fail (1/9 vs peers, 3/9 vs own history): every scandal firm shows *higher*
  backing on the implicated theme than its peers - see limitation 1.
* Robustness: ρ = 0.93 (sector peers), 0.87 (disclosure only), 0.53 (pay only), 0.97 for firm
  means with a one-year lag.

## Limitations / threats to validity

1. **Disclosure is not behaviour.** Backing is measured in documents the firm writes. A firm can
   disclose substantively about practices it does not follow; pay metrics are intentions, not
   outcomes. The known-group misses are best read this way: after a scandal the proxy documents
   the board's response - Wells Fargo's 2017 proxy reports cancelled 2016 bonuses, forfeited
   equity and executives evaluated on risk management and Code-of-Ethics compliance - so the firm
   scores *high* on the implicated themes exactly when its behaviour was worst. OAI measures
   documented commitment, not conduct; it is not a misconduct detector.
2. **Channel asymmetry and construct coverage.** Some values have weak natural expression in a
   proxy (innovation, collaboration); peer-relative scoring equalises the scale but measures
   backing on those themes with more noise.
3. **Relative measure.** Percentiles cannot detect sector- or market-wide movements. Part 4 shows
   this concretely: with peer-relative backing, DEI retreats looked "talk first" (14 vs 5); with
   absolute disclosure the split is 12 vs 12, because nearly all firms cut DEI disclosure at once.
4. **Measurement error compounds.** LLM salience, dictionary density and metric extraction each
   add noise; OAI inherits all of it, attenuating correlations with external criteria.
5. **Sample.** 50 of the largest 2024 firms, observed backward: survivorship and size bias.

## With more time

* Replace or augment the lived side with outcome data (EEO-1 workforce composition, EPA GHGRP
  emissions, OSHA injuries, CFPB complaints, enforcement fines) to move from "backed by disclosure"
  to "backed by behaviour".
* Estimate an item-response or latent-variable model treating stated and lived codes as noisy
  indicators, giving uncertainty intervals per firm-year.
* Pre-register the known-groups expectations on an independent event list (e.g. RepRisk) instead
  of a hand-picked set.
