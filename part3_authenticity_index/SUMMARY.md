# Part 3 Summary — An index of organizational authenticity

## The idea in one paragraph

We call a firm authentic to the extent that **the values it advertises are backed by what it
discloses and pays for**. For each of the 12 value themes we compare two things:
- how loudly the firm claims the theme on its website (Part 1);
- how strongly its proxy statement backs it, relative to peers that year (Part 2). Backing
  combines substantive disclosure (60%) and executive-pay incentives (40%).

The Organizational Authenticity Index (OAI) is the claim-weighted average of that backing. It
runs from 0 to 100. Because it is built up theme by
theme, every score can be traced to the specific claims that pull it down (`say_do_gaps`).

## What the index looks like

- **Coverage.** 390 of 450 firm-years are scored, covering 47 firms. Three firms are never
  scored because they have no real About page (Part 1). Apple's page is a navigation hub and
  Berkshire Hathaway's is a static homepage. EOG Resources' only company page is a year-by-year
  record of production and dividends written for shareholders. That last case is telling in its
  own right: the firm presents itself entirely through financial results.
  A few firms are scored in only 4–5 years (Abbott, Broadcom, Lowe's), so their averages are
  less reliable.
- **Scale.** The mean is 39.7 and half of firm-years fall between 32 and 46. The distribution is
  mildly right-skewed: a few firms back their claims far more than the rest (maximum 94).
Most themes are never tied to executive pay, so most claims can earn at most 60 of the 100 points; that, not weak backing per se, is why scores centre near 40.
- **Partly a stable trait, partly year-to-year movement.** 55% of the variation is between firms
  and 45% is change within a firm over time. Firm rankings are stable when averaged over years,
  but single-year scores move by about 8 points on average. Single years should be read with
  caution.
- **Highest and lowest firms.** The highest averages belong to McDonald's (72.6), Wells Fargo,
  American Express, Citigroup and Microsoft (50–54). The lowest belong to Tesla (19.5),
  Halliburton, Charles Schwab, IBM and Salesforce (22–30). Tesla is the clearest case: its
  executive pay is tied almost entirely to market value and financial milestones, so the
  values on its website find little backing in its proxy.
- **Sectors and years.** Financials (42.7) and healthcare (41.2) score slightly higher than
  technology (36.6). There is no trend over time: the yearly mean stays between 39 and 41.
  Because the index is relative to peers, an economy-wide change cancels out.
- **Most common unbacked claims:** innovation, employees, purpose, community and customers.
  These are the soft, aspirational themes that are easy to state and rarely tied to specific
  disclosure or pay.
- **"Silent strengths" are rare.** These are themes a firm backs strongly in its proxy but does
  not claim on its website. Only about 70 theme-years qualify. The most common are shareholder
  governance (23) and health & safety (20). Energy firms, for example, pay executives for safety
  results without featuring safety as a headline value.

## Does it measure what it should?

- **Own-versus-peer test: passes.** If the index captures firm-specific alignment, a firm's
  claims should be better backed by its *own* proxy than by a randomly chosen peer's. They are:
  - Against random firms in the same year, the true mean is 39.7 versus 38.2 under shuffling
    (z = 5.4, p = 0.001).
  - Against random firms in the same *sector* and year, the result is weaker but still
    significant (z = 1.8, p = 0.035).

  Much of the alignment is therefore shared within sectors. The firm-specific part is real but
  modest.

- **Known cases: mostly fail, and the failure is informative.** We pre-specified that firms
  with well-known say-do controversies would show weak backing on the implicated themes:
  - Wells Fargo on integrity and customers, 2016–18.
  - Meta on integrity and customers, 2018–19.
  - Johnson & Johnson on safety and integrity, 2018–20.
  - ExxonMobil on climate, 2020–22.

  The expectation was met in only 1 of 9 comparisons against sector peers and 3 of 9 against
  the firm's own other years. In every scandal case the firm's backing on the implicated theme
  was *higher* than its peers'. For example, Wells Fargo's customer-theme backing was 0.71
  against a peer average of 0.38.

  The likely reason is that **scandals trigger remediation disclosure**. After a scandal, the
  proxy explains the board's response, its new oversight structures and the pay actions it took.
  Wells Fargo's 2017 proxy, covering 2016 pay, is an example: the board eliminated annual
  incentive awards, reduced performance-share payouts and forced executives to forfeit equity
  awards. It also stated that executives are evaluated on "appropriate risk management practices
  and compliance with our Code of Ethics." Its new incentive metrics, however, remained
  financial. This is real accountability, but it is a *response* to misconduct. A text-based
  index reads it as strong backing.

  We did not change the test after seeing this result. We report it as a finding about what the
  index can and cannot see.

- **Robustness.** Rankings are stable under reasonable alternative designs:
  - Using sector instead of market-wide peers: ρ = 0.93.
  - Using disclosure only: ρ = 0.87.
  - Pairing each website year with the next year's proxy: ρ = 0.97 for firm averages, though
    only 0.56 year by year.
  - Using pay only: ρ = 0.53. Pay and disclosure capture different things, which is why both
    are included.

## Limits a decision-maker must know

1. **It measures backing in the firm's own disclosures, not conduct or outcomes.** As the
   known-cases test shows, a firm in trouble can score *high*: the remediation it is forced to
   disclose looks like commitment. The OAI is not a misconduct detector.
2. **It is relative to peers.** If all firms backslide together, the index will not show it.
3. **It only scores what firms claim.** A firm that states few values and backs them scores
   well. The `claim_selection_effect` column shows how much of a score comes from *which* themes
   a firm chose to claim.
4. **Single-year scores are noisy.** Use multi-year averages for comparisons between firms.

## How to use it

- **Prioritise questions, don't rank virtue.** For each firm-year the `say_do_gaps` column lists
  the specific claims an analyst, investor or journalist should ask about.
- **Read a high score in a scandal period as "the firm is now documenting a response",** not
  "the firm was authentic".
- **Next step: validate against outcomes.** The natural next check is to compare the index with
  external records of conduct, such as regulatory violations, emissions data or workforce
  diversity reports. The code already accepts an external score file
  (`data/external/esg_scores.csv`) for this purpose.
