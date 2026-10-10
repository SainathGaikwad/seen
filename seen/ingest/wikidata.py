"""Map ESPNcricinfo IDs (Cricsheet register) to Wikipedia article titles via Wikidata P2697."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

from ..config import user_agent

log = logging.getLogger(__name__)
SPARQL = "https://query.wikidata.org/sparql"


def build_query(cricinfo_ids: list[str], editions: list[str]) -> str:
    values = " ".join(f'"{i}"' for i in cricinfo_ids)
    optional = "\n".join(
        f'OPTIONAL {{ ?art_{e} schema:about ?item ; schema:isPartOf <https://{e}.wikipedia.org/> ; schema:name ?title_{e} . }}'
        for e in editions
    )
    selects = " ".join(f"?title_{e}" for e in editions)
    return f"""
SELECT ?cricinfo ?item ?itemLabel {selects} WHERE {{
  VALUES ?cricinfo {{ {values} }}
  ?item wdt:P2697 ?cricinfo .
  {optional}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}"""


def map_players(cricinfo_ids: list[str], editions: list[str], cache_dir: Path, batch: int = 40, pause: float = 1.0) -> dict:
    """Returns {cricinfo_id: {"qid":..., "label":..., "titles": {edition: title}}}. Cached per ID."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "wikidata_map.json"
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            log.warning("ignoring unreadable cache %s", cache_file)
            cache = {}
    todo = [i for i in cricinfo_ids if i and i not in cache]
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        q = build_query(chunk, editions)
        try:
            r = requests.get(SPARQL, params={"query": q, "format": "json"},
                             headers={"User-Agent": user_agent(), "Accept": "application/sparql-results+json"}, timeout=90)
            r.raise_for_status()
        except requests.RequestException as exc:
            log.warning("wikidata batch failed (not cached, will retry next run): %s", exc)
            time.sleep(pause)
            continue
        found = {}
        for row in r.json()["results"]["bindings"]:
            cid = row["cricinfo"]["value"]
            label = row.get("itemLabel", {}).get("value")
            if label and re.fullmatch(r"Q\d+", label):  # Wikidata returns the bare QID when no English label exists
                label = None
            entry = found.setdefault(cid, {"qid": row["item"]["value"].rsplit("/", 1)[-1], "label": label, "titles": {}})
            for e in editions:
                key = f"title_{e}"
                if key in row:
                    entry["titles"][e] = row[key]["value"]
        for i in chunk:
            cache[i] = found.get(i, {"qid": None, "label": None, "titles": {}})
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(pause)
    return {i: cache.get(i, {"qid": None, "label": None, "titles": {}}) for i in cricinfo_ids}
