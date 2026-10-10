"""Analysis windows: an event (competition + season) or rolling days."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd


@dataclass
class Window:
    kind: str
    label: str
    start: date
    end: date
    match_ids: list[str] = field(default_factory=list)
    competition: str | None = None
    season: str | None = None

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def resolve_window(con, cfg: dict) -> Window:
    w = cfg["window"]
    if w["kind"] == "event":
        df = con.execute(
            "SELECT match_id, date FROM matches WHERE competition = ? AND season = ? ORDER BY date",
            [w["competition"], str(w["season"])],
        ).df()
        if df.empty:
            raise ValueError(f"No matches for {w['competition']} {w['season']} — check config.window or the data load")
        return Window(
            kind="event",
            label=f"{w['competition']} {w['season']}",
            start=pd.to_datetime(df["date"].min()).date(),
            end=pd.to_datetime(df["date"].max()).date(),
            match_ids=df["match_id"].tolist(),
            competition=w["competition"],
            season=str(w["season"]),
        )
    days = int(w.get("days", 28))
    end = pd.to_datetime(con.execute("SELECT MAX(date) FROM matches").fetchone()[0]).date()
    start = end - timedelta(days=days - 1)
    df = con.execute("SELECT match_id FROM matches WHERE date BETWEEN ? AND ? ORDER BY date", [start, end]).df()
    return Window(kind="days", label=f"Last {days} days to {end.isoformat()}", start=start, end=end,
                  match_ids=df["match_id"].tolist())


def window_players(con, window: Window) -> pd.DataFrame:
    """Per-player aggregates inside the window."""
    ids = window.match_ids
    if not ids:
        return pd.DataFrame()
    placeholders = ",".join("?" * len(ids))
    df = con.execute(
        f"""
        SELECT pm.player_id, COALESCE(n.display_name, p.name) AS name, p.name AS short_name, p.key_cricinfo, pm.team,
               COUNT(*) AS matches,
               SUM(runs) AS runs, SUM(balls_faced) AS balls_faced,
               SUM(CASE WHEN batted THEN 1 ELSE 0 END) AS innings,
               SUM(CASE WHEN dismissed THEN 1 ELSE 0 END) AS dismissals,
               MAX(runs) AS best_score,
               SUM(wickets) AS wickets, SUM(balls_bowled) AS balls_bowled, SUM(runs_conceded) AS runs_conceded,
               SUM(impact) AS impact,
               SUM(CASE WHEN won THEN 1 ELSE 0 END) AS wins
        FROM player_match pm JOIN players p USING (player_id)
        LEFT JOIN player_names n USING (player_id)
        WHERE pm.match_id IN ({placeholders})
        GROUP BY 1,2,3,4,5
        """,
        ids,
    ).df()
    import numpy as np
    for col in ("runs", "balls_faced", "innings", "dismissals", "best_score", "wickets", "balls_bowled", "runs_conceded", "impact", "wins", "matches"):
        df[col] = df[col].fillna(0).astype(float)
    df["strike_rate"] = np.where(df["balls_faced"] > 0, (100 * df["runs"] / df["balls_faced"].replace(0, np.nan)).round(1), np.nan)
    df["economy"] = np.where(df["balls_bowled"] > 0, (6 * df["runs_conceded"] / df["balls_bowled"].replace(0, np.nan)).round(2), np.nan)
    df["batting_average"] = np.where(df["dismissals"] > 0, (df["runs"] / df["dismissals"].replace(0, np.nan)).round(1), np.nan)
    # role inference (documented heuristic)
    def role(r):
        bat = r.balls_faced >= 20
        bowl = r.balls_bowled >= 24
        if bat and bowl:
            return "all-rounder"
        if bowl:
            return "bowler"
        if bat:
            return "batter"
        return "batter" if r.balls_faced >= r.balls_bowled else "bowler"
    df["role"] = df.apply(role, axis=1)
    df = df.sort_values("impact", ascending=False).reset_index(drop=True)
    df["impact_rank"] = range(1, len(df) + 1)
    return df
