"""Paths, project-wide constants and config loaders.

Every script imports from here so the data layout is defined exactly once:

    data/raw/       untouched downloads (Wayback HTML, EDGAR filings)  - git-ignored
    data/interim/   intermediate artefacts (CDX listings, extracted text, LLM caches)
    outputs/partN/  deliverable datasets, figures and auto-generated digests

AUTH_DATA_DIR / AUTH_OUT_DIR env vars redirect both trees (used by the offline demo in tests/).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = Path(os.environ.get("AUTH_DATA_DIR", ROOT / "data"))
OUT_DIR = Path(os.environ.get("AUTH_OUT_DIR", ROOT / "outputs"))

RAW = DATA_DIR / "raw"
INTERIM = DATA_DIR / "interim"

YEARS = list(range(2016, 2025))  # 2016..2024 inclusive, 9 time points

# Snapshot target date within each year. Mid-year is chosen so the "year" label sits in the
# middle of the capture window and is roughly contemporaneous with proxy statements, which are
# mostly filed March-May (see part1 README, "Snapshot selection rule").
TARGET_MONTH_DAY = "0701"


def out_dir(part: str) -> Path:
    p = OUT_DIR / part
    p.mkdir(parents=True, exist_ok=True)
    return p


def interim_dir(*parts: str) -> Path:
    p = INTERIM.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_dir(*parts: str) -> Path:
    p = RAW.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_companies() -> pd.DataFrame:
    """The 50-firm sample with seed URLs. List-valued columns are split on ';'."""
    df = pd.read_csv(CONFIG_DIR / "companies.csv", dtype=str).fillna("")
    for col in ("seed_urls", "alt_domains", "predecessor_ciks"):
        df[col] = df[col].apply(lambda s: [x.strip() for x in s.split(";") if x.strip()])
    return df


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)
