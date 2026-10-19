"""Theme taxonomy helpers: loading, regex dictionaries, and prompt rendering.

The same compiled dictionaries power (a) classical dictionary measures, (b) passage retrieval
for the LLM in Part 2, and (c) the offline mock LLM, so the three are consistent by construction.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .config import load_yaml


@lru_cache(maxsize=1)
def taxonomy() -> dict:
    return load_yaml("themes.yaml")


def theme_ids() -> list[str]:
    return list(taxonomy()["themes"].keys())


@lru_cache(maxsize=1)
def compiled() -> dict[str, re.Pattern]:
    """One alternation regex per theme, word-bounded and case-insensitive."""
    pats = {}
    for tid, spec in taxonomy()["themes"].items():
        alts = "|".join(f"(?:{k})" for k in spec["keywords"])
        # \b on both sides stops acronyms (DEI, GHG, TSR) matching inside longer words.
        pats[tid] = re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)
    return pats


def theme_hits(text: str) -> dict[str, int]:
    """Raw keyword hit counts per theme."""
    return {tid: len(p.findall(text)) for tid, p in compiled().items()}


def theme_density(text: str, n_words: int | None = None) -> dict[str, float]:
    """Hits per 1,000 words - comparable across documents of very different length."""
    n = n_words if n_words is not None else max(1, len(text.split()))
    return {tid: 1000 * c / max(n, 1) for tid, c in theme_hits(text).items()}


def themes_prompt_block() -> str:
    """Render the taxonomy for inclusion in an LLM prompt."""
    lines = []
    for tid, spec in taxonomy()["themes"].items():
        lines.append(f"- {tid}: {spec['label']}. {spec['definition']}")
    return "\n".join(lines)


def salience_scale_block() -> str:
    return "\n".join(f"{k} = {v}" for k, v in taxonomy()["salience_scale"].items())
