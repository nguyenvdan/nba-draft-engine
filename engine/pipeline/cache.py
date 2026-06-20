"""Throttled, on-disk cache for every network fetch.

Design goals:
  * Each URL / API call is fetched at most once, then served from disk forever
    (re-runs are free and deterministic).
  * Polite rate limiting (~18 requests/min) with exponential backoff on 429/5xx.
  * 404s are remembered (``.404`` marker) so slug-probing the CBB site does not
    re-hit known-missing pages every run.
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "raw_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class FetchError(Exception):
    """Retryable transport error (429 / 5xx / timeout)."""


class NotFound(Exception):
    """Hard 404 — the resource does not exist (cached as a miss)."""


class RateLimiter:
    """Spaces live requests at least ``min_interval`` seconds apart."""

    def __init__(self, min_interval: float = 3.2):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        delta = time.monotonic() - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta + random.uniform(0.0, 0.4))
        self._last = time.monotonic()


limiter = RateLimiter()


def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return CACHE_DIR / safe


@retry(
    retry=retry_if_exception_type(FetchError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _http_get(url: str) -> str:
    limiter.wait()
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if resp.status_code == 404:
        raise NotFound(url)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise FetchError(f"HTTP {resp.status_code} for {url}")
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code} for {url}")
    resp.encoding = "utf-8"  # SR/BBRef serve UTF-8; avoid latin-1 mojibake on accents
    return resp.text


def get_html(url: str, cache_key: str, force: bool = False) -> str:
    """Return page HTML, fetching + caching on first call.

    Raises NotFound (and remembers it) for 404s.
    """
    path = _cache_path(cache_key)
    miss = _cache_path(cache_key + ".404")
    if not force:
        if path.exists():
            return path.read_text(encoding="utf-8")
        if miss.exists():
            raise NotFound(url)
    try:
        text = _http_get(url)
    except NotFound:
        miss.write_text("404", encoding="utf-8")
        raise
    path.write_text(text, encoding="utf-8")
    return text


def get_json(cache_key: str, producer, force: bool = False):
    """Return cached JSON, calling ``producer()`` (a no-arg callable) on a miss.

    ``producer`` must return a JSON-serialisable object with no NaN (use the raw
    nba_api ``get_dict()`` response, whose missing values are ``None``).
    """
    path = _cache_path(cache_key)
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    obj = producer()
    path.write_text(json.dumps(obj), encoding="utf-8")
    return obj


def fetch_text_and_url(url: str):
    """GET following redirects; return (text, final_url) or (None, None).

    Used for the Sports-Reference search endpoint, which 302-redirects a unique
    query straight to the player page (resolves nickname/legal-name mismatches).
    Not cached by slug — searches are rare (only on slug-probe misses).
    """
    limiter.wait()
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30,
                         allow_redirects=True)
    except requests.RequestException:
        return None, None
    if r.status_code != 200:
        return None, None
    r.encoding = "utf-8"
    return r.text, r.url
