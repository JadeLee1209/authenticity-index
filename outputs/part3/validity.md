# OAI validity checks (auto-generated)

## 1. Permutation test (own proxy vs. a random peer's proxy)

| shuffle_within   |   true_mean_oai |   null_mean |   null_sd |    z |   p_one_sided |
|:-----------------|----------------:|------------:|----------:|-----:|--------------:|
| year             |           39.69 |       38.2  |     0.275 | 5.41 |         0.001 |
| year+sector      |           39.69 |       39.25 |     0.244 | 1.82 |         0.035 |

Interpretation: z > 2 and small p mean firms' words are backed by their OWN disclosures more than by peers' - OAI captures firm-specific alignment rather than generic disclosure volume.

## 2. Known groups

| ticker   | theme               | years     | expectation   |   stated_salience |   backing_event |   backing_sector_peers |   backing_own_other_years | met_vs_peers   | met_vs_own_history   |
|:---------|:--------------------|:----------|:--------------|------------------:|----------------:|-----------------------:|--------------------------:|:---------------|:---------------------|
| WFC      | integrity_ethics    | 2016-2018 | low           |              2.33 |           0.54  |                  0.388 |                     0.522 | False          | False                |
| WFC      | customer_focus      | 2016-2018 | low           |              3    |           0.713 |                  0.384 |                     0.54  | False          | False                |
| META     | integrity_ethics    | 2018-2019 | low           |              0    |           0.342 |                  0.265 |                     0.355 | False          | True                 |
| META     | customer_focus      | 2018-2019 | low           |              1    |           0.701 |                  0.282 |                     0.266 | False          | False                |
| JNJ      | health_safety       | 2018-2020 | low           |              2    |           0.544 |                  0.293 |                     0.409 | False          | False                |
| JNJ      | integrity_ethics    | 2018-2020 | low           |              2    |           0.556 |                  0.329 |                     0.554 | False          | False                |
| XOM      | environment_climate | 2020-2022 | low           |              1.67 |           0.694 |                  0.534 |                     0.641 | False          | False                |
| BLK      | environment_climate | 2020-2022 | high          |              0    |           0.376 |                  0.338 |                     0.215 | True           | True                 |
| BLK      | purpose_mission     | 2020-2022 | high          |              2.67 |           0.24  |                  0.337 |                     0.215 | False          | True                 |

## 3. Robustness: rank correlation with variants

| variant         |   n |   spearman_firm_year |   spearman_firm_mean |
|:----------------|----:|---------------------:|---------------------:|
| disclosure_only | 390 |                0.873 |                0.849 |
| pay_only        | 390 |                0.528 |                0.575 |
| sector_peers    | 390 |                0.933 |                0.922 |
| lag_1           | 345 |                0.557 |                0.966 |
| no_imputation   | 384 |                1     |                1     |