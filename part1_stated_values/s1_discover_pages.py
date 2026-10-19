"""Part 1, step 1 - Identify the "About Us / values" page for each company.

Input : config/companies.csv  (curated seed URLs + company domains)
        config/page_overrides.csv (optional; ticker,url - forces a primary page after review)
Output: data/interim/part1/page_candidates.csv  every candidate URL with its score components
        data/interim/part1/page_selection.csv   ranked candidate list per company (primary first)
        data/interim/part1/cdx/<TICKER>/...      cached CDX listings (reused by step 2)

Page-identification criteria (documented in README, "Which page counts?"):
  We want the page where the company states WHO IT IS and WHAT IT VALUES, and we want the SAME
  page across years where possible, because a change of page would masquerade as a change of
  values. Candidates come from (a) hand-curated seeds and (b) automatic discovery of archived URLs
  in the same directory as each seed whose path contains values-related words (whole-domain scans
  are avoided: on large sites they time out on the CDX server). Each candidate is scored:

    keyword score   values|credo|principles|mission|purpose|spirit|way = 3,
                    who-we-are|about-us|about|company-info = 2, our-company|company|culture = 1
    seed bonus      +2 (curated by a human reading the live site / press coverage)
    coverage        +4 * (years 2016-2024 with a usable capture) / 9
    penalties       -3 for careers/news/investor/leadership/history/contact/locations pages,
                    -5 for non-English locale, -2 for query strings, -1 per path depth beyond 4

  The top-ranked candidate is the primary page; the rest are fallbacks used only for years in
  which the primary has no usable capture (step 2 flags those years as url_switched).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import CONFIG_DIR, YEARS, interim_dir, load_companies
from authenticity.http import PoliteSession
from authenticity.wayback import CDXUnavailable, cdx_query, host_of

KW3 = re.compile(r"values|credo|principles|mission|purpose|spirit|the-[a-z]+-way|philosophy", re.I)
KW2 = re.compile(r"who-?we-?are|about-?us|about|company-?info", re.I)
KW1 = re.compile(r"our-?company|company|culture|corporate", re.I)
PENALTY = re.compile(r"career|jobs?\b|news|press|media|investor|leadership|board|executive|"
                     r"history|contact|locations?|events?|blog|stories|search|login|privacy|"
                     r"terms|sitemap|supplier|esg-report|annual-report", re.I)
LOCALE_SEG = re.compile(r"^[a-z]{2}[-_][a-z]{2}$", re.I)
DISCOVERY_REGEX = r"original:.*(about|values|mission|purpose|who-we-are|our-company|credo|principles|company-info|culture).*"


def usable(row: dict) -> bool:
    """A capture is usable if it returned content (200) or is a WARC revisit (same bytes as an
    earlier 200, status '-'), or a redirect (3xx) that step 2 may be able to follow."""
    return row.get("statuscode", "") in ("200", "-") or row.get("statuscode", "").startswith("3")


def years_covered(rows: list[dict]) -> list[int]:
    ys = {int(r["timestamp"][:4]) for r in rows if usable(r)}
    return sorted(y for y in ys if y in YEARS)


def keyword_score(url: str) -> int:
    path = url.split("/", 1)[1] if "/" in url else ""
    if KW3.search(path):
        return 3
    if KW2.search(path):
        return 2
    if KW1.search(path):
        return 1
    return 0


def structural_penalty(url: str) -> float:
    p = 0.0
    path = "/" + (url.split("/", 1)[1] if "/" in url else "")
    if PENALTY.search(path):
        p -= 3
    # A locale segment like fr-fr / de-de / ja-jp that does not include "en" -> non-English page
    if any(LOCALE_SEG.match(s) and "en" not in s.lower().replace("_", "-").split("-")
           for s in path.split("/")):
        p -= 5
    if "?" in url:
        p -= 2
    depth = len([s for s in path.split("?")[0].split("/") if s])
    p -= max(0, depth - 4)
    return p


def canonical(url: str) -> str:
    """Strip scheme, www, trailing slash, and fragments so near-duplicates collapse."""
    u = re.sub(r"^https?://", "", url.strip(), flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I).split("#")[0]
    u = re.sub(r":80(?=/)", "", u)
    host, _, path = u.partition("/")
    return (host.lower() + ("/" + path if path else "")).rstrip("/")


def cdx_cached(sess, ticker: str, url: str) -> list[dict]:
    """CDX listing for one exact URL, cached as JSON for reuse in step 2."""
    d = interim_dir("part1", "cdx", ticker.replace(".", "_"))
    fn = d / (re.sub(r"[^A-Za-z0-9]+", "_", canonical(url))[:150] + ".json")
    if fn.exists():
        rows = json.loads(fn.read_text(encoding="utf-8"))
        if rows:  # an empty cached list may stem from an earlier outage -> ask again
            return rows
    try:
        rows = cdx_query(sess, url)
    except CDXUnavailable as e:
        print(f"   WARNING {e} - treated as no captures for now; re-run later to retry")
        return []  # not cached, so the next run retries
    fn.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def discovery_roots(seed: str) -> list[str]:
    """Where to look for sibling pages of a seed URL: its parent directory, or - for a top-level
    seed like jnj.com/credo - the seed itself. Never the whole domain: a prefix scan of
    microsoft.com covers millions of captures and routinely times out on the CDX server."""
    host, _, path = seed.partition("/")
    segs = [x for x in path.split("/") if x]
    if len(segs) >= 2:
        return [host + "/" + "/".join(segs[:-1]) + "/"]
    return [seed.rstrip("/") + "/"] if segs else []


def discover(sess, root: str, limit: int = 500) -> list[str]:
    """Archived URLs under `root` whose path looks like an about/values page."""
    rows = cdx_query(sess, root, match_type="prefix", collapse="urlkey",
                     filters=[DISCOVERY_REGEX, "statuscode:200", "mimetype:text/html"],
                     limit=limit, fields=["original", "timestamp"])
    return sorted({canonical(r["original"]) for r in rows})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*", help="restrict to these tickers")
    ap.add_argument("--no-discovery", action="store_true", help="use seed URLs only")
    ap.add_argument("--max-discovered", type=int, default=8,
                    help="top-N discovered URLs (by keyword score) to check for coverage")
    args = ap.parse_args(argv)

    sess = PoliteSession()
    # Discovery is optional, so it gets a short leash: give up quickly instead of waiting out
    # long back-offs on a slow prefix query.
    fast = PoliteSession(max_retries=2, timeout=40)
    cos = load_companies()
    t0 = time.time()
    if args.tickers:
        cos = cos[cos.ticker.isin(args.tickers)]
    overrides = {}
    ov_path = CONFIG_DIR / "page_overrides.csv"
    if ov_path.exists():
        ov = pd.read_csv(ov_path, dtype=str, comment="#").dropna()
        overrides = dict(zip(ov.ticker, ov.url))

    cand_rows, sel_rows = [], []
    for i, (_, co) in enumerate(cos.iterrows(), 1):
        print(f"[{co.ticker}] ({i}/{len(cos)}, {(time.time() - t0) / 60:.0f} min elapsed) "
              f"finding candidate pages", flush=True)
        seeds = [canonical(u) for u in co.seed_urls]
        if overrides.get(co.ticker):  # a reviewed override is always a candidate
            seeds = list(dict.fromkeys([canonical(overrides[co.ticker])] + seeds))
        discovered: list[str] = []
        if not args.no_discovery:
            roots = list(dict.fromkeys(r for u in seeds for r in discovery_roots(u)))
            for root in roots:
                try:
                    discovered += discover(fast, root)
                except Exception as e:  # discovery is best-effort; seeds still work
                    print(f"   discovery skipped for {root}: {e}", flush=True)
        # Only check coverage for the most promising discovered URLs (CDX calls are slow).
        discovered = [u for u in dict.fromkeys(discovered) if u not in seeds]
        discovered.sort(key=lambda u: (keyword_score(u) + structural_penalty(u)), reverse=True)
        discovered = discovered[: args.max_discovered]

        scored = []
        for url, is_seed in [(u, True) for u in seeds] + [(u, False) for u in discovered]:
            rows = cdx_cached(sess, co.ticker, url)
            yrs = years_covered(rows)
            ks, pen = keyword_score(url), structural_penalty(url)
            cov = 4 * len(yrs) / len(YEARS)
            score = ks + pen + cov + (2 if is_seed else 0)
            if overrides.get(co.ticker) and canonical(overrides[co.ticker]) == url:
                score += 100  # human override always wins
            rec = dict(ticker=co.ticker, url=url, host=host_of(url), is_seed=is_seed,
                       keyword_score=ks, penalty=pen, coverage_score=round(cov, 2),
                       n_years=len(yrs), years=";".join(map(str, yrs)), n_captures=len(rows),
                       score=round(score, 2))
            scored.append(rec)
        cand_rows += scored
        ranked = sorted([r for r in scored if r["n_years"] > 0], key=lambda r: -r["score"])
        sel_rows.append(dict(
            ticker=co.ticker,
            primary_url=ranked[0]["url"] if ranked else "",
            primary_years=ranked[0]["years"] if ranked else "",
            ranked_urls=";".join(r["url"] for r in ranked),
            n_candidates_with_captures=len(ranked),
            note=co.notes,
        ))

    out = interim_dir("part1")
    cand, sel = pd.DataFrame(cand_rows), pd.DataFrame(sel_rows)
    if args.tickers:  # partial re-run: replace only these firms, keep everyone else
        for name, new in (("page_candidates.csv", cand), ("page_selection.csv", sel)):
            if (out / name).exists():
                old = pd.read_csv(out / name, dtype=str)
                new = pd.concat([old[~old.ticker.isin(args.tickers)], new], ignore_index=True)
            if name == "page_candidates.csv":
                cand = new
            else:
                sel = new
    cand.to_csv(out / "page_candidates.csv", index=False)
    sel.to_csv(out / "page_selection.csv", index=False)
    print(f"wrote {out/'page_selection.csv'} - REVIEW IT; add config/page_overrides.csv to fix picks")


if __name__ == "__main__":
    main()
