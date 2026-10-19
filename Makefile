# Pipeline entry points. Load credentials first:  set -a && source .env && set +a
PY ?= python

.PHONY: test part1 part2 part3 part4 all

test:            ## offline end-to-end run on synthetic data with the mock LLM
	bash tests/run_offline_demo.sh

part1:
	$(PY) part1_stated_values/s1_discover_pages.py
	$(PY) part1_stated_values/s2_collect_snapshots.py
	$(PY) part1_stated_values/s3_extract_text.py
	$(PY) part1_stated_values/s4_llm_analyze.py --reliability 60
	$(PY) part1_stated_values/s5_build_dataset.py

part2:
	$(PY) part2_lived_values/s1_edgar_index.py
	$(PY) part2_lived_values/s2_download_proxies.py
	$(PY) part2_lived_values/s3_parse_proxies.py
	$(PY) part2_lived_values/s4_classical_nlp.py
	$(PY) part2_lived_values/s5_llm_analyze.py
	$(PY) part2_lived_values/s6_build_dataset.py
	$(PY) part2_lived_values/s7_event_analysis.py

part3:
	$(PY) part3_authenticity_index/build_index.py
	$(PY) part3_authenticity_index/validity.py

part4:
	$(PY) part4_proposal/lead_lag.py

all: part1 part2 part3 part4
