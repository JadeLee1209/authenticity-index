"""Wayback Machine CDX API helpers (Part 1).

CDX API reference: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
Playback of the *original* archived bytes (no Wayback toolbar / URL rewriting) uses the
`id_` modifier:  https://web.archive.org/web/<timestamp>id_/<original-url>
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlencode, urlparse

from .http import PoliteSession

CDX = "https://web.archive.org/cdx/search/cdx"


class CDXUnavailable(RuntimeError):
    """The CDX server could not be reached or refused the request (not the same as 0 captures)."""

WB_URL_RE = re.compile(r"web\.archive\.org/web/(\d{14})[a-z_]*/(.+)$")
CDX_FIELDS = ["timestamp", "original", "statuscode", "mimetype", "digest", "length"]

# Path segments that are only a locale (e.g. /en-us/, /us/en/) - used to detect "homepage" redirects
LOCALE_SEG = re.compile(r"^([a-z]{2}([-_][a-z]{2})?|global|home|index(\.html?)?)$", re.I)


def cdx_query(sess: PoliteSession, url: str, *, match_type: str | None = None,
              from_year: int = 2016, to_year: int = 2024, collapse: str | None = "timestamp:8",
              filters: list[str] | None = None, limit: int | None = None,
              fields: list[str] = CDX_FIELDS) -> list[dict]:
    """Return CDX rows as dicts. collapse='timestamp:8' keeps at most one capture per day,
    which bounds the listing size for heavily crawled pages without losing year coverage."""
    params = [("url", url), ("output", "json"), ("from", str(from_year)), ("to", str(to_year)),
              ("fl", ",".join(fields))]
    if match_type:
        params.append(("matchType", match_type))
    if collapse:
        params.append(("collapse", collapse))
    for f in filters or []:
        params.append(("filter", f))
    if limit:
        params.append(("limit", str(limit)))
    r = sess.get(f"{CDX}?{urlencode(params)}")
    if r.status != 200:
        # Throttled / blocked / network error. Raise instead of returning [] so callers never
        # mistake an outage for "this page was never archived" (and never cache that).
        raise CDXUnavailable(f"CDX HTTP {r.status} for {url}")
    try:
        data = json.loads(r.content) if r.content.strip() else []
    except json.JSONDecodeError as e:
        raise CDXUnavailable(f"CDX returned non-JSON for {url}") from e
    if len(data) < 2:
        return []
    header = data[0]
    return [dict(zip(header, row)) for row in data[1:]]


def ts_to_dt(ts: str) -> datetime:
    return datetime.strptime(ts[:14].ljust(14, "0"), "%Y%m%d%H%M%S")


def playback_url(ts: str, original: str) -> str:
    return f"https://web.archive.org/web/{ts}id_/{original}"


def parse_wayback_url(url: str) -> tuple[str | None, str]:
    """('20190703120000', 'https://example.com/about') from a Wayback playback URL."""
    m = WB_URL_RE.search(url)
    if not m:
        return None, url
    orig = m.group(2)
    if not orig.startswith("http"):
        orig = "http://" + orig
    return m.group(1), orig


def host_of(url: str) -> str:
    u = url if "://" in url else "http://" + url
    h = urlparse(u).netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def host_allowed(url: str, domains: list[str]) -> bool:
    """True if url's host is one of the company's domains or any subdomain of them."""
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in (x.lower() for x in domains))


def is_homepage(url: str) -> bool:
    """A redirect that lands on '/' or a bare locale root ('/en-us/') means the page was retired
    and the server bounced visitors home - that is NOT the About page and is rejected."""
    u = url if "://" in url else "http://" + url
    segs = [s for s in urlparse(u).path.split("/") if s]
    return all(LOCALE_SEG.match(s) for s in segs)


# Language codes of non-English site versions big US firms publish (/es/, /fr-fr/, /zh-cn/ ...).
NON_EN_LANGS = {"es", "fr", "de", "ja", "zh", "pt", "it", "ko", "nl", "ru", "ar", "sv", "pl", "tr",
                "he", "id", "th", "vi", "cs", "da", "fi", "no", "nb", "hu", "el", "ro", "uk", "ms"}


def foreign_locale(url: str) -> str | None:
    """Return the non-English locale segment of a URL path (e.g. 'es' in /es/about/), else None."""
    u = url if "://" in url else "http://" + url
    for seg in urlparse(u).path.lower().split("/"):
        lang = re.split(r"[-_]", seg)[0] if re.fullmatch(r"[a-z]{2}([-_][a-z]{2})?", seg) else None
        if lang in NON_EN_LANGS:
            return seg
    return None


SOFT_404 = re.compile(r"page (was )?not found|404|page (you|you're|you are) (requested|looking for)|"
                      r"no longer (available|exists)|(cannot|can't|could not) be found|"
                      r"page (does not|doesn't) exist|página no encontrada", re.I)


def soft_404(html: bytes) -> bool:
    """True if a 200 response is really an error page. Only the <title> and first <h1> are
    checked, so a values page that merely mentions '404' in its body is not rejected."""
    head = html[:200_000].decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", head, re.I | re.S)
    probe = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)) for m in (title, h1) if m)
    return bool(SOFT_404.search(probe))
