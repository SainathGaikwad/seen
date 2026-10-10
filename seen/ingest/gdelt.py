"""GDELT DOC 2.0 API: count news articles naming an athlete in a date range (optional signal)."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date
from pathlib import Path

import requests

from ..config import user_agent

log = logging.getLogger(__name__)
API = "https://api.gdeltproject.org/api/v2/doc/doc"


def article_count(name: str, start: date, end: date, cache_dir: Path, pause: float = 5.0) -> dict:
    """Returns {"count": n, "languages": {...}, "countries": {...}} using artlist (max 250 records).
    Counts above 250 are reported as 250 (censored). Query adds "cricket" to reduce name collisions."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"gd_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:16]}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    if cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))
    params = {
        "query": f'"{name}" cricket', "mode": "artlist", "maxrecords": 250, "format": "json",
        "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959",
    }
    data = None
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, headers={"User-Agent": user_agent()}, timeout=60)
            if r.status_code == 429:  # GDELT rate limit: back off and retry
                time.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json() if r.text.strip() else {}
            break
        except (requests.RequestException, ValueError) as exc:
            log.warning("gdelt failed for %s: %s", name, exc)
            return {"count": None, "languages": {}, "countries": {}, "error": str(exc)[:200]}
    if data is None:
        log.warning("gdelt rate-limited for %s; skipped (not cached)", name)
        return {"count": None, "languages": {}, "countries": {}, "error": "429 rate limited"}
    arts = data.get("articles", []) or []
    langs, countries = {}, {}
    for a in arts:
        langs[a.get("language", "?")] = langs.get(a.get("language", "?"), 0) + 1
        countries[a.get("sourcecountry", "?")] = countries.get(a.get("sourcecountry", "?"), 0) + 1
    out = {"count": len(arts), "censored": len(arts) >= 250, "languages": langs, "countries": countries}
    cf.write_text(json.dumps(out), encoding="utf-8")
    time.sleep(pause)
    return out
