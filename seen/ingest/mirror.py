"""Development-only loader: a third-party DuckDB warehouse built from Cricsheet.

Used when cricsheet.org is unreachable (some corporate networks). Maps the
mirror's tables into the canonical schema. Never use for published numbers —
re-derive from Cricsheet JSON with `seen.ingest.cricsheet`.
"""
from __future__ import annotations

import logging

import duckdb

log = logging.getLogger(__name__)


def run(con: duckdb.DuckDBPyConnection, mirror_path: str, gender: str = "female") -> dict:
    con.execute(f"ATTACH '{mirror_path}' AS mirror (READ_ONLY)")
    try:
        con.execute("DELETE FROM matches; DELETE FROM players; DELETE FROM player_names; DELETE FROM appearances; DELETE FROM deliveries;")
        con.execute(
            """
            INSERT INTO matches
            SELECT match_id, start_date, competition, season,
                   CASE WHEN event_match_number IS NOT NULL THEN 'Match ' || event_match_number END,
                   format, gender,
                   NULL, NULL, venue_canonical, city, winner, result_type,
                   CASE WHEN margin_runs IS NOT NULL THEN margin_runs || ' runs'
                        WHEN margin_wickets IS NOT NULL THEN margin_wickets || ' wickets' END,
                   'mirror'
            FROM mirror.matches WHERE gender = ?
            """,
            [gender],
        )
        # teams from innings (batting/bowling teams)
        con.execute(
            """
            UPDATE matches SET team1 = t.t1, team2 = t.t2 FROM (
                SELECT match_id, MIN(batting_team) AS t1, MAX(batting_team) AS t2
                FROM (SELECT match_id, batting_team FROM mirror.innings
                      UNION SELECT match_id, bowling_team FROM mirror.innings) GROUP BY 1
            ) t WHERE matches.match_id = t.match_id
            """
        )
        con.execute(
            """
            INSERT INTO players
            SELECT player_id, unique_name, unique_name, key_cricinfo FROM mirror.players
            """
        )
        con.execute(
            """
            INSERT INTO deliveries
            SELECT d.match_id, d.innings_no, d.batting_team, d.bowling_team, d.over_number, d.ball_in_over,
                   d.batter_id, d.bowler_id, d.runs_batter, d.runs_extras, d.runs_total,
                   d.is_wide, d.is_noball, NOT (d.is_wide OR d.is_noball),
                   w.player_out_id IS NOT NULL, w.kind, w.player_out_id, COALESCE(w.is_bowler_credited, FALSE),
                   d.is_four, d.is_six, COALESCE(d.is_super_over, FALSE)
            FROM mirror.deliveries d
            LEFT JOIN (
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY match_id, innings_no, over_number, ball_in_over
                                                 ORDER BY wicket_idx) AS rn
                    FROM mirror.wickets
                ) WHERE rn = 1
            ) w
              ON w.match_id = d.match_id AND w.innings_no = d.innings_no
             AND w.over_number = d.over_number AND w.ball_in_over = d.ball_in_over
            WHERE d.gender = ?
            """,
            [gender],
        )
        # display names: an alias that looks like a full name (no initials) beats the register's short form
        con.execute(
            """
            INSERT INTO player_names
            SELECT player_id, alias, 'alias' FROM (
                SELECT a.player_id, a.alias,
                       ROW_NUMBER() OVER (PARTITION BY a.player_id ORDER BY LENGTH(a.alias) DESC) AS rn
                FROM mirror.player_aliases a JOIN mirror.players p USING (player_id)
                WHERE a.alias <> p.unique_name
                  AND regexp_matches(a.alias, '^[A-Z][a-z]+ [A-Z]')      -- "Hayley Matthews", not "H Matthews"
                  AND NOT regexp_matches(a.alias, '^[A-Z]{1,3} ')
            ) WHERE rn = 1
            """
        )
        # appearances inferred from participation (mirror has no playing-XI table)
        con.execute(
            """
            INSERT INTO appearances
            SELECT DISTINCT match_id, team, player_id FROM (
                SELECT match_id, batting_team AS team, batter_id AS player_id FROM deliveries
                UNION SELECT match_id, batting_team, bowler_id FROM deliveries WHERE FALSE
                UNION SELECT match_id, bowling_team, bowler_id FROM deliveries
                UNION SELECT match_id, batting_team, player_out_id FROM deliveries WHERE player_out_id IS NOT NULL
            ) WHERE player_id IS NOT NULL
            """
        )
        n = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        log.info("mirror loaded: %s matches", n)
        return {"matches": n, "note": "appearances inferred from batting/bowling participation"}
    finally:
        con.execute("DETACH mirror")
