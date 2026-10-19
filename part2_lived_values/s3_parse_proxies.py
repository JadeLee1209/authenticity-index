"""Part 2, step 3 - Convert proxy HTML to clean paragraphs and locate the CD&A section.

Input : data/interim/part2/proxy_manifest.csv + data/raw/edgar/**.htm
Output: data/interim/part2/parsed/<TICKER>_<YEAR>.json   {paragraphs:[...], kinds:[...], cda:[i,j]}
        data/interim/part2/docs.csv                       per-document parse statistics

Parsing choices
  * EDGAR HTML is typeset for print: text is split across <div>/<font> runs, tables hold both
    layout and data, and every page repeats a running header/footer. We therefore
      - render table rows as "cell | cell | cell" lines (kept: incentive-metric weights live in tables),
      - re-assemble prose paragraphs from consecutive lines until sentence-final punctuation,
      - drop lines that repeat >= 4 times in the document (running headers/footers, page numbers).
  * Each paragraph is tagged prose / table / heading so prose-only measures (tone, hedging)
    are not polluted by tables of numbers.
  * CD&A: see find_cda() - the "Compensation Discussion and Analysis" mention that starts the
    LONGEST span up to the next "Summary Compensation Table" heading (the table of contents and
    cross-references give short spans).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # some EDGAR files are XHTML

from authenticity.config import interim_dir
from authenticity.textutils import normalize

CDA_RE = re.compile(r"^\s*(compensation\s+discussion\s*(and|&)\s*analysis|cd&a)\b", re.I)
SCT_RE = re.compile(r"^\s*(\d{4}\s+)?summary\s+compensation\s+table", re.I)
PAGE_NO = re.compile(r"^\s*(page\s*)?[ivxlc\d]{1,4}\s*$", re.I)
BLOCK_TAGS = ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "center"]


def html_to_lines(html: str) -> list[tuple[str, str]]:
    """Return (kind, text) lines; kind in {'table','text'}."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "head"]):
        t.decompose()
    # Replace each table row by a single line "a | b | c" (empty cells dropped).
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ").split()) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c and c not in ("$", "%", ")")]
        tr.replace_with(soup.new_string("\n␞TABLE " + " | ".join(cells) + "\n" if cells else "\n"))
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_after("\n")
    lines = []
    for raw in soup.get_text().split("\n"):
        line = normalize(raw.replace("\xa0", " "))
        if not line:
            continue
        if line.startswith("␞TABLE "):
            lines.append(("table", line[7:]))
        else:
            lines.append(("text", line))
    return lines


PARSER_VERSION = 2  # bump when parsing changes; cached parses with another version are redone


def needs_layout_repair(paras: list[str], kinds: list[str]) -> bool:
    """Two broken layouts seen in EDGAR proxies:
      * the whole document is typeset inside layout tables (IBM 2019, MPC 2022-24): almost no
        prose, so prose-only measures and LLM passage sampling see nothing;
      * line breaks are lost, so 'paragraphs' are whole pages (GOOGL 2020): passages are too long
        to sample (> 350 words) and CD&A boundaries are coarse.
    Only such documents are repaired, so parses (and LLM caches) of normal documents are unchanged."""
    n = sum(len(p.split()) for p in paras) or 1
    prose = [len(p.split()) for p, k in zip(paras, kinds) if k == "prose"]
    return sum(prose) / n < 0.15 or (bool(prose) and sum(prose) / len(prose) > 150)


