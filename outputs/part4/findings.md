# Part 4 findings (auto-generated - interpret in SUMMARY.md)

## Lead-lag regressions (first differences, year+theme FE, firm-clustered SE)

| model                                            |    n |   n_firms |    coef |     se |     t |   own_lag_coef |   std_effect |
|:-------------------------------------------------|-----:|----------:|--------:|-------:|------:|---------------:|-------------:|
| A: talk -> walk (d_backing[t+1] ~ d_salience[t]) | 3504 |        47 |  0.0056 | 0.0046 |  1.21 |        -0.4381 |        0.018 |
| B: walk -> talk (d_salience[t+1] ~ d_backing[t]) | 3504 |        47 | -0.0135 | 0.0451 | -0.3  |        -0.1767 |       -0.004 |
| A [hot-button themes only]                       |  584 |        47 |  0.0285 | 0.0097 |  2.95 |        -0.4404 |        0.089 |
| B [hot-button themes only]                       |  584 |        47 |  0.1502 | 0.1246 |  1.2  |        -0.1384 |        0.047 |
| A [other themes]                                 | 2920 |        47 |  0.0019 | 0.0053 |  0.36 |        -0.4381 |        0.006 |
| B [other themes]                                 | 2920 |        47 | -0.0393 | 0.045  | -0.87 |        -0.1821 |       -0.012 |

## DEI retreat sequencing (firms whose stated DEI salience peaked >= 2)

Lived side = peer-relative backing (drop = 0.15 below peak):

| retreat_pattern   |   count |
|:------------------|--------:|
| talk_first        |      14 |
| no_retreat        |       6 |
| walk_first        |       5 |
| simultaneous      |       2 |

talk-first 14 vs walk-first 5: two-sided exact binomial p = 0.064

Robustness - lived side = ABSOLUTE substantive DEI disclosure (drop = below 80% of peak):

| retreat_pattern   |   count |
|:------------------|--------:|
| walk_first        |      12 |
| talk_first        |      12 |
| no_retreat        |       2 |
| simultaneous      |       1 |

talk-first 12 vs walk-first 12: two-sided exact binomial p = 1.000

## DEI series (index, each series' peak = 100)

|   year |   stated_salience |   raw_disclosure |   firms_with_dei_pay |
|-------:|------------------:|-----------------:|---------------------:|
|   2016 |              48.4 |             26   |                  0   |
|   2017 |              54.2 |             30   |                  0   |
|   2018 |              67.2 |             37.4 |                  0   |
|   2019 |              75.6 |             58.1 |                  0   |
|   2020 |              75.6 |             67.7 |                  0   |
|   2021 |              89.6 |            100   |                 12.5 |
|   2022 |             100   |             97.3 |                 76.7 |
|   2023 |              81.4 |             80.4 |                100   |
|   2024 |              75.6 |             67.2 |                 85.6 |