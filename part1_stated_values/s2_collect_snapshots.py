"""Part 1, step 2 - Collect one archived snapshot per company-year (2016-2024).

Input : data/interim/part1/page_selection.csv (+ cached CDX listings from step 1)
Output: data/raw/wayback/<TICKER>/<YEAR>.html     original archived bytes (id_ playback)
        data/interim/part1/snapshot_manifest.csv  one row per company-year, incl. every gap reason

Snapshot selection rule
  For year Y the target date is Y-07-01. We walk the company's ranked URLs (primary first) and,
  for each URL, try that year's captures in order of distance from the target date - at most
  `--tries` (default 5) captures per URL. Status 200 and WARC revisits ('-', byte-identical to an earlier
  200) are preferred over redirects. The first capture that passes ALL checks below is kept.

Redirect-chain rule (a 3xx capture, or a 200 whose playback redirects)
  * follow up to 5 hops;
  * the final URL must stay on the company's own domains (domain + alt_domains, any subdomain);
    e.g. google.com/about/philosophy.html -> about.google/philosophy/ is accepted, a redirect to
    a third-party site or a cookie wall is not;
  * the final URL must NOT be a homepage/locale root - a retired page bouncing to '/' is
    recorded as `redirect_to_homepage`, not as the About page;
  * the final URL must not be a non-English version the original was not (e.g. /about ->
    /es/about/ happens when the crawler carried a Spanish-language cookie) - `redirect_to_other_language`;
  * the capture actually served must fall in the same calendar year Y (Wayback serves the
    nearest capture of the redirect target, which can be years away) - else `capture_outside_year`.

Readable-text rule
  A capture must yield >= 40 words of body text with the step-3 extractor. JavaScript-rendered
  pages often archive as empty shells; rejecting them here (`no_extractable_text`) lets the
  next capture or a fallback URL fill the year instead of leaving an empty text downstream.

Blocklist
  config/url_blocklist.csv (ticker,url_prefix,reason) lists fallback URLs that a human review
  found are not About/values pages (press releases, product, legal or CSR-report pages). They
  are never used; a year with no other valid page stays missing rather than being filled with
  an off-topic page.

Error-page rule
  A capture with HTTP 200 whose <title>, first <h1> or opening text says "page not found" /
  "something has gone wrong" (a retired page served as an error page, a "soft 404") is
  rejected as `soft_404`, so the next capture or the
  fallback URL is tried instead.

Missing-snapshot rule
  If no URL yields a valid capture for Y the row is kept with status='missing' and a reason code.
  We do NOT borrow neighbouring years here: imputation is a modelling choice made explicitly
  (and flagged) downstream in Part 3, never silently in the raw data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import (CONFIG_DIR, TARGET_MONTH_DAY, YEARS, interim_dir,
                                 load_companies, raw_dir)
from authenticity.http import PoliteSession
from authenticity.wayback import (foreign_locale, host_allowed, is_homepage, parse_wayback_url,
                                  playback_url, soft_404, ts_to_dt)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1_discover_pages import canonical, cdx_cached  # noqa: E402
from s3_extract_text import MIN_WORDS as MIN_TEXT_WORDS, extract, is_error_text  # noqa: E402

from authenticity.textutils import words  # noqa: E402

MIN_BYTES = 1500  # smaller bodies are error stubs / empty JS shells


def ranked_captures(rows: list[dict], year: int) -> list[dict]:
    target = ts_to_dt(f"{year}{TARGET_MONTH_DAY}000000")
    rows = [r for r in rows if r["timestamp"].startswith(str(year))]

    def key(r):
        good = r["statuscode"] in ("200", "-")
        return (0 if good else 1, abs((ts_to_dt(r["timestamp"]) - target).total_seconds()))

    return sorted([r for r in rows if r["statuscode"] in ("200", "-")
                   or r["statuscode"].startswith("3")], key=key)


def try_capture(sess, row: dict, year: int, domains: list[str], allow_home: bool) -> dict:
    """Fetch one capture and apply the acceptance rules. Returns a result dict with
    ok=True/False and a reason code."""
    url = playback_url(row["timestamp"], row["original"])
    r = sess.get(url)
    hops = [h[1] for h in r.history]
    final_ts, final_orig = parse_wayback_url(r.final_url)
    res = dict(requested=row["original"], cdx_ts=row["timestamp"], cdx_status=row["statuscode"],
               http_status=r.status, final_url=final_orig, capture_ts=final_ts or row["timestamp"],
               n_redirects=len(hops), redirect_chain=" -> ".join(parse_wayback_url(h)[1] for h in hops))
    if r.status == 0:
        return {**res, "ok": False, "reason": "network_error"}
    if r.status != 200:
        return {**res, "ok": False, "reason": f"http_{r.status}"}
    if len(hops) > 5:
        return {**res, "ok": False, "reason": "redirect_chain_too_long"}
    if not host_allowed(final_orig, domains):
        return {**res, "ok": False, "reason": "redirect_offsite"}
    if hops and is_homepage(final_orig) and not allow_home:
        return {**res, "ok": False, "reason": "redirect_to_homepage"}
    if hops and foreign_locale(final_orig) and not foreign_locale(row["original"]):
        # e.g. wellsfargo.com/about -> wellsfargo.com/es/about/ (crawler got the Spanish site)
        return {**res, "ok": False, "reason": "redirect_to_other_language"}
    if not str(res["capture_ts"]).startswith(str(year)):
        return {**res, "ok": False, "reason": "capture_outside_year"}
    ctype = r.headers.get("Content-Type", r.headers.get("content-type", ""))
    if ctype and "html" not in ctype.lower():
        return {**res, "ok": False, "reason": f"non_html:{ctype.split(';')[0]}"}
    if len(r.content) < MIN_BYTES:
        return {**res, "ok": False, "reason": "empty_body"}
    if soft_404(r.content):
        # HTTP 200 but the page says "Page not found" - a retired page served as an error page
        return {**res, "ok": False, "reason": "soft_404"}
    text, _ = extract(r.content.decode("utf-8", errors="replace"))
    if is_error_text(text):
        # Error message in the page body (e.g. "We're sorry - something has gone wrong")
        return {**res, "ok": False, "reason": "soft_404"}
    if len(words(text)) < MIN_TEXT_WORDS:
        # Archived, but no readable text (typically a JavaScript-rendered page whose content
        # the crawler never saw). Reject now so another capture or fallback URL can be tried.
        return {**res, "ok": False, "reason": "no_extractable_text"}
    return {**res, "ok": True, "reason": "", "_content": r.content}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--tries", type=int, default=5, help="captures tried per URL per year")
    args = ap.parse_args(argv)

    sess = PoliteSession()
    cos = load_companies().set_index("ticker")
    sel = pd.read_csv(interim_dir("part1") / "page_selection.csv", dtype=str).fillna("")
    # Reviewed exclusions: fallback pages that are not About/values pages (press releases,
    # product pages, legal pages, CSR reports). Each line is a URL prefix; see README.
    blocklist: dict[str, list[str]] = {}
    bl_path = CONFIG_DIR / "url_blocklist.csv"
    if bl_path.exists():
        bl = pd.read_csv(bl_path, dtype=str, comment="#").dropna(subset=["ticker", "url_prefix"])
        for tk, pre in zip(bl.ticker, bl.url_prefix):
            blocklist.setdefault(tk.strip(), []).append(canonical(pre).lower())
    if args.tickers:
        sel = sel[sel.ticker.isin(args.tickers)]

    manifest = []
    for _, s in sel.iterrows():
        co = cos.loc[s.ticker]
        domains = [co.domain] + co.alt_domains
        urls = [u for u in s.ranked_urls.split(";") if u]
        blocked = [u for u in urls if any(u.lower().startswith(b) for b in blocklist.get(s.ticker, []))]
        urls = [u for u in urls if u not in blocked]
        if blocked:
            print(f"   blocklisted {len(blocked)} URL(s): {', '.join(b[:60] for b in blocked)}")
        allow_home = any(is_homepage("http://" + u) for u in co.seed_urls[:1])  # e.g. BRK
        out_dir = raw_dir("wayback", s.ticker.replace(".", "_"))
        print(f"[{s.ticker}] {len(urls)} candidate URLs", flush=True)

        for year in YEARS:
            attempts, kept = [], None
            for rank, u in enumerate(urls):
                rows = cdx_cached(sess, s.ticker, u)
                for cap in ranked_captures(rows, year)[: args.tries]:
                    res = try_capture(sess, cap, year, domains, allow_home)
                    attempts.append(f"{rank}:{cap['timestamp']}:{res['reason'] or 'ok'}")
                    if res["ok"]:
                        kept = {**res, "url_rank": rank, "page_url": canonical(u)}
                        break
                if kept:
                    break
            row = dict(ticker=s.ticker, year=year, primary_url=s.primary_url,
                       attempts=" | ".join(attempts))
            if kept:
                html_path = out_dir / f"{year}.html"
                html_path.write_bytes(kept.pop("_content"))
                row.update(status="ok", html_path=str(html_path),
                           url_switched=kept["url_rank"] > 0, **kept)
            else:
                # Most informative reason: no captures at all vs. captures that all failed checks
                reasons = [a.split(":")[-1] for a in attempts]
                why = "no_capture_in_year" if not attempts else \
                    max(set(reasons), key=reasons.count)
                row.update(status="missing", missing_reason=why)
            manifest.append(row)
            print(f"   {year}: {row['status']} {row.get('missing_reason', row.get('page_url', ''))}")

    out = interim_dir("part1") / "snapshot_manifest.csv"
    df = pd.DataFrame(manifest)
    if out.exists() and args.tickers:  # partial re-run: merge into existing manifest
        old = pd.read_csv(out, dtype={"year": int})
        df = pd.concat([old[~old.ticker.isin(args.tickers)], df], ignore_index=True)
    df.sort_values(["ticker", "year"]).to_csv(out, index=False)
    ok = (df.status == "ok").mean()
    print(f"wrote {out}  coverage={ok:.1%} of {len(df)} company-years")


if __name__ == "__main__":
    main()
