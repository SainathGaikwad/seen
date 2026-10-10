"""DuckDB schema for the Women's Cricket Graph (canonical tables).

Two loaders populate it: `seen.ingest.cricsheet` (real path: Cricsheet JSON) and
`seen.ingest.mirror` (development only: a third-party DuckDB build of Cricsheet).
Everything downstream reads only these canonical tables.
"""
from __future__ import annotations

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    date DATE,
    competition TEXT,
    season TEXT,
    stage TEXT,
    match_type TEXT,
    gender TEXT,
    team1 TEXT,
    team2 TEXT,
    venue TEXT,
    city TEXT,
    winner TEXT,
    result TEXT,          -- win | tie | no result
    margin TEXT,
    source TEXT           -- e.g. cricsheet:<file> or mirror
);
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    name TEXT,
    unique_name TEXT,
    key_cricinfo TEXT
);
CREATE TABLE IF NOT EXISTS player_names (
    player_id TEXT PRIMARY KEY,
    display_name TEXT,
    source TEXT            -- alias | wikidata | manual
);
CREATE TABLE IF NOT EXISTS appearances (
    match_id TEXT,
    team TEXT,
    player_id TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
    match_id TEXT,
    innings_no INTEGER,
    batting_team TEXT,
    bowling_team TEXT,
    over_no INTEGER,
    ball_no INTEGER,
    batter_id TEXT,
    bowler_id TEXT,
    runs_batter INTEGER,
    runs_extras INTEGER,
    runs_total INTEGER,
    is_wide BOOLEAN,
    is_noball BOOLEAN,
    legal_ball BOOLEAN,
    is_wicket BOOLEAN,
    wicket_kind TEXT,
    player_out_id TEXT,
    bowler_credited BOOLEAN,
    is_four BOOLEAN,
    is_six BOOLEAN,
    is_super_over BOOLEAN
);
"""

BOWLER_CREDITED_KINDS = {"caught", "bowled", "lbw", "stumped", "caught and bowled", "hit wicket"}


def connect(path: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path, read_only=read_only)
    if not read_only:
        con.execute(SCHEMA)
    return con


def reset(con: duckdb.DuckDBPyConnection) -> None:
    for t in ("matches", "players", "player_names", "appearances", "deliveries"):
        con.execute(f"DELETE FROM {t}")


def apply_competition_aliases(con: duckdb.DuckDBPyConnection, aliases: dict[str, list[str]]) -> int:
    """Unify historical competition names (e.g. 'Women's World T20' → 'ICC Women's T20 World Cup')."""
    n = 0
    for canonical, olds in (aliases or {}).items():
        for old in olds:
            n += con.execute("UPDATE matches SET competition = ? WHERE competition = ?", [canonical, old]).fetchone()[0] or 0
    return n


def upsert_display_names(con: duckdb.DuckDBPyConnection, rows: list[tuple[str, str, str]]) -> None:
    for pid, name, source in rows:
        if not isinstance(name, str) or not name.strip() or name.strip().lower() in ("nan", "none", "null"):
            continue
        if __import__("re").fullmatch(r"Q\d+", name.strip()):
            continue
        con.execute(
            "INSERT INTO player_names VALUES (?,?,?) ON CONFLICT (player_id) DO UPDATE SET "
            "display_name = CASE WHEN player_names.source = 'manual' AND excluded.source <> 'manual' THEN player_names.display_name ELSE excluded.display_name END, "
            "source = CASE WHEN player_names.source = 'manual' AND excluded.source <> 'manual' THEN player_names.source ELSE excluded.source END",
            [pid, name, source])


def build_player_match(con: duckdb.DuckDBPyConnection) -> None:
    """Derived table: one row per player per match with batting and bowling totals."""
    con.execute("DROP TABLE IF EXISTS player_match")
    con.execute(
        """
        CREATE TABLE player_match AS
        WITH bat AS (
            SELECT match_id, batter_id AS player_id, batting_team AS team,
                   SUM(runs_batter) AS runs,
                   SUM(CASE WHEN is_wide THEN 0 ELSE 1 END) AS balls_faced,
                   SUM(CASE WHEN is_four THEN 1 ELSE 0 END) AS fours,
                   SUM(CASE WHEN is_six THEN 1 ELSE 0 END) AS sixes
            FROM deliveries WHERE NOT is_super_over GROUP BY 1,2,3
        ),
        outs AS (
            SELECT match_id, player_out_id AS player_id, COUNT(*) AS dismissed
            FROM deliveries WHERE is_wicket AND player_out_id IS NOT NULL AND NOT is_super_over
              AND wicket_kind NOT IN ('retired hurt','retired not out')
            GROUP BY 1,2
        ),
        bowl AS (
            SELECT match_id, bowler_id AS player_id, bowling_team AS team,
                   SUM(CASE WHEN is_wicket AND bowler_credited THEN 1 ELSE 0 END) AS wickets,
                   SUM(CASE WHEN legal_ball THEN 1 ELSE 0 END) AS balls_bowled,
                   -- bowler concedes batter runs plus wides and no-balls (byes and leg-byes excluded)
                   SUM(runs_batter + CASE WHEN is_wide OR is_noball THEN runs_extras ELSE 0 END) AS runs_conceded
            FROM deliveries WHERE NOT is_super_over GROUP BY 1,2,3
        ),
        app AS (SELECT match_id, team, player_id FROM appearances)
        SELECT a.match_id, a.player_id, a.team,
               m.date, m.competition, m.season, m.stage,
               CASE WHEN m.team1 = a.team THEN m.team2 ELSE m.team1 END AS opponent,
               m.winner = a.team AS won,
               COALESCE(b.runs, 0) AS runs,
               COALESCE(b.balls_faced, 0) AS balls_faced,
               COALESCE(b.fours, 0) AS fours,
               COALESCE(b.sixes, 0) AS sixes,
               COALESCE(o.dismissed, 0) > 0 AS dismissed,
               b.player_id IS NOT NULL AS batted,
               COALESCE(w.wickets, 0) AS wickets,
               COALESCE(w.balls_bowled, 0) AS balls_bowled,
               COALESCE(w.runs_conceded, 0) AS runs_conceded,
               w.player_id IS NOT NULL AS bowled
        FROM app a
        JOIN matches m USING (match_id)
        LEFT JOIN bat b ON b.match_id = a.match_id AND b.player_id = a.player_id
        LEFT JOIN outs o ON o.match_id = a.match_id AND o.player_id = a.player_id
        LEFT JOIN bowl w ON w.match_id = a.match_id AND w.player_id = a.player_id
        """
    )
    con.execute(
        """
        ALTER TABLE player_match ADD COLUMN impact DOUBLE;
        UPDATE player_match SET impact = runs + 20 * wickets;
        """
    )