def repair_lines(lines: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Layout-table rows whose text is essentially one long cell become ordinary text lines."""
    out = []
    for kind, t in lines:
        if kind == "table":
            cells = t.split(" | ")
            longest = max(cells, key=lambda c: len(c.split()))
            if len(longest.split()) >= 20 and len(longest.split()) >= 0.8 * len(t.split()):
                out.append(("text", longest))
                continue
        out.append((kind, t))
    return out


SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(])")


def split_long(paras: list[str], kinds: list[str], max_words: int = 300) -> tuple[list[str], list[str]]:
    """Split over-long prose blocks into sentence-aligned chunks of <= ~max_words."""
    P, K = [], []
    for p, k in zip(paras, kinds):
        if k != "prose" or len(p.split()) <= max_words:
            P.append(p); K.append(k); continue
        buf = []
        for sent in SENT_END.split(p):
            buf.append(sent)
            if sum(len(x.split()) for x in buf) >= max_words * 0.6:
                P.append(" ".join(buf)); K.append("prose"); buf = []
        if buf:
            P.append(" ".join(buf)); K.append("prose" if len(" ".join(buf).split()) >= 25 else "heading")
    return P, K


def parse(html: str) -> tuple[list[str], list[str], bool]:
    lines = html_to_lines(html)
    paras, kinds = assemble(lines)
    if not needs_layout_repair(paras, kinds):
        return paras, kinds, False
    paras, kinds = assemble(repair_lines(lines))
    paras, kinds = split_long(paras, kinds)
    return paras, kinds, True


def assemble(lines: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    freq = Counter(t for _, t in lines if len(t) < 120)
    paras, kinds, buf = [], [], []

    def flush():
        if buf:
            p = " ".join(buf)
            paras.append(p)
            kinds.append("prose" if len(p.split()) >= 25 else "heading")
            buf.clear()

    for kind, t in lines:
        if PAGE_NO.match(t) or (freq[t] >= 4 and len(t) < 120):
            continue  # page numbers and running headers/footers
        if kind == "table":
            flush()
            paras.append(t)
            kinds.append("table")
            continue
        short_heading = len(t.split()) <= 12 and not t.endswith((".", ",", ";", ":")) and not buf
        if short_heading:
            paras.append(t)
            kinds.append("heading")
            continue
        buf.append(t)
        if t.endswith((".", "?", "!", ":", '."', ".)")):
            flush()
    flush()
    return paras, kinds


CDA_ANY = re.compile(r"compensation\s+discussion\s*(and|&|&amp;)\s*analysis", re.I)
CDA_ABBR = re.compile(r"\bcd\s*&\s*a\b", re.I)  # fallback only: also used for cross-references
SCT_ANY = re.compile(r"summary\s+compensation\s+table", re.I)
# Committee names vary ("Compensation and Management Development Committee Report",
# "Report of the Talent and Compensation Committee", "Human Resources Committee Report" ...).
CCR_HEAD = re.compile(r"^\W*(([\w&,-]+\s+){0,6}committee\s+report|report\s+of\s+the\s+([\w&,-]+\s+){0,6}committee)\b", re.I)
CCR_TOPIC = re.compile(r"compensation|talent|human|people|leadership|personnel", re.I)
SCT_HEADER_ROW = re.compile(r"salary.*stock\s+awards|stock\s+awards.*salary", re.I)
SCT_HEADER_ROW2 = re.compile(r"all\s+other\s+compensation|non-?\s*equity\s+incentive", re.I)


def section_ends(paras: list[str], kinds: list[str]) -> list[int]:
    """Markers that follow the CD&A in the standard proxy layout (CD&A -> Compensation Committee
    Report -> Summary Compensation Table): a heading that STARTS with "Summary Compensation Table"
    or "Compensation Committee Report", or the SCT's own column-header row. Plain mentions of the
    SCT inside the CD&A ("see the Summary Compensation Table") are not ends."""
    ends = []
    for i, (p, k) in enumerate(zip(paras, kinds)):
        n = len(p.split())
        if k == "table":
            if SCT_HEADER_ROW.search(p) and SCT_HEADER_ROW2.search(p):
                ends.append(i)
        elif n <= 40 and (SCT_RE.match(p) or (n <= 15 and CCR_HEAD.match(p) and CCR_TOPIC.search(p))):
            ends.append(i)
    return ends


def find_cda(paras: list[str], kinds: list[str], pat: re.Pattern = CDA_ANY,
             strict_ends: bool = True) -> list[int] | None:
    """Locate the CD&A section.

    Start candidates: non-table paragraphs that name "Compensation Discussion and Analysis"
    within their first 8 words, or are short (<= 20 words) and name it anywhere. Headings in
    EDGAR HTML are often fused with neighbouring text, so an exact-heading match is too strict.
    End: the next short paragraph naming the Summary Compensation Table at least 20 paragraphs
    later (else +600 paragraphs). Several starts usually share one end (table of contents,
    proxy summary, the real heading); the LATEST of them is the real heading. Among the
    resulting sections the longest (> 1,000 words) is the CD&A."""
    starts = []
    for i, (p, k) in enumerate(zip(paras, kinds)):
        if k == "table":
            continue
        w = p.split()
        if pat.search(" ".join(w[:8])) or (len(w) <= 20 and pat.search(p)):
            starts.append(i)
    if strict_ends:
        ends = section_ends(paras, kinds)
    else:  # fallback: any short paragraph mentioning the SCT
        ends = [i for i, p in enumerate(paras) if len(p.split()) <= 40 and SCT_ANY.search(p)]
    by_end: dict[int, tuple[int, int]] = {}
    for s0 in starts:
        e = next((x for x in ends if x > s0 + 20), min(len(paras), s0 + 600))
        n = sum(len(paras[i].split()) for i in range(s0, e))
        if n > 1000 and (e not in by_end or s0 > by_end[e][0]):
            by_end[e] = (s0, n)
    if not by_end:
        # Fallbacks, in order: looser end markers; then the "CD&A" abbreviation as a title.
        if strict_ends:
            return find_cda(paras, kinds, pat, strict_ends=False)
        return find_cda(paras, kinds, CDA_ABBR) if pat is CDA_ANY else None
    e, (s0, _) = max(by_end.items(), key=lambda kv: kv[1][1])
    return [s0, e]


def main():
    man = pd.read_csv(interim_dir("part2") / "proxy_manifest.csv")
    pdir = interim_dir("part2", "parsed")
    stats = []
    for _, m in man[man.status == "ok"].iterrows():
        out = pdir / f"{m.ticker.replace('.', '_')}_{int(m.year)}.json"
        d = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        dirty = False
        if (d is None or d.get("accession") != m.accession
                or d.get("parser_version") != PARSER_VERSION):
            # (Re)parse when new, when a different filing now occupies this firm-year, or when the
            # parser changed. Normal documents come out identical, so their LLM caches stay valid.
            html = Path(m.path).read_bytes().decode("utf-8", errors="replace")
            paras, kinds, repaired = parse(html)
            d = {"ticker": m.ticker, "year": int(m.year), "accession": m.accession,
                 "parser_version": PARSER_VERSION, "layout_repaired": repaired,
                 "paragraphs": paras, "kinds": kinds}
            dirty = True
        cda = find_cda(d["paragraphs"], d["kinds"])  # cheap; always recomputed
        if "cda" not in d or d["cda"] != cda:
            d["cda"] = cda
            dirty = True
        if dirty:
            out.write_text(json.dumps(d), encoding="utf-8")
        k = Counter(d["kinds"])
        stats.append(dict(ticker=m.ticker, year=int(m.year),
                          n_words=sum(len(p.split()) for p in d["paragraphs"]),
                          n_prose_words=sum(len(p.split()) for p, kk in zip(d["paragraphs"], d["kinds"]) if kk == "prose"),
                          n_paragraphs=len(d["paragraphs"]), n_prose=k["prose"], n_table_rows=k["table"],
                          layout_repaired=d.get("layout_repaired", False),
                          cda_found=cda is not None,
                          cda_words=sum(len(p.split()) for p in d["paragraphs"][cda[0]:cda[1]]) if cda else 0))
        cw = stats[-1]["cda_words"]
        # Typical CD&As run 4k-25k words; outside 2.5k-30k the boundaries deserve a manual look.
        stats[-1]["cda_suspect"] = bool(cda) and not (2500 <= cw <= 30000)
        print(f"[{m.ticker}] {int(m.year)} paragraphs={len(d['paragraphs'])} "
              f"cda={'NO' if not cda else stats[-1]['cda_words']}"
              + (" layout_repaired" if d.get("layout_repaired") else ""))
    pd.DataFrame(stats).to_csv(interim_dir("part2") / "docs.csv", index=False)
    # Remove parses for firm-years that no longer have a proxy (later steps read every file here).
    keep = {f"{t.replace('.', '_')}_{int(y)}.json" for t, y in
            zip(man.loc[man.status == "ok", "ticker"], man.loc[man.status == "ok", "year"])}
    for f in pdir.glob("*.json"):
        if f.name not in keep:
            f.unlink()
    found = sum(s_["cda_found"] for s_ in stats)
    print(f"CD&A located in {found}/{len(stats)} proxies; "
          f"{sum(s_['cda_suspect'] for s_ in stats)} with unusual length (cda_suspect); "
          f"{sum(s_['layout_repaired'] for s_ in stats)} layout-repaired")


if __name__ == "__main__":
    main()
