"""Text normalisation, similarity, and interpretable linguistic features.

The linguistic features are deliberately simple, transparent lexicon counts. They complement the
LLM's qualitative reading with numbers that are reproducible, cheap and easy to audit.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# Hedging / aspirational vs. commitment / concrete language. Based on the hedging literature
# (Hyland 1998) and corporate "cheap talk" work that treats specificity and quantification as
# markers of substantive rather than symbolic disclosure (e.g. Hope, Hu & Lu 2016 on boilerplate).
HEDGES = {"may", "might", "could", "aim", "aims", "aspire", "aspires", "strive", "strives",
          "seek", "seeks", "hope", "hopes", "believe", "believes", "endeavor", "endeavour",
          "intend", "intends", "potentially", "generally", "typically", "approximately",
          "wish", "envision", "ambition", "aspiration"}
COMMITMENTS = {"will", "must", "commit", "commits", "committed", "commitment", "require",
               "requires", "required", "ensure", "ensures", "guarantee", "achieved", "reduced",
               "increased", "target", "targets", "measured", "tracked", "audited"}
FIRST_PERSON_PLURAL = {"we", "our", "us", "ours", "ourselves"}
FUTURE = {"will", "shall", "going", "future", "tomorrow", "next", "aim", "goal", "goals"}
NUM_RE = re.compile(r"(?<![A-Za-z])(\d[\d,.]*\s?%?|\$\s?\d[\d,.]*)")


def normalize(text: str) -> str:
    """NFKC, unify quotes/dashes, collapse whitespace - used before any comparison."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[–—]", "-", t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text or "")]


def shingles(text: str, k: int = 5) -> set:
    w = words(text)
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def jaccard(a: str, b: str, k: int = 5) -> float:
    sa, sb = shingles(a, k), shingles(b, k)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def seq_ratio(a: str, b: str) -> float:
    """Word-level SequenceMatcher ratio (order-aware, robust to small edits)."""
    return difflib.SequenceMatcher(None, words(a), words(b), autojunk=False).ratio()


def text_similarity(a: str, b: str) -> float:
    """Average of an order-aware and an order-free similarity. 1 = identical text."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 0.5 * seq_ratio(a, b) + 0.5 * jaccard(a, b)


def diff_summary(a: str, b: str, max_lines: int = 40) -> str:
    """Compact sentence-level unified diff, fed to the LLM so it reasons about the actual edit."""
    sa = re.split(r"(?<=[.!?])\s+|\n+", a or "")
    sb = re.split(r"(?<=[.!?])\s+|\n+", b or "")
    out = [l for l in difflib.unified_diff(sa, sb, lineterm="", n=0)
           if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    return "\n".join(out[:max_lines]) + ("\n[... diff truncated]" if len(out) > max_lines else "")


def _syllables(word: str) -> int:
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 else 0)
    return max(1, n)


def linguistic_features(text: str) -> dict:
    """Interpretable per-document features (rates per 1,000 words unless noted)."""
    w = words(text)
    n = max(1, len(w))
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
    syl = sum(_syllables(x) for x in w)
    fk = 0.39 * (n / max(1, len(sents))) + 11.8 * (syl / n) - 15.59 if w else None
    return {
        "n_words": len(w),
        "n_sentences": len(sents),
        "fk_grade": round(fk, 2) if fk is not None else None,       # Flesch-Kincaid grade
        "hedge_rate": round(1000 * sum(x in HEDGES for x in w) / n, 2),
        "commit_rate": round(1000 * sum(x in COMMITMENTS for x in w) / n, 2),
        "we_rate": round(1000 * sum(x in FIRST_PERSON_PLURAL for x in w) / n, 2),
        "future_rate": round(1000 * sum(x in FUTURE for x in w) / n, 2),
        "number_rate": round(1000 * len(NUM_RE.findall(text or "")) / n, 2),  # specificity proxy
    }
