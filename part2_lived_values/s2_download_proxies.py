"""Part 2, step 2 - Download one annual-meeting proxy statement per company-year.

Input : data/interim/part2/proxy_index.csv
Output: data/raw/edgar/<TICKER>/<YEAR>.htm
        data/interim/part2/proxy_manifest.csv   one row per company-year (incl. gaps + reasons)

Selection rule when a firm files several DEF 14As in one calendar year:
  keep the one whose opening text mentions an "annual meeting" (special-meeting proxies are
  excluded); ties -> the largest document. Year = filing year (a proxy filed in spring Y mostly
  describes fiscal year Y-1; this lag is handled explicitly in Parts 2-3). "Year" is the proxy
  year from step 1: Nov/Dec filings count toward the next year's meeting.
If the primary document is suspiciously small (< 150 KB: cover letter / notice only), the filing's
index.json is read and the largest .htm in the filing is used instead.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import YEARS, interim_dir, load_companies, raw_dir
from authenticity.http import PoliteSession

SMALL = 150_000
ANNUAL = re.compile(r"annual\s+meeting", re.I)


def fetch_main_doc(sess, row) -> tuple[bytes, str, str]:
    r = sess.get(row.url)
    if r.status != 200:
        return b"", row.url, f"http_{r.status}"
    if len(r.content) >= SMALL:
        return r.content, row.url, ""
    idx = sess.get_json(row.index_url)
    items = (idx or {}).get("directory", {}).get("item", [])
    htms = [i for i in items if i["name"].lower().endswith((".htm", ".html"))]
    if htms:
        best = max(htms, key=lambda i: int(i.get("size") or 0))
        url = row.url.rsplit("/", 1)[0] + "/" + best["name"]
        r2 = sess.get(url)
        if r2.status == 200 and len(r2.content) > len(r.content):
            return r2.content, url, "used_largest_doc_in_filing"
    return r.content, row.url, "small_primary_doc"


def main():
    sess = PoliteSession()
    idx = pd.read_csv(interim_dir("part2") / "proxy_index.csv")
    rows = []
    for _, co in load_companies().iterrows():
        for y in YEARS:
            cands = idx[(idx.ticker == co.ticker) & (idx.filing_year == y)]
            base = dict(ticker=co.ticker, year=y, n_def14a_in_year=len(cands))
            if cands.empty:
                rows.append({**base, "status": "missing", "missing_reason": "no_def14a_filed_in_year"})
                continue
            docs = []
            for _, c in cands.iterrows():
                content, url, note = fetch_main_doc(sess, c)
                if content:
                    head = content[:200_000].decode("utf-8", errors="replace")
                    docs.append((bool(ANNUAL.search(head)), len(content), content, url, note, c))
            if not docs:
                rows.append({**base, "status": "missing", "missing_reason": "download_failed"})
                continue
            is_annual, size, content, url, note, c = max(docs, key=lambda d: (d[0], d[1]))
            path = raw_dir("edgar", co.ticker.replace(".", "_")) / f"{y}.htm"
            path.write_bytes(content)
            rows.append({**base, "status": "ok", "path": str(path), "url": url,
                         "filing_date": c.filing_date, "accession": c.accession, "cik": c.cik,
                         "is_predecessor_cik": c.is_predecessor_cik, "bytes": size,
                         "annual_meeting_detected": is_annual, "download_note": note})
            print(f"[{co.ticker}] {y}: {c.filing_date} {size/1e6:.1f} MB {note}")
    df = pd.DataFrame(rows)
    if "missing_reason" not in df:
        df["missing_reason"] = pd.NA
    df.to_csv(interim_dir("part2") / "proxy_manifest.csv", index=False)
    print(f"coverage {(df.status == 'ok').mean():.1%} of {len(df)} company-years")


if __name__ == "__main__":
    main()
