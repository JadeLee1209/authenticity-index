# Part 2 Summary — What do proxy statements reveal about lived priorities?

## Bottom line

Between 2016 and 2024 the largest US firms began writing far more about environment and climate
(about 4× more), diversity (about 2× more, peaking in 2021) and their purpose and communities.
What they actually **pay executives for** moved much less. Financial performance and shareholder
returns still drive roughly three-quarters of incentive pay. Climate goals grew to about 3% of
incentive weight on average, and diversity goals never exceeded 1%. About half of the
value-related language is substantive (numbers, specific actions, named oversight). That share
rose only modestly, from 48% to 53–55%.

## What we analysed and why

We used each firm's annual proxy statement (SEC form DEF 14A) and obtained all **450 of 450
firm-years**. Two firms had changed their SEC registration (BlackRock, ExxonMobil), so their
earlier filings were retrieved under the predecessor registrant.

Proxies suit this question for three reasons:
- They are mandatory, follow a common structure and carry legal liability, so firms and years
  are comparable.
- Unlike sustainability reports, they disclose what the board **pays executives for** in the
  Compensation Discussion & Analysis (CD&A).
- That makes them the closest thing in a firm's own disclosures to revealed priorities.

We measured each firm-year in three ways:
1. **Emphasis:** how often each of the 12 value themes (shared with Part 1) is mentioned, per
   1,000 words.
2. **Substance:** whether the theme passages are substantive or boilerplate, classified by an
   LLM over about 16,000 passages.
3. **Pay:** the incentive metrics and their weights, extracted by an LLM from the CD&A of each
   proxy. The CD&A was located automatically in 98% of proxies; for the rest the whole document
   was searched.

## Findings

1. **What firms talk about changed a lot.** All figures are mentions per 1,000 words.
   - **Environment/climate:** 0.70 in 2016 → 2.81 in 2023 (a quadrupling), easing to 2.60 in 2024.
   - **Diversity & inclusion:** about 1.0 on average in 2016–19 → 2.22 in 2021, then down about
     20% to 1.78 by 2024.
   - **Purpose/mission:** tripled (0.05 → 0.16).
   - **Community:** more than doubled (0.38 → 0.90).
   - **Employees:** rose 57% to a 2021 peak. In 2021 the SEC began requiring human-capital
     disclosure, which may have contributed.
   - **Governance and shareholder language** dominates every year (about 7.6) and did not move.
     This reflects what a proxy is for, not a change in values.

2. **Only about half of value talk is substantive, and that barely changed.** The share of theme
   passages with concrete content rose from 48% (2016) to 55% (2023) and slipped to 53% in 2024.
   The volume of value language grew several-fold, while its concreteness improved by only a few
   percentage points.

3. **Pay moved far less than talk.**
   - The share of firms with at least one non-financial incentive metric rose from 26% to 46%.
   - The average weight on climate goals went from essentially zero to 2.8% of incentive pay.
   - Diversity goals appeared after 2020 and peaked at 0.9% of incentive weight in 2022. They
     were 0.7% in 2024, so they had not been dropped from pay plans by then.
   - The weight on financial performance dipped from 59% to 52% in 2021 and recovered to 54%.

4. **Sectors differ in predictable ways.**
   - **Energy:** writes most about climate and safety (3.2 and 0.65 per 1,000 words, the highest
     of any sector).
   - **Financials:** write most about customers, employees and diversity.
   - **Healthcare:** writes most about innovation.
   - **Boilerplate stickiness:** year-over-year document similarity was high everywhere (0.81–0.84)
     and highest in healthcare. Proxies are largely re-used from year to year.

5. **Events.** For each event we compared the three proxies before and after it, within firms,
   against a "placebo" comparison two years earlier. Most themes were already rising steadily,
   so for most events the shift was no larger than the placebo and cannot be attributed to the
   event. Four results stand out:
   - **After the Supreme Court's affirmative-action ruling (SFFA, 2023):** diversity language fell
     17% and its substantive content 21% (95% interval excludes zero). Two years earlier the same
     comparison showed a 17% *rise*. This is the clearest reversal in the data.
   - **After the Business Roundtable's 2019 purpose statement:** community language nearly
     doubled (+96%, 86% of firms increased) versus +42% in the placebo window. Substantive
     customer language rose 60% versus 1%.
   - **After mid-2020 (George Floyd protests):** the rise in diversity *language* was no faster
     than its existing trend. But diversity metrics entered *pay* plans: a 0.6-point increase in
     average weight from near zero, at about a quarter of firms. The placebo shift was 0.07 points.
   - **After the 2023 anti-ESG backlash:** climate language stopped growing (+8%, not
     statistically distinguishable from zero), after rising 110% over the previous window.

   COVID, the racial-justice movement and the SEC human-capital rule all landed in 2020, and the
   affirmative-action ruling and the anti-ESG backlash both in 2023. For the same theme and year
   our design cannot separate these events, so they are timing coincidences, not causal
   estimates.

## Caveats in plain words

- Proxies show what firms disclose and incentivise, not what they achieve.
- Some values (innovation, teamwork) rarely appear in a governance document at all, so a low
  score for them in a proxy is not evidence of neglect.
- **Document problems that were repaired automatically:**
  - Five proxies were typeset in ways that broke text extraction (IBM 2019, Marathon Petroleum
    2022–24, Alphabet 2020).
  - In about 6% of proxies the CD&A boundaries look unusual; these are listed in `digest.md`.
  - Pay metrics are read from the start of the CD&A, or from the whole document when the CD&A
    is missing or implausibly short, so these issues have limited effect on the pay measures.
- **Unusually long proxies:** a few are much longer than usual (e.g. Tesla 2024, which includes
  a special committee report). All emphasis measures are per 1,000 words, so length alone does
  not inflate them.

## What a reader can do with it

- **Judge priorities by pay metrics, not adjectives.** Climate and diversity language
  multiplied, but together they account for under 4% of the average executive's incentive
  weight.
- **Watch for symbolic adoption.** Be wary when a theme's language grows faster than its
  substance. Diversity language more than doubled while its substantive share stayed near half,
  and it was the first theme to retreat when the legal and political climate changed.
