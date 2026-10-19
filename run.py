"""Cross-platform entry point (Windows / macOS / Linux, PyCharm terminal or Run button).

    python run.py test      offline end-to-end check (synthetic data, mock LLM, no API cost)
    python run.py check     verify .env, API key and network access to Wayback / EDGAR
    python run.py part1     (part2, part3, part4, all)
    python run.py part1 --from 3     resume Part 1 from step 3
    python run.py part1 --tickers WFC NVDA   re-collect only these firms (after editing
                                             config/page_overrides.csv), then rebuild everything

Reads settings from .env in this folder (no need to `source` it).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = {
    "part1": ["part1_stated_values/s1_discover_pages.py",
              "part1_stated_values/s2_collect_snapshots.py",
              "part1_stated_values/s3_extract_text.py",
              "part1_stated_values/s4_llm_analyze.py --reliability 60",
              "part1_stated_values/s5_build_dataset.py"],
    "part2": ["part2_lived_values/s1_edgar_index.py",
              "part2_lived_values/s2_download_proxies.py",
              "part2_lived_values/s3_parse_proxies.py",
              "part2_lived_values/s4_classical_nlp.py",
              "part2_lived_values/s5_llm_analyze.py",
              "part2_lived_values/s6_build_dataset.py",
              "part2_lived_values/s7_event_analysis.py"],
    "part3": ["part3_authenticity_index/build_index.py",
              "part3_authenticity_index/validity.py"],
    "part4": ["part4_proposal/lead_lag.py"],
}
TEST_STEPS = ["tests/make_fixtures.py",
              "part1_stated_values/s3_extract_text.py",
              "part1_stated_values/s4_llm_analyze.py --reliability 20",
              "part1_stated_values/s5_build_dataset.py",
              "part2_lived_values/s3_parse_proxies.py",
              "part2_lived_values/s4_classical_nlp.py --topics 8",
              "part2_lived_values/s5_llm_analyze.py",
              "part2_lived_values/s6_build_dataset.py",
              "part2_lived_values/s7_event_analysis.py",
              "part3_authenticity_index/build_index.py",
              "part3_authenticity_index/validity.py",
              "part4_proposal/lead_lag.py"]


def load_env() -> dict:
    env = dict(os.environ)
    f = ROOT / ".env"
    if not f.exists():
        return env
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def run_steps(steps: list[str], env: dict) -> None:
    # PYTHONUTF8=1: on Chinese-locale Windows the default file encoding is GBK, which cannot
    # write characters like (c) or curly quotes found in web pages. Force UTF-8 everywhere.
    env = {**env, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    for s in steps:
        script, *args = s.split()
        print(f"\n=== {script} {' '.join(args)}", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, env=env)
        if r.returncode != 0:
            sys.exit(f"\nFAILED at {script}. Fix the error above, then resume with --from.")


def check(env: dict) -> None:
    ok = True
    key = env.get("ANTHROPIC_API_KEY", "")
    print(f"ANTHROPIC_API_KEY: {'set' if key.startswith('sk-ant') else 'MISSING or placeholder'}")
    ua = env.get("SEC_USER_AGENT", "")
    print(f"SEC_USER_AGENT:    {ua if '@' in ua and 'your.email' not in ua else 'MISSING - needs your name and real e-mail'}")
    ok &= key.startswith("sk-ant") and "@" in ua and "your.email" not in ua
    import requests
    for name, url in [("Wayback", "https://web.archive.org/cdx/search/cdx?url=jnj.com/credo&limit=1"),
                      ("EDGAR", "https://data.sec.gov/submissions/CIK0000200406.json")]:
        try:
            r = requests.get(url, headers={"User-Agent": ua or "test"}, timeout=20)
            print(f"{name:8} HTTP {r.status_code}")
            ok &= r.status_code == 200
        except Exception as e:  # noqa: BLE001
            print(f"{name:8} FAILED: {e}")
            ok = False
    if key.startswith("sk-ant"):
        try:
            import anthropic
            m = anthropic.Anthropic(api_key=key).messages.create(
                model=env.get("LLM_MODEL", "claude-haiku-5-5"), max_tokens=5,
                messages=[{"role": "user", "content": "Say ok"}])
            print(f"Claude API: OK ({m.model})")
        except Exception as e:  # noqa: BLE001
            print(f"Claude API: FAILED: {e}")
            ok = False
    print("\nAll good - ready to run part1." if ok else "\nFix the items above first.")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("test", "check", "all", *STEPS):
        sys.exit(__doc__)
    cmd = sys.argv[1]
    start = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 1
    env = load_env()
    if cmd == "check":
        check(env)
    elif cmd == "test":
        tmp = Path(tempfile.mkdtemp(prefix="oai_demo_"))
        env.update(LLM_BACKEND="mock", AUTH_DATA_DIR=str(tmp / "data"), AUTH_OUT_DIR=str(tmp / "outputs"))
        run_steps(TEST_STEPS, env)
        print(f"\nOK - all stages ran on synthetic data. Look at the outputs in:\n{tmp / 'outputs'}")
    elif cmd == "part1" and "--tickers" in sys.argv:
        i = sys.argv.index("--tickers") + 1
        tickers = []
        while i < len(sys.argv) and not sys.argv[i].startswith("--"):
            tickers.append(sys.argv[i])
            i += 1
        t = " ".join(tickers)
        # Overrides need no auto-discovery; steps 3-5 re-run for all firms but reuse caches,
        # so only the changed firms cost new downloads / LLM calls.
        steps = [f"{STEPS['part1'][0]} --no-discovery --tickers {t}",
                 f"{STEPS['part1'][1]} --tickers {t}"] + STEPS["part1"][2:]
        run_steps(steps, env)
        print(f"\nDone. Results in {ROOT / 'outputs'}")
    else:
        parts = list(STEPS) if cmd == "all" else [cmd]
        for p in parts:
            steps = STEPS[p][start - 1:] if len(parts) == 1 else STEPS[p]
            run_steps(steps, env)
        print(f"\nDone. Results in {ROOT / 'outputs'}")


if __name__ == "__main__":
    main()
