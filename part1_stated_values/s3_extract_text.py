"""Part 1, step 3 - Extract visible body text, stripping navigation, footer and boilerplate.

Input : data/interim/part1/snapshot_manifest.csv + data/raw/wayback/**.html
Output: data/interim/part1/texts.csv  (ticker, year, text, extraction_method, n_words, quality_flag)

Extraction cascade (first method yielding >= 40 words wins; the method is recorded per row):
  1. trafilatura (if installed) - a main-content extractor benchmarked as among the most accurate
     open-source boilerplate removers; run in precision mode.
  2. DOM heuristics (always available, BeautifulSoup):
       - drop <script>, <style>, <nav>, <header>, <footer>, <aside>, <form>, <noscript>, <svg>,
         <iframe>, <button>, cookie banners, Wayback toolbar remnants (#wm-ipp*);
       - drop any element whose id/class/role/aria-label looks like navigation, menus, breadcrumbs,
         footers, cookie/consent, social-share, search, modal or skip-links;
       - if a <main>, [role=main] or <article> region exists and holds >= 50 words, keep only it;
       - line-level filter removes residual boilerplate lines (copyright, "all rights reserved",
         "skip to content", "follow us", "privacy policy", ...) and exact duplicate lines.
     Short lines are deliberately KEPT - on values pages one-word headings ("Integrity",
     "Respect") are often the values themselves.
  3. Embedded JSON (for JavaScript-rendered sites, e.g. Next.js __NEXT_DATA__): when the visible
     DOM is nearly empty, harvest human-language strings (>= 8 words, no markup) from JSON blobs.

Quality flags: ok | thin (<40 words) | js_shell (thin and script-heavy - archive captured an
empty client-side app) | not_english | error_page (text opens like an error message) | empty.
Cookie/consent banners and language-switch notices are always removed, whatever their length.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from bs4 import BeautifulSoup

from authenticity.config import interim_dir
from authenticity.textutils import normalize, words

try:
    import trafilatura  # optional, recommended (needs lxml_html_clean with lxml >= 5.2)
except Exception as _e:  # noqa: BLE001 - any import problem -> fall back to DOM heuristics
    print(f"NOTE: trafilatura unavailable ({type(_e).__name__}: {_e}); using DOM heuristics only")
    trafilatura = None

import warnings

from bs4 import XMLParsedAsHTMLWarning

# A few archived captures are XML/XHTML; parsing them as HTML is fine for text extraction.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

DROP_TAGS = ["script", "style", "noscript", "svg", "iframe", "nav", "header", "footer", "aside",
             "form", "button", "select", "input", "template", "picture", "video", "audio"]
BOILER_ATTR = re.compile(
    r"(^|[\s_-])(nav|navbar|menu|megamenu|breadcrumb|footer|header|masthead|cookie|consent|gdpr|"
    r"onetrust|social|share|sharing|search|modal|popup|skip|subscribe|newsletter|banner-cookie|"
    r"site-?map|utility|toolbar|wm-ipp|related|sidebar)([\s_-]|$)", re.I)
BOILER_LINE = re.compile(
    r"(©|\(c\)\s*\d{4}|copyright|all rights reserved|skip to (main )?content|follow us|privacy "
    r"(policy|statement|notice)|terms (of use|and conditions)|cookie|sign in|log ?in|subscribe|"
    r"site ?map|back to top|share (this|on)|javascript (is )?(disabled|required)|enable javascript|"
    r"your browser|accessibility statement|do not sell my)", re.I)
# Lines that are never part of a values statement, whatever their length: cookie/consent
# banners (SLB 2016-18 archived only its EU cookie notice) and language-switch notices
# (wellsfargo.com served "Navegó a una página que no está disponible en español").
ALWAYS_DROP_LINE = re.compile(
    r"\bcookies?\b|consent to (the )?use|no est[aá] disponible en espa[nñ]ol|^p[aá]gina principal$|"
    r"navegó a una página", re.I)
# Text openings that mark an error page rather than content (checked on the first 300 chars).
ERROR_TEXT = re.compile(
    r"something (has )?gone wrong|something went wrong|page (was )?not found|we('re| are) sorry|"
    r"oops|an error (has )?occurred|page (is )?(no longer|not) available|cannot be found|"
    r"page you (requested|are looking for)|p[aá]gina no (encontrada|disponible)", re.I)


def is_error_text(text: str) -> bool:
    return bool(ERROR_TEXT.search((text or "")[:300]))


STOP_EN = {"the", "and", "of", "to", "in", "we", "our", "is", "for", "with", "that", "are",
           "you", "your", "a", "an", "on", "at", "by", "from", "about", "more", "learn", "us"}
# Frequent function words of the other languages big US firms publish in (Spanish, French,
# German, Portuguese, Italian). Words that are also English ("a", "on", "in") are excluded.
STOP_FOREIGN = {"el", "la", "los", "las", "del", "que", "por", "para", "con", "una", "nuestro",
                "nuestra", "nuestros", "le", "les", "des", "et", "est", "pour", "avec", "une",
                "nous", "notre", "der", "die", "das", "und", "ist", "mit", "wir", "unser", "nicht",
                "da", "dos", "das", "uma", "nosso", "nossa", "il", "della", "che", "per", "sono"}
MIN_WORDS = 40


def _attr_text(el) -> str:
    if not getattr(el, "attrs", None):
        return ""
    vals = []
    for a in ("id", "class", "role", "aria-label", "data-component"):
        v = el.attrs.get(a)
        if isinstance(v, list):
            v = " ".join(v)
        if v:
            vals.append(str(v))
    return " ".join(vals)


def clean_lines(text: str) -> str:
    seen, out = set(), []
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        if ALWAYS_DROP_LINE.search(line):
            continue
        if BOILER_LINE.search(line) and len(line.split()) < 25:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return normalize("\n".join(out))


def extract_dom(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(DROP_TAGS):
        t.decompose()
    root_el = soup.body or soup
    total = max(1, len(root_el.get_text(" ").split()))
    for el in list(soup.find_all(True)):
        if getattr(el, "decomposed", False):  # removed together with an ancestor
            continue
        try:
            if el.name in ("html", "body", "main", "article") or not BOILER_ATTR.search(_attr_text(el)):
                continue
            # Safety valve: page-wide wrappers often carry state classes such as
            # "has-sidebar" or "menu-open". Never delete an element that holds the main heading
            # or a large share of the page's text - that is content, not boilerplate.
            if el.find(["main", "article", "h1"]) is not None:
                continue
            if len(el.get_text(" ").split()) > 0.4 * total:
                continue
            el.decompose()
        except Exception:  # element already removed together with an ancestor
            continue
    region = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    if region is not None and len(region.get_text(" ").split()) >= 50:
        root = region
    else:
        root = soup.body or soup
    return clean_lines(root.get_text("\n"))


def extract_embedded_json(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    blobs = [s.string for s in soup.find_all("script")
             if s.string and (s.get("type") == "application/json" or s.get("id") == "__NEXT_DATA__"
                              or s.string.strip().startswith("{"))]
    strings: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o.split()) >= 8 and "<" not in o and "{" not in o \
                and not o.startswith("http"):
            strings.append(o)

    for b in blobs:
        try:
            walk(json.loads(b))
        except (json.JSONDecodeError, TypeError):
            continue
    return clean_lines("\n".join(dict.fromkeys(strings)))


def extract(html: str) -> tuple[str, str]:
    if trafilatura is not None:
        t = trafilatura.extract(html, favor_precision=True, include_comments=False,
                                include_tables=False, deduplicate=False) or ""
        # deduplicate=False: trafilatura's de-duplication keeps a cache ACROSS documents, so a
        # page identical to last year's could lose its text depending on processing order.
        # Each snapshot must be extracted independently of every other snapshot.
        t = clean_lines(t)
        if len(words(t)) >= MIN_WORDS:
            return t, "trafilatura"
    t = extract_dom(html)
    if len(words(t)) >= MIN_WORDS:
        return t, "dom_heuristic"
    j = extract_embedded_json(html)
    if len(words(j)) > len(words(t)):
        return j, "embedded_json"
    return t, "dom_heuristic"


def quality(text: str, html: str) -> str:
    w = words(text)
    if not w:
        return "empty"
    if is_error_text(text):
        return "error_page"
    if len(w) < MIN_WORDS:
        n_scripts = html.lower().count("<script")
        return "js_shell" if n_scripts >= 10 else "thin"
    # Language check. A share-of-English-stop-words threshold misfires on navigation-style
    # hub pages ("Investor relations", "Learn more" ...), so compare against other languages
    # instead, and treat text that is mostly non-Latin script as non-English.
    n_en = sum(x in STOP_EN for x in w)
    n_foreign = sum(x in STOP_FOREIGN for x in w)
    letters = [c for c in text if c.isalpha()]
    non_latin = sum(not c.isascii() for c in letters) / max(1, len(letters))
    if non_latin > 0.3 or (n_foreign >= 5 and n_foreign > n_en):
        return "not_english"
    return "ok"


def main():
    man = pd.read_csv(interim_dir("part1") / "snapshot_manifest.csv")
    rows = []
    for _, m in man[man.status == "ok"].iterrows():
        html = Path(m.html_path).read_bytes().decode("utf-8", errors="replace")
        text, method = extract(html)
        rows.append(dict(ticker=m.ticker, year=int(m.year), text=text, extraction_method=method,
                         n_words=len(words(text)), quality_flag=quality(text, html)))
    df = pd.DataFrame(rows)
    out = interim_dir("part1") / "texts.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out}: {len(df)} texts; quality:\n{df.quality_flag.value_counts().to_string()}")
    print(f"methods:\n{df.extraction_method.value_counts().to_string()}")
    bad = df[df.quality_flag.isin(["empty", "js_shell"])]
    if len(bad):
        print("firm-years with no usable text (open the saved HTML to check):")
        print(bad.groupby("ticker").year.apply(lambda y: ",".join(map(str, y))).to_string())


if __name__ == "__main__":
    main()
