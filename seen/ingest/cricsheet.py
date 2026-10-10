"""Cricsheet loader — the real data path.

Downloads the JSON zips listed in config.yaml, parses every match into the
canonical tables, and loads the people register (ESPNcricinfo IDs).

Cricsheet data is published under the ODC Attribution licence (ODC-BY 1.0);
attribute "Cricsheet (cricsheet.org)" wherever the numbers appear.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from pathlib import Path

import requests

from ..config import user_agent
from ..db import BOWLER_CREDITED_KINDS

log = logging.getLogger(__name__)


def download(url: str, dest: Path, timeout: int = 120) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("cached %s", dest.name)
        return dest
    try:
        r = requests.get(url, headers={"User-Agent": user_agent()}, timeout=timeout, stream=True)
    except requests.RequestException as exc:
        log.warning("download failed %s: %s", url, exc)
        return None
    if r.status_code != 200:
        log.warning("download failed %s: HTTP %s", url, r.status_code)
        return None
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    log.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def parse_match(data: dict, source: str, gender_filter: str | None = "female") -> dict | None:
    """Turn one Cricsheet match JSON into canonical rows. Returns None if filtered out."""
    info = data.get("info", {})
    if gender_filter and info.get("gender") != gender_filter:
        return None
    registry = info.get("registry", {}).get("people", {})
    teams = info.get("teams", [])
    if len(teams) != 2:
        return None
    event = info.get("event", {}) or {}
    outcome = info.get("outcome", {}) or {}
    result = "win" if outcome.get("winner") else outcome.get("result", "unknown")
    by = outcome.get("by", {}) or {}
    margin = None
    if "runs" in by:
        margin = f"{by['runs']} runs"
    elif "wickets" in by:
        margin = f"{by['wickets']} wickets"
    match_id = str(Path(source).stem)
    match = {
        "match_id": match_id,
        "date": info.get("dates", [None])[0],
        "competition": event.get("name") or "Bilateral",
        "season": str(info.get("season", "")),
        "stage": event.get("stage") or (f"Match {event['match_number']}" if event.get("match_number") else None),
        "match_type": info.get("match_type"),
        "gender": info.get("gender"),
        "team1": teams[0],
        "team2": teams[1],
        "venue": info.get("venue"),
        "city": info.get("city"),
        "winner": outcome.get("winner"),
        "result": result,
        "margin": margin,
        "source": f"cricsheet:{Path(source).name}",
    }
    players = {}
    appearances = []
    for team, names in (info.get("players") or {}).items():
        for name in names:
            pid = registry.get(name, name)
            players[pid] = name
            appearances.append((match_id, team, pid))

    deliveries = []
    for innings_no, inn in enumerate(data.get("innings", []), start=1):
        batting_team = inn.get("team")
        bowling_team = teams[1] if batting_team == teams[0] else teams[0]
        is_super_over = bool(inn.get("super_over", False))
        for over in inn.get("overs", []):
            over_no = over.get("over", 0)
            for ball_no, d in enumerate(over.get("deliveries", []), start=1):
                extras = d.get("extras", {}) or {}
                runs = d.get("runs", {}) or {}
                is_wide = "wides" in extras
                is_noball = "noballs" in extras
                wickets = d.get("wickets", []) or []
                wk = wickets[0] if wickets else None
                kind = wk.get("kind") if wk else None
                deliveries.append(
                    (
                        match_id, innings_no, batting_team, bowling_team, over_no, ball_no,
                        registry.get(d.get("batter"), d.get("batter")),
                        registry.get(d.get("bowler"), d.get("bowler")),
                        int(runs.get("batter", 0)), int(runs.get("extras", 0)), int(runs.get("total", 0)),
                        is_wide, is_noball, not (is_wide or is_noball),
                        wk is not None, kind,
                        registry.get(wk.get("player_out"), wk.get("player_out")) if wk else None,
                        kind in BOWLER_CREDITED_KINDS if kind else False,
                        int(runs.get("batter", 0)) == 4 and not d.get("runs", {}).get("non_boundary", False),
                        int(runs.get("batter", 0)) == 6 and not d.get("runs", {}).get("non_boundary", False),
                        is_super_over,
                    )
                )
    return {"match": match, "players": players, "appearances": appearances, "deliveries": deliveries}


MATCH_COLS = ("match_id", "date", "competition", "season", "stage", "match_type", "gender",
              "team1", "team2", "venue", "city", "winner", "result", "margin", "source")
DELIVERY_COLS = ("match_id", "innings_no", "batting_team", "bowling_team", "over_no", "ball_no", "batter_id", "bowler_id",
                 "runs_batter", "runs_extras", "runs_total", "is_wide", "is_noball", "legal_ball", "is_wicket", "wicket_kind",
                 "player_out_id", "bowler_credited", "is_four", "is_six", "is_super_over")


def load_zip(con, zip_path: Path, gender_filter: str = "female", batch_matches: int = 400) -> int:
    """Load every JSON match in a Cricsheet zip into the canonical tables (bulk inserts via DataFrames)."""
    import pandas as pd

    n = 0
    buf = {"matches": [], "players": {}, "appearances": [], "deliveries": []}

    def flush():
        if not buf["matches"]:
            return
        mdf = pd.DataFrame(buf["matches"], columns=MATCH_COLS)
        ids = mdf["match_id"].tolist()
        con.register("_m", mdf)
        con.execute("DELETE FROM matches WHERE match_id IN (SELECT match_id FROM _m)")
        con.execute("DELETE FROM appearances WHERE match_id IN (SELECT match_id FROM _m)")
        con.execute("DELETE FROM deliveries WHERE match_id IN (SELECT match_id FROM _m)")
        con.execute("INSERT INTO matches SELECT * FROM _m")
        con.unregister("_m")
        pdf = pd.DataFrame([(pid, nm, nm, None) for pid, nm in buf["players"].items()], columns=["player_id", "name", "unique_name", "key_cricinfo"])
        con.register("_p", pdf)
        con.execute("INSERT OR IGNORE INTO players SELECT * FROM _p")
        con.unregister("_p")
        adf = pd.DataFrame(buf["appearances"], columns=["match_id", "team", "player_id"])
        con.register("_a", adf)
        con.execute("INSERT INTO appearances SELECT * FROM _a")
        con.unregister("_a")
        ddf = pd.DataFrame(buf["deliveries"], columns=DELIVERY_COLS)
        con.register("_d", ddf)
        con.execute("INSERT INTO deliveries SELECT * FROM _d")
        con.unregister("_d")
        buf["matches"].clear(); buf["players"].clear(); buf["appearances"].clear(); buf["deliveries"].clear()

    with zipfile.ZipFile(zip_path) as zf:
        names = [n_ for n_ in zf.namelist() if n_.endswith(".json")]
        for name in names:
            with zf.open(name) as fh:
                try:
                    data = json.load(fh)
                except json.JSONDecodeError:
                    log.warning("bad json %s", name)
                    continue
            parsed = parse_match(data, name, gender_filter)
            if not parsed:
                continue
            m = parsed["match"]
            buf["matches"].append(tuple(m[k] for k in MATCH_COLS))
            buf["players"].update(parsed["players"])
            buf["appearances"].extend(parsed["appearances"])
            buf["deliveries"].extend(parsed["deliveries"])
            n += 1
            if len(buf["matches"]) >= batch_matches:
                flush()
                log.info("%s: %s matches loaded so far", zip_path.name, n)
    flush()
    return n


def _insert(con, parsed: dict) -> None:
    """Insert one parsed match (used by tests)."""
    m = parsed["match"]
    con.execute("DELETE FROM matches WHERE match_id = ?", [m["match_id"]])
    con.execute("INSERT INTO matches VALUES (" + ",".join("?" * len(MATCH_COLS)) + ")", [m[k] for k in MATCH_COLS])
    for pid, name in parsed["players"].items():
        con.execute("INSERT OR IGNORE INTO players (player_id, name, unique_name, key_cricinfo) VALUES (?,?,?,NULL)", [pid, name, name])
    con.execute("DELETE FROM appearances WHERE match_id = ?", [m["match_id"]])
    con.executemany("INSERT INTO appearances VALUES (?,?,?)", parsed["appearances"])
    con.execute("DELETE FROM deliveries WHERE match_id = ?", [m["match_id"]])
    if parsed["deliveries"]:
        con.executemany("INSERT INTO deliveries VALUES (" + ",".join("?" * len(DELIVERY_COLS)) + ")", parsed["deliveries"])


def load_register(con, csv_path: Path) -> int:
    """People register: identifier,name,unique_name,...,key_cricinfo,... (bulk upsert)."""
    import pandas as pd

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = row.get("identifier")
            if pid:
                rows.append((pid, row.get("name") or row.get("unique_name"), row.get("unique_name"), row.get("key_cricinfo") or None))
    if not rows:
        return 0
    rdf = pd.DataFrame(rows, columns=["player_id", "name", "unique_name", "key_cricinfo"]).drop_duplicates("player_id")
    con.register("_r", rdf)
    con.execute(
        "INSERT INTO players SELECT * FROM _r ON CONFLICT (player_id) DO UPDATE SET "
        "name = excluded.name, unique_name = excluded.unique_name, key_cricinfo = COALESCE(excluded.key_cricinfo, players.key_cricinfo)"
    )
    con.unregister("_r")
    return len(rdf)


def run(con, cfg: dict) -> dict:
    """Download configured competitions and the register, load everything. Returns counts."""
    raw = Path(cfg["paths"]["raw"])
    counts = {}
    for code in cfg["cricsheet"]["competitions"]:
        url = f"{cfg['cricsheet']['base_url']}{code}_json.zip"
        zp = download(url, raw / f"{code}_json.zip")
        if zp is None:
            counts[code] = "unavailable"
            continue
        counts[code] = load_zip(con, zp, cfg["cricsheet"].get("gender", "female"))
    reg = download(cfg["cricsheet"]["register_url"], raw / "people.csv")
    counts["register"] = load_register(con, reg) if reg else "unavailable"
    return counts


def parse_register_bytes(raw: bytes) -> list[dict]:
    """Helper used by tests."""
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
