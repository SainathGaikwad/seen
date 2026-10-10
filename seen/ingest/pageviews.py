"""Wikimedia Pageviews REST API client (per article, per language edition, daily)."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
from datetime import date
from pathlib import Path

import requests

from ..config import user_agent

log = logging.getLogger(__name__)
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{edition}.wikipedia/all-access/user/{article}/daily/{start}/{end}"


def fetch_daily(edition: str, title: str, start: date, end: date, cache_dir: Path, pause: float = 0.2) -> dict[str, int] | None:
    """Returns {YYYY-MM-DD: views} ({} when the API has no rows), or None if the request failed after retries.
    Successful results are cached per (edition, title, range); failures are not, so a re-run only refetches what failed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    # short, ASCII-only cache key: long percent-encoded titles exceed Windows path limits
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]
    cf = cache_dir / f"pv_{edition}_{digest}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    if cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))
    article = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = BASE.format(edition=edition, article=article, start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}")
    out = None
    for attempt in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": user_agent(), "Accept": "application/json"}, timeout=60)
        except requests.RequestException as exc:
            log.warning("pageviews attempt %s failed %s/%s: %s", attempt + 1, edition, title, str(exc)[:120])
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 404:  # article exists in Wikidata but has no pageview rows (new or renamed)
            out = {}
            break
        if r.status_code == 429 or r.status_code >= 500:  # throttled: wait 5, 10, 20 s
            time.sleep(5 * (2 ** attempt))
            continue
        if r.status_code != 200:
            log.warning("pageviews HTTP %s for %s/%s", r.status_code, edition, title)
            return None
        try:
            out = {item["timestamp"][:8]: int(item["views"]) for item in r.json().get("items", [])}
            out = {f"{k[:4]}-{k[4:6]}-{k[6:8]}": v for k, v in out.items()}
        except (ValueError, KeyError):
            return None
        break
    if out is None:  # failed after retries: not cached, so the next run refetches it
        log.warning("pageviews gave up on %s/%s", edition, title)
        return None
    cf.write_text(json.dumps(out), encoding="utf-8")
    time.sleep(pause)
    return out


def fetch_baseline_and_window(edition: str, title: str, b_start: date, b_end: date, w_start: date, w_end: date,
                              cache_dir: Path, pause: float = 0.2) -> tuple[dict | None, dict | None]:
    """Returns (baseline series, window series) with ONE API request covering both ranges.
    If both ranges are already cached from an earlier run, no request is made."""
    def _cached(start: date, end: date):
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]
        cf = cache_dir / f"pv_{edition}_{digest}_{start:%Y%m%d}_{end:%Y%m%d}.json"
        return json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else None
    b, w = _cached(b_start, b_end), _cached(w_start, w_end)
    if b is not None and w is not None:
        return b, w
    full = fetch_daily(edition, title, b_start, w_end, cache_dir, pause=pause)
    if full is None:
        return None, None
    b = {d: v for d, v in full.items() if b_start.isoformat() <= d <= b_end.isoformat()}
    w = {d: v for d, v in full.items() if w_start.isoformat() <= d <= w_end.isoformat()}
    return b, w
