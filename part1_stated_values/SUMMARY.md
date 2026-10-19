# Part 1 Summary — What do large US firms say they value, and how did that change (2016–2024)?

## Bottom line

Large US firms describe themselves mainly through **performance, innovation and customers**,
and their pages show clear industry signatures (safety in energy and healthcare, purpose in
healthcare, almost no shareholder language in tech). The social themes that rose between 2016 and
2022 then fell back: the share of firms clearly stating **diversity, equity and inclusion rose from
18% to 39% and dropped to 29% by 2024**, and employee and community themes followed the same
path. Stated values change less often than raw page edits suggest: in a typical year about
**one firm in five** substantially rewrites its values message, and change comes in bursts
rather than gradually.

## What we collected

We followed each firm's "About us" / values page in the Internet Archive, one snapshot per year
(target date 1 July), for 50 firms × 9 years = 450 firm-years.

* **409 (91%)** have usable page text, and **384** enter the authenticity index (Part 3).
* Gaps are documented, not filled. 27 firm-years were archived only as empty JavaScript shells
  (NVIDIA 2019–22, Abbott 2018–23, Broadcom 2020–24 and others), 12 were never archived, and 2
  pages had been retired and redirected to the homepage.
* Three firms have no real About page, so they stay in the dataset but are excluded from the
  index:
  * Apple, whose page is a navigation hub.
  * Berkshire Hathaway, which has a static homepage.
  * EOG Resources. Its only company page is a year-by-year record of production, returns and
    dividends written for shareholders. It was judged "not an About page" in 5 of 7 years.
* Snapshot quality was checked by hand as well as by code. We rejected redirects to foreign-
  language versions, error pages served as normal pages, cookie banners, and off-topic fallback
  pages such as press releases and product pages. For Wells Fargo we used its dedicated *Vision &
  Values* page while it existed (2016–2020).

## What firms say they value

**Most common themes.** In a typical year roughly 6 in 10 pages clearly emphasise performance,
innovation or customers, and about 55% state an explicit purpose or mission. Diversity,
environment, and health and safety are minority themes overall.

**Industry signatures** (share of firm-years where the theme is clearly stated):

| Sector | Distinctive emphasis |
|---|---|
| Healthcare | purpose 88%, customers/patients 81%, health & safety 73% |
| Energy | performance 87%, innovation 75%, safety 51%, environment 51% |
| Financials | customers/clients 70%; safety 0%, environment 6% |
| Technology | innovation 84%; shareholders/governance 1% |
| Consumer | performance 72%, customers 66% |

These contrasts are what one would expect from each industry's risks and stakeholders, which is
also a sign that the coding captures real differences rather than noise.

## How it changed

**Social themes rose and then partly retreated.** Share of firms clearly stating each theme:

| Theme | 2016 | Peak | 2024 |
|---|---|---|---|
| Diversity, equity & inclusion | 18% | 39% (2022) | 29% |
| Community & social impact | 36% | 67% (2022) | 54% |
| Employees & talent | 41% | 57% (2021–22) | 44% |
| Environment & climate | 13% | 29% (2023–24) | 29% |

The DEI rise starts after mid-2020 and the decline after 2023. That timing matches the 2020 racial-justice
movement and the 2023 Supreme Court affirmative-action ruling, followed by organised pressure on
corporate DEI. Climate language rose and has so far held its gain.

**Change is bursty, not gradual.** Most page edits are redesigns or small rewording. Counting
only major rewrites on the same URL, about **20% of firm-years** show a real change in stated
values. The share peaked in **2021 (31%)** and fell to **8% in 2022**. Of the 45 firms with
enough data, 32 changed in a few discrete jumps, 9 were essentially stable, 3 changed gradually
and 1 was volatile.

**Illustrative cases** (as seen in the archived pages):

* **Stable anchors.** Johnson & Johnson's *Our Credo* and Medtronic's mission are essentially unchanged across the
  period, and Home Depot's values list barely moves.
* **Crisis-era rewriting.** Wells Fargo's 2017 page acknowledges the sales-practices scandal, and in
  2018 the values were rewritten with integrity, employees and diversity raised to top emphasis.
  The dedicated values page was retired around 2020.
* **Repositioning around purpose.** Occidental's 2021 "Oxy" rewrite moved from integrity and
  shareholder language to emissions reduction and energy for society. Chevron's page was rebuilt
  around purpose and "human ingenuity" in 2021, and Starbucks replaced its values list with a
  heritage narrative in 2022.

## How much to trust this

Each page was coded independently by an AI model on 12 value themes. A second, independently
worded coding of 60 random pages agreed closely: weighted agreement (kappa) was 0.93–0.99 across
themes, with exact agreement on 87–98% of pages. The AI scores also track a simple keyword count
(correlations 0.57–0.88). The AI is deliberately stricter than the keywords, because it scores a
theme only when the company presents it as a value, not when a word merely appears.

**Main caveats.** A website is only one channel for stated values. Archive coverage is weakest for
JavaScript-heavy sites. And a few apparent changes coincide with a change of page rather than of
wording; these are flagged row by row in the dataset (`url_switched`, `analyst_notes`).

## What a reader can do with this

* Treat About pages as **positioning**: they show what a firm wants to be associated with, and
  that shifts with the public mood (DEI, climate). Part 3 tests whether the firm's own disclosures back it.
* Use the **timing** of rewrites. Firms that rewrote their values right after a scandal or a
  political shift are natural candidates for a closer look at whether practice followed.
* Prefer firms' **long-stable statements** (J&J, Medtronic, Home Depot) as reference points.
  A value that survives a decade of redesigns is more likely to be load-bearing than one added in
  a single year.
