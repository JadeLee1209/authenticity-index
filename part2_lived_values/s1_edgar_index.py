"""Part 2, step 1 - Index every DEF 14A (definitive proxy statement) filed 2016-2024.

Why proxy statements (DEF 14A)?  See README "Document choice". In short:
  * Coverage: every US-listed firm must file one each year -> near-complete 50 x 9 panel from a
    single authoritative source (SEC EDGAR), unlike voluntary ESG/DEI reports that start late,
    change format, and are self-curated marketing documents.
  * Behaviour, not just talk: proxies disclose what executives are actually PAID for (incentive
    metrics and weights in the CD&A) and how the board allocates OVERSIGHT - revealed priorities.
  * Comparability: legally mandated structure and liability (Rule 14a-9) make cross-firm,
    cross-year comparison more defensible.

Input : config/companies.csv
Output: data/interim/part2/proxy_index.csv  all DEF 14A / DEFC14A filings whose proxy year (see
        proxy_year()) is 2016-2024, per company

Source: SEC EDGAR submissions API (data.sec.gov). Requires SEC_USER_AGENT="Name email" (SEC policy).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import YEARS, interim_dir, load_companies
from authenticity.http import PoliteSession

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
# DEF 14A = definitive proxy; DEFC14A = definitive proxy in a contested election (e.g. a proxy
# fight - the company still files its annual-meeting proxy under this form). Excludes DEFA14A
# (additional materials) and DEFM14A (merger proxies).
FORMS = {"DEF 14A", "DEFC14A"}


def proxy_year(filing_date: str) -> int:
    """Year of the annual meeting a proxy serves. Firms with fiscal years ending in autumn file in
    Nov/Dec for a meeting early the next year (e.g. Apple filed 27 Dec 2017 for its Feb 2018
    meeting). Assigning by calendar filing year would give such firms two proxies in one year and
    none in the next, so Nov/Dec filings are attributed to the following year."""
    y, m = int(filing_date[:4]), int(filing_date[5:7])
    return y + 1 if m >= 11 else y


def cik_map(sess) -> dict[str, int]:
    data = sess.get_json(TICKERS_URL) or {}
    return {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}


def filings_for(sess, cik: int) -> list[dict]:
    """All filings for a CIK: the 'recent' block plus older paginated files."""
    root = sess.get_json(SUBMISSIONS.format(name=f"CIK{cik:010d}.json"))
    if not root:
        return []
    blocks = [root["filings"]["recent"]]
    for f in root["filings"].get("files", []):
        extra = sess.get_json(SUBMISSIONS.format(name=f["name"]))
        if extra:
            blocks.append(extra)
    out = []
    for b in blocks:
        n = len(b.get("form", []))
        for i in range(n):
            out.append({k: b[k][i] for k in ("form", "filingDate", "accessionNumber",
                                             "primaryDocument", "reportDate") if k in b})
    return out


def main():
    sess = PoliteSession()
    ciks = cik_map(sess)
    rows = []
    for _, co in load_companies().iterrows():
        main_cik = ciks.get(co.sec_ticker.upper())
        all_ciks = ([main_cik] if main_cik else []) + [int(c) for c in co.predecessor_ciks]
        if not all_ciks:
            print(f"[{co.ticker}] CIK not found - add it to predecessor_ciks in companies.csv")
            continue
        for cik in all_ciks:
            for f in filings_for(sess, cik):
                if f["form"] not in FORMS:
                    continue
                y = proxy_year(f["filingDate"])
                if y not in YEARS:
                    continue
                acc = f["accessionNumber"].replace("-", "")
                rows.append(dict(
                    ticker=co.ticker, cik=cik, is_predecessor_cik=cik != main_cik, form=f["form"],
                    filing_date=f["filingDate"], filing_year=y, accession=f["accessionNumber"],
                    primary_doc=f["primaryDocument"],
                    url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{f['primaryDocument']}",
                    index_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"))
        n = sum(r["ticker"] == co.ticker for r in rows)
        print(f"[{co.ticker}] CIK {all_ciks}: {n} DEF 14A filings 2016-2024")
    df = pd.DataFrame(rows).sort_values(["ticker", "filing_date"])
    out = interim_dir("part2") / "proxy_index.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} filings)")


if __name__ == "__main__":
    main()
