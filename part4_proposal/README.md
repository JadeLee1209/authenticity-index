# Part 4 — Does talk lead walk, or does walk lead talk?

## Why this question

The OAI is a snapshot of alignment. The scientifically interesting question is **how alignment is
produced over time**, because two well-established theories predict opposite dynamics:

* **Aspirational talk** (Christensen, Morsing & Thyssen 2013): value statements are public
  commitments that later pull practice toward them → a rise in stated emphasis should *precede*
  a rise in backing.
* **Decoupling / impression management** (Meyer & Rowan 1977; Bromley & Powell 2012): rhetoric
  tracks the institutional mood while practice moves slowly → stated emphasis should *not* predict
  later backing; if anything firms start talking about what they already do (walk → talk).

2016–2024 offers a rare test: DEI language rose sharply after 2020 and came under organised
pressure after mid-2023. Who blinked first — the words or the practices?

## What `lead_lag.py` does

1. Firm × theme × year panel from Part 3 (`oai_theme_long.csv`), first-differenced (removes every
   firm × theme fixed level, e.g. energy firms always stress safety).
2. Two regressions with year and theme fixed effects and firm-clustered (CR1) standard errors:
   (A) Δbacking<sub>t+1</sub> on Δsalience<sub>t</sub> — *talk → walk*;
   (B) Δsalience<sub>t+1</sub> on Δbacking<sub>t</sub> — *walk → talk*;
   each controlling for the outcome's own lagged change (mean reversion). Run on all themes, on
   "hot-button" themes (DEI, climate) and on the rest.
3. DEI case: for each firm whose stated DEI salience peaked ≥ 2, date the first decline after the
   peak in stated salience and in lived backing; classify **talk-first** (words dropped while
   practice persists — "DEI-hushing", analogous to greenhushing), **walk-first** (practice erodes
   behind unchanged words — window dressing) or simultaneous. Done twice: with peer-relative
   backing (drop = 0.15 below peak) and, as the robustness check, with **absolute** substantive DEI
   disclosure density (drop = below 80% of peak), each with an exact binomial test of talk-first
   vs walk-first. The absolute version matters because a peer-relative score cannot see a retreat
   that every firm makes at once. Plus aggregate series (each indexed to its peak) in
   `dei_series.png`.

## How to read the results

* β (A) > 0 and δ (B) ≈ 0 → support for aspirational talk.
* δ > 0 and β ≈ 0 → firms talk about what they already do (or practice responds to the same
  shocks first).
* Neither → stated values and disclosed practice move independently = decoupling.
* A hot-button vs. other-themes contrast tells whether contested values behave differently from
  core values — the more interesting finding if it appears.

## Results of the final run (interpreted in `SUMMARY.md`)

* All themes: no lead in either direction (A: t = 1.2; B: t = −0.3) → decoupling for core values.
* Hot-button themes (DEI, climate): talk → walk, β = 0.029 (+2.9 percentile points of backing per
  one-step rise in stated salience), t = 2.95, survives a Bonferroni correction for 6 models;
  walk → talk not significant (t = 1.2). Other themes: nothing.
* DEI series: website emphasis peaks 2022, proxy disclosure 2021, DEI pay adoption 2023 and still
  at 86% of peak in 2024 - pay is the stickiest signal.
* DEI retreat: peer-relative 14 talk-first vs 5 walk-first (p = 0.064), but absolute 12 vs 12
  (p = 1.00). The apparent "DEI-hushing" is an artefact of the relative measure; we report the
  absolute result.

## Caveats (why this is preliminary)

* Short panel: ≤ 8 consecutive transitions per firm-theme (fewer where years are missing); the lag structure is annual
  while events are not.
* Backing is peer-relative, so the regressions speak to changes in *relative* position.
* Δsalience is coarse (0–3 integer steps); many firm-themes never change.
* The models include the outcome's own lagged change; in first-differenced panels this biases
  that coefficient (the coefficient of interest much less so).
* Granger-style precedence is not causation: a common shock that hits disclosure before the website
  is redesigned would look like walk → talk.

## Next steps

Monthly Wayback sampling around 2020 and 2023 to date stated changes precisely; adding outcome
data (EEO-1, emissions) to see whether practice outside the proxy persisted when words retreated; extending to
all 500 firms for power.
