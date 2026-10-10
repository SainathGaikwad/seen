"""Fan discovery feed: athlete-first ranking with exploration slots, and event logging."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

EVENT_COLUMNS = ["ts", "fan_id", "player_id", "event", "channel", "language"]


def rank_cards(xi: pd.DataFrame, interests: dict, cfg: dict) -> pd.DataFrame:
    """interests: {"teams": [...], "roles": [...], "language": "hi", "country": "India"}"""
    if xi.empty:
        return xi
    df = xi.copy()
    teams = set(interests.get("teams", []))
    roles = set(interests.get("roles", []))
    def score(r):
        s = 0.0
        if r.team in teams:
            s += 1.0
        if r.role in roles:
            s += 0.5
        s += 0.3 * float(r.gap_z if pd.notna(r.gap_z) else 0)  # under-seen players get a lift everywhere
        return s
    df["relevance"] = df.apply(score, axis=1)
    df["card_reason"] = df.apply(lambda r: "matches your teams" if r.team in teams else ("matches your favourite roles" if r.role in roles else "new to you"), axis=1)
    top = df.sort_values("relevance", ascending=False)
    # exploration: guarantee N cards from outside the fan's stated teams
    explore = top[~top.team.isin(teams)].head(int(cfg["fan_feed"]["exploration_slots"]))
    rest = top.drop(explore.index)
    out = pd.concat([rest.head(3), explore, rest.iloc[3:]]).drop_duplicates("player_id")
    return out.reset_index(drop=True)


def log_event(derived_dir: Path, fan_id: str, player_id: str, event: str, channel: str = "fan_feed", language: str = "en") -> None:
    path = derived_dir / "fan_events.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(EVENT_COLUMNS)
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), fan_id, player_id, event, channel, language])


def load_events(derived_dir: Path) -> pd.DataFrame:
    path = derived_dir / "fan_events.csv"
    if not path.exists():
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.read_csv(path)
