"""Polite, cached HTTP client shared by the Wayback (Part 1) and EDGAR (Part 2) scrapers.

Design choices
--------------
* Per-host rate limiting. The Wayback Machine throttles aggressive clients (HTTP 429 and
  temporary IP blocks); SEC EDGAR's fair-access policy caps clients at 10 requests/second and
  requires a descriptive User-Agent with contact e-mail.
* Exponential back-off with jitter on 429 / 5xx / connection errors.
* Disk cache keyed by URL so the whole pipeline is re-runnable and resumable without
  re-hitting the archives. Delete data/interim/http_cache to force fresh downloads.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import interim_dir

DEFAULT_UA = os.environ.get(
    "SEC_USER_AGENT",  # EDGAR rejects anonymous clients; set "Name email@domain" in .env
    "AuthenticityResearch/1.0 (academic research; contact: set SEC_USER_AGENT)",
)

# Minimum seconds between requests to the same host.
HOST_MIN_INTERVAL = {
    "web.archive.org": 1.5,
    "data.sec.gov": 0.15,
    "www.sec.gov": 0.15,
}


@dataclass
class FetchResult:
    url: str            # URL requested
    final_url: str      # URL after redirects
    status: int         # final HTTP status (0 = network failure)
    content: bytes
    headers: dict
    history: list       # list of (status, url) for each redirect hop
    from_cache: bool = False

    @property
    def text(self) -> str:
        enc = "utf-8"
        ctype = self.headers.get("Content-Type", "") or self.headers.get("content-type", "")
        if "charset=" in ctype:
            enc = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        return self.content.decode(enc, errors="replace")


class PoliteSession:
    def __init__(self, cache_name: str = "http_cache", user_agent: str = DEFAULT_UA,
                 max_retries: int = 6, timeout: int = 60):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.max_retries = max_retries
        self.timeout = timeout
        self.cache_dir = interim_dir(cache_name)
        self._last_hit: dict[str, float] = {}

    # ---------------------------------------------------------------- cache helpers
    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        h = hashlib.sha1(url.encode()).hexdigest()
        sub = self.cache_dir / h[:2]
        sub.mkdir(exist_ok=True)
        return sub / f"{h}.bin", sub / f"{h}.json"

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        gap = HOST_MIN_INTERVAL.get(host, 0.5)
        wait = self._last_hit.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    # ---------------------------------------------------------------- public API
    def get(self, url: str, use_cache: bool = True, allow_redirects: bool = True,
            cache_statuses: tuple = (200, 404)) -> FetchResult:
        body_p, meta_p = self._cache_paths(url)
        if use_cache and body_p.exists() and meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            return FetchResult(url, meta["final_url"], meta["status"], body_p.read_bytes(),
                               meta["headers"], meta["history"], from_cache=True)

        last_exc = None
        for attempt in range(self.max_retries):
            self._throttle(url)
            try:
                r = self.s.get(url, timeout=self.timeout, allow_redirects=allow_redirects)
            except requests.RequestException as e:  # DNS, reset, timeout ...
                last_exc = e
                self._backoff(attempt)
                continue
            if r.status_code in (429, 500, 502, 503, 504, 520, 522, 524):
                # Honour Retry-After when the server sends one.
                ra = r.headers.get("Retry-After")
                self._backoff(attempt, float(ra) if ra and ra.isdigit() else None)
                continue
            res = FetchResult(url, r.url, r.status_code, r.content, dict(r.headers),
                              [(h.status_code, h.url) for h in r.history])
            if r.status_code in cache_statuses:
                body_p.write_bytes(r.content)
                meta_p.write_text(json.dumps({"final_url": r.url, "status": r.status_code,
                                              "headers": dict(r.headers),
                                              "history": res.history}), encoding="utf-8")
            return res
        return FetchResult(url, url, 0, b"", {}, [], from_cache=False) if last_exc else \
            FetchResult(url, url, 429, b"", {}, [])

    def get_json(self, url: str, **kw):
        r = self.get(url, **kw)
        if r.status != 200 or not r.content.strip():
            return None
        try:
            return json.loads(r.content)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _backoff(attempt: int, retry_after: float | None = None) -> None:
        delay = retry_after if retry_after else min(120, (2 ** attempt) * 2) + random.random()
        if delay >= 8:  # let the user see that a long pause is deliberate, not a hang
            print(f"   (server busy or slow - waiting {delay:.0f}s before retry {attempt + 2})", flush=True)
        time.sleep(delay)
