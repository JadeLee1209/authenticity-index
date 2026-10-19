# Codebook — `outputs/part2/lived_values.csv`

One row per company × proxy filing year (50 × 9 = 450 rows, gaps included). `<theme>` stands for
each of the 12 theme ids in `config/themes.yaml`, so each templated column appears 12 times.
The reason for including each group is given in *italics*.

## Identifiers and provenance
| Column | Description |
|---|---|
| `ticker`, `company_name`, `sector` | From `config/companies.csv` (GICS sector as given in the assignment). |
| `year` | Calendar year in which the proxy was **filed**. |
| `fiscal_year_described` | `year − 1`; proxies filed in spring describe the previous fiscal year (approximate for off-calendar fiscal years, e.g. MDT, ORCL, NKE). *Needed to align with external events correctly.* |
| `status`, `missing_reason` | `ok` / `missing`; reasons: `no_def14a_filed_in_year`, `download_failed`. *Every gap is explicit.* |
| `filing_date`, `accession`, `url`, `cik` | EDGAR provenance; `url` opens the exact document analysed. *Reproducibility.* |
| `is_predecessor_cik` | Filed under a predecessor registrant (e.g. Broadcom Ltd before 2018). |
| `n_def14a_in_year` | Number of DEF 14A / DEFC14A filings assigned to that proxy year (Nov–Dec filings count toward the next year; >1 ⇒ special meeting; selection rule in README). |
| `annual_meeting_detected` | The kept document mentions an annual meeting in its opening text. *Selection audit.* |
| `download_note` | `used_largest_doc_in_filing` / `small_primary_doc` when the primary document looked like a cover only. |

## Document structure (from parsing)
| Column | Description |
|---|---|
| `n_words`, `n_prose_words` | Words in the whole document / in prose paragraphs (≥25 words). *Length controls; disclosure volume itself grew over the period.* |
| `n_paragraphs`, `n_prose`, `n_table_rows` | Parse counts. |
| `cda_found`, `cda_words` | Whether the Compensation Discussion & Analysis section was located, and its length. *Quality flag for the pay measures.* |
| `cda_suspect` | CD&A span < 2,500 or > 30,000 words: boundaries worth a manual look (pay metrics then read from the whole document if the span is short). |
| `layout_repaired` | Document typeset in layout tables or with lost line breaks; text repaired before analysis (see README). |

## Classical text measures (step 4)
| Column | Description |
|---|---|
| `dens_<theme>` | Theme-dictionary hits per 1,000 words, whole document. *Emphasis on each value theme on the same axes as Part 1.* |
| `cda_dens_<theme>` | Same within the CD&A only. *Is the theme part of how pay is justified?* |
| `ling_hedge_rate`, `ling_commit_rate` | Hedging ("aim", "strive", "may") vs. commitment ("will", "committed", "achieved", "target") words per 1,000 prose words. *Symbolic vs. committal language.* |
| `ling_number_rate` | Numbers, percentages and dollar amounts per 1,000 prose words. *Specificity proxy.* |
| `ling_we_rate`, `ling_future_rate`, `ling_fk_grade`, `ling_n_words`, `ling_n_sentences` | First-person plural rate, future orientation, Flesch-Kincaid grade, counts. |
| `lm_negative`, `lm_positive`, `lm_uncertainty`, `lm_litigious`, `lm_strong_modal`, `lm_weak_modal`, `lm_net_tone` | Loughran-McDonald finance sentiment per 1,000 prose words (only if the dictionary is supplied). *Tone measured with a lexicon validated on SEC filings.* |
| `sim_prior_year` | TF-IDF cosine similarity with the same firm's previous-year proxy. *Boilerplate stickiness; low values = real rewriting.* |
| `outputs/part2/doc_topics.csv` | NMF topic shares (T00…), with top terms in `topics_top_words.csv`. *Unsupervised check on what the taxonomy might miss.* |

## LLM measures (step 5)
| Column | Description |
|---|---|
| `npass_<theme>` | Number of sampled passages the LLM labelled with the theme. |
| `subst_ratio_<theme>` | Share of those passages that are substantive (quantified outcome, concrete action or governance mechanism) rather than aspirational or boilerplate. *Separates talk from evidence inside the disclosure itself.* |
| `subst_ratio_all` | Same across all sampled passages. |
| `subst_dens_<theme>` | `dens_<theme> × subst_ratio_<theme>` (fallback: document-level, then corpus-level ratio; 0 when density is 0). *Main disclosure-based lived-value measure: emphasis × quality.* |
| `pay_w_<theme>` | Share of incentive-pay weight tied to metrics in the theme; annual and long-term plans averaged equally; sums to 1 across themes when metrics exist. *The most behavioural signal in a proxy: what the board actually rewards.* |
| `pay_mod_<theme>` | 1 if a payout **modifier** (±adjustment) is tied to the theme. |
| `pay_n_metrics`, `pay_n_nonfinancial` | Number of incentive metrics extracted; how many are non-financial. |
| `pay_has_nonfin_metric` | Any core metric in a non-financial value theme. |
| `pay_has_strategic` | Plan includes an individual/strategic-objectives component. |

Long-format companions: `pay_metrics_long.csv` (one row per extracted metric with name, plan,
weight, kind, theme), `data/interim/part2/llm_passages.csv` (every labelled passage with its text),
`event_shifts.csv` (step 7).
