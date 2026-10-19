#!/usr/bin/env bash
# Offline end-to-end test: synthetic data + mock LLM, written to a throwaway directory.
# Exercises every step except the two network downloaders. Usage: bash tests/run_offline_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export LLM_BACKEND=mock
export AUTH_DATA_DIR="${AUTH_DATA_DIR:-$(mktemp -d)/data}"
export AUTH_OUT_DIR="${AUTH_OUT_DIR:-$(dirname "$AUTH_DATA_DIR")/outputs}"
echo "demo data: $AUTH_DATA_DIR  outputs: $AUTH_OUT_DIR"

python tests/make_fixtures.py
python part1_stated_values/s3_extract_text.py
python part1_stated_values/s4_llm_analyze.py --reliability 20
python part1_stated_values/s5_build_dataset.py
python part2_lived_values/s3_parse_proxies.py
python part2_lived_values/s4_classical_nlp.py --topics 8
python part2_lived_values/s5_llm_analyze.py
python part2_lived_values/s6_build_dataset.py
python part2_lived_values/s7_event_analysis.py
python part3_authenticity_index/build_index.py
python part3_authenticity_index/validity.py
python part4_proposal/lead_lag.py
echo "OK - all stages ran. Outputs in $AUTH_OUT_DIR"
