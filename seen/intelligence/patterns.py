"""Narrative-pattern library: turns graph facts into story candidates.

Every candidate carries: the player, the pattern, a factual headline, a rarity
count (how many times this has happened before), stakes, magnitude, arc flags
and a list of facts with IDs and sources. No free text is generated here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .windows import Window, window_players

log = logging.getLogger(__name__)

ICC_EVENT_KEYWORDS = ("World Cup", "Champions Trophy", "World Twenty20", "World T20")


def _magnitude(z: float) -> float:
    """z-score of impact / 3, clipped to [-0.5, 1] (same transform as significance.magnitude_from_z)."""
    return max(-0.5, min(1.0, z / 3.0))


@dataclass
class Fact:
    id: str
    type: str
    text: str
    value: float | int | str | None
    source: str

    def as_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "text": self.text, "value": self.value, "source": self.source}


@dataclass
class Candidate:
    candidate_id: str
    player_id: str
    player_name: str
    team: str
    pattern: str
    headline: str
    rarity_count: int
    stakes: float
    magnitude: float
    arc_flags: list[str] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    match_id: str | None = None

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["facts"] = [f.as_dict() for f in self.facts]
        return d


def stakes_for(competition: str, stage: str | None) -> float:
    c = (competition or "").lower()
    s = 0.4
    if "qualifier" in c:
        s = 0.5
    elif any(k.lower() in c for k in ICC_EVENT_KEYWORDS):
        s = 0.9
    elif any(k in c for k in ("Premier League", "Big Bash", "Hundred", "Super League")):
        s = 0.6
    elif "commonwealth" in c or "asia cup" in c:
        s = 0.7
    st = (stage or "").lower()
    if "final" in st and "semi" not in st and "quarter" not in st:
        s = min(1.0, s + 0.1)
    elif "semi" in st:
        s = min(1.0, s + 0.05)
    return s


class PatternEngine:
    def __init__(self, con, cfg: dict, window: Window, players: pd.DataFrame | None = None):
        self.con = con
        self.cfg = cfg
        self.window = window
        self.players = players if players is not None else window_players(con, window)
        self.full_members = set(cfg["full_members"])
        self._fact_counter = 0
        ids = window.match_ids
        ph = ",".join("?" * len(ids))
        self.pm = con.execute(
            f"""SELECT pm.*, p.name AS short_name FROM player_match pm JOIN players p USING (player_id)
                WHERE pm.match_id IN ({ph})""", ids).df()
        names = dict(zip(self.players["player_id"], self.players["name"]))
        self.pm["name"] = self.pm["player_id"].map(names).fillna(self.pm["short_name"])
        self.matches = con.execute(
            f"SELECT * FROM matches WHERE match_id IN ({ph})", ids).df()
        self.matches_by_id = self.matches.set_index("match_id")
        # magnitude: z-score of window impact among players with at least one match
        imp = self.players["impact"].astype(float)
        self.z = (imp - imp.mean()) / (imp.std(ddof=0) or 1.0)
        self.zmap = dict(zip(self.players["player_id"], self.z))
        self.namemap = dict(zip(self.players["player_id"], self.players["name"]))
        self.teammap = dict(zip(self.players["player_id"], self.players["team"]))

    # ------------------------------------------------------------------ helpers
    def _fid(self) -> str:
        self._fact_counter += 1
        return f"F{self._fact_counter}"

    def fact(self, ftype: str, text: str, value, source: str) -> Fact:
        return Fact(self._fid(), ftype, text, value, source)

    def match_facts(self, row) -> list[Fact]:
        m = self.matches_by_id.loc[row.match_id]
        src = f"cricsheet:{row.match_id}"
        facts = []
        line = []
        if row.batted:
            line.append(f"{int(row.runs)} runs off {int(row.balls_faced)} balls")
            facts.append(self.fact("runs_in_match", f"{row['name']} scored {int(row.runs)} off {int(row.balls_faced)} balls v {row.opponent} on {pd.to_datetime(m.date).date().isoformat()}", int(row.runs), src))
            facts.append(self.fact("balls_in_match", f"balls faced v {row.opponent}", int(row.balls_faced), src))
        if row.bowled:
            line.append(f"{int(row.wickets)}/{int(row.runs_conceded)} from {int(row.balls_bowled)} balls")
            facts.append(self.fact("wickets_in_match", f"{row['name']} took {int(row.wickets)} for {int(row.runs_conceded)} from {int(row.balls_bowled)} balls v {row.opponent} on {pd.to_datetime(m.date).date().isoformat()}", int(row.wickets), src))
            facts.append(self.fact("runs_conceded_in_match", f"runs conceded v {row.opponent}", int(row.runs_conceded), src))
        facts.append(self.fact("match_result", f"{m.team1} v {m.team2}, {m.venue or ''}: {m.winner or m.result} won{(' by ' + m.margin) if m.margin else ''}", m.winner or m.result, src))
        return facts

    def aggregate_facts(self, p) -> list[Fact]:
        src = f"aggregate:{self.window.label}"
        f = [
            self.fact("window_matches", f"{p['name']} played {int(p.matches)} matches in {self.window.label}", int(p.matches), src),
            self.fact("window_runs", f"{int(p.runs)} runs off {int(p.balls_faced)} balls in {self.window.label}", int(p.runs), src),
            self.fact("window_balls_faced", "balls faced in window", int(p.balls_faced), src),
            self.fact("window_wickets", f"{int(p.wickets)} wickets from {int(p.balls_bowled)} balls in {self.window.label}", int(p.wickets), src),
            self.fact("window_balls_bowled", "balls bowled in window", int(p.balls_bowled), src),
            self.fact("impact_rank", f"ranked {int(p.impact_rank)} of {len(self.players)} players by impact (runs + 20 x wickets) in {self.window.label}", int(p.impact_rank), src),
            self.fact("impact", "impact score (runs + 20 x wickets)", float(p.impact), src),
        ]
        if p.balls_faced > 0 and not pd.isna(p.strike_rate):
            f.append(self.fact("strike_rate", f"strike rate {p.strike_rate} in {self.window.label}", float(p.strike_rate), src))
        if p.balls_bowled > 0 and not pd.isna(p.economy):
            f.append(self.fact("economy", f"economy {p.economy} in {self.window.label}", float(p.economy), src))
        # her best match with the bat and with the ball, so every kit has a match-level line (match facts cite the Cricsheet id)
        mine = self.pm[self.pm.player_id == p.player_id]
        if not mine.empty:
            best_bat = mine[mine.batted].sort_values(["runs", "balls_faced"], ascending=[False, True]).head(1)
            if not best_bat.empty and int(best_bat.iloc[0].runs) > 0:
                f += [x for x in self.match_facts(best_bat.iloc[0]) if x.type in ("runs_in_match", "balls_in_match")]
            best_bowl = mine[mine.bowled].sort_values(["wickets", "runs_conceded"], ascending=[False, True]).head(1)
            if not best_bowl.empty and int(best_bowl.iloc[0].wickets) > 0:
                f += [x for x in self.match_facts(best_bowl.iloc[0]) if x.type in ("wickets_in_match", "runs_conceded_in_match")]
        f.append(self.fact("team", f"{p['name']} plays for {p.team}", p.team, src))
        f.append(self.fact("competition", f"competition: {self.window.label}", self.window.label, src))
        return f

    def prior_count(self, sql: str, params: list) -> int:
        """Occurrences of a pattern BEFORE the window start (history in the graph)."""
        return int(self.con.execute(sql, params).fetchone()[0])

    # ----------------------------------------------------------------- patterns
    def run(self) -> list[Candidate]:
        cands: list[Candidate] = []
        for fn in (self.p_top_performer, self.p_allround_match, self.p_first_for_country,
                   self.p_competition_record, self.p_team_first_win, self.p_associate_upset,
                   self.p_streak, self.p_debut_impact, self.p_comeback, self.p_career_milestone):
            try:
                cands.extend(fn())
            except Exception as exc:  # a broken pattern must not kill the run
                log.exception("pattern %s failed: %s", fn.__name__, exc)
        for i, c in enumerate(cands):
            c.candidate_id = f"C{i+1}"
        log.info("%s candidates from %s patterns", len(cands), 10)
        return cands

    def _base(self, pid: str, pattern: str, headline: str, rarity: int, stakes: float,
              arc: list[str] | None = None, match_id: str | None = None) -> Candidate:
        return Candidate(
            candidate_id="", player_id=pid, player_name=self.namemap.get(pid, pid), team=self.teammap.get(pid, ""),
            pattern=pattern, headline=headline, rarity_count=rarity, stakes=stakes,
            magnitude=float(_magnitude(self.zmap.get(pid, 0.0))), arc_flags=arc or [], match_id=match_id,
        )

    def p_top_performer(self) -> list[Candidate]:
        out = []
        comp = self.window.competition or ""
        stakes = stakes_for(comp, None)
        top = self.players.head(15)
        for _, p in top.iterrows():
            c = self._base(p.player_id, "TOP_PERFORMER",
                           f"{p['name']} ranked #{int(p.impact_rank)} of {len(self.players)} players by impact in {self.window.label}",
                           rarity=int(p.impact_rank) - 1, stakes=stakes)
            c.facts = self.aggregate_facts(p)
            out.append(c)
        return out

    def p_allround_match(self) -> list[Candidate]:
        out = []
        for _, r in self.pm.iterrows():
            t20 = str(self.matches_by_id.loc[r.match_id].match_type).upper() in ("T20", "IT20")
            need_runs, need_wk = (40, 2) if t20 else (50, 3)
            if r.runs >= need_runs and r.wickets >= need_wk:
                m = self.matches_by_id.loc[r.match_id]
                prior = self.prior_count(
                    """SELECT COUNT(*) FROM player_match WHERE competition = ? AND date < ? AND runs >= ? AND wickets >= ?""",
                    [m.competition, self.window.start, need_runs, need_wk])
                prior_team = self.prior_count(
                    """SELECT COUNT(*) FROM player_match WHERE competition = ? AND date < ? AND runs >= ? AND wickets >= ? AND team = ?""",
                    [m.competition, self.window.start, need_runs, need_wk, r.team])
                head = (f"{r['name']}: {int(r.runs)} runs and {int(r.wickets)} wickets in one match v {r.opponent}"
                        + (f" — the first such all-round performance for {r.team} in the {m.competition}" if prior_team == 0 else ""))
                c = self._base(r.player_id, "ALLROUND_MATCH", head, rarity=prior, stakes=stakes_for(m.competition, m.stage), match_id=r.match_id)
                c.facts = self.match_facts(r) + [
                    self.fact("prior_occurrences", f"all-round matches ({need_runs}+ runs and {need_wk}+ wickets) in {m.competition} history before this window: {prior}", prior, "graph:history"),
                    self.fact("prior_occurrences_team", f"...of which by {r.team} players: {prior_team}", prior_team, "graph:history"),
                ]
                if prior_team == 0:
                    c.arc_flags.append("first_for_country")
                out.append(c)
        return out

    def p_first_for_country(self) -> list[Candidate]:
        out = []
        comp = self.window.competition
        if not comp or not any(k.lower() in comp.lower() for k in ICC_EVENT_KEYWORDS):
            return out
        for _, r in self.pm.iterrows():
            m = self.matches_by_id.loc[r.match_id]
            for kind, col, thr, label in (("50", "runs", 50, "a half-century"), ("4W", "wickets", 4, "four wickets")):
                if r[col] >= thr:
                    prior_team = self.prior_count(
                        f"SELECT COUNT(*) FROM player_match WHERE competition = ? AND date < ? AND {col} >= ? AND team = ?",
                        [comp, self.window.start, thr, r.team])
                    prior_all = self.prior_count(
                        f"SELECT COUNT(*) FROM player_match WHERE competition = ? AND date < ? AND {col} >= ?",
                        [comp, self.window.start, thr])
                    if prior_team == 0:
                        val = f"{int(r.runs)} runs" if col == "runs" else f"{int(r.wickets)} wickets"
                        c = self._base(r.player_id, f"FIRST_FOR_COUNTRY_{kind}",
                                       f"{r['name']} is the first {r.team} player with {label} in the {comp} ({val} v {r.opponent})",
                                       rarity=0, stakes=stakes_for(comp, m.stage), arc=["first_for_country"], match_id=r.match_id)
                        c.facts = self.match_facts(r) + [
                            self.fact("prior_occurrences_team", f"{r.team} players with {label} in {comp} history before this window: 0", 0, "graph:history"),
                            self.fact("prior_occurrences", f"all players with {label} in {comp} history before this window: {prior_all}", prior_all, "graph:history"),
                        ]
                        out.append(c)
        return out

    def p_competition_record(self) -> list[Candidate]:
        out = []
        comp = self.window.competition
        if not comp:
            return out
        for col, label, top_n in (("runs", "score", 3), ("wickets", "bowling figures", 3)):
            hist = self.con.execute(
                f"""SELECT pm.player_id, p.name, pm.team, pm.{col} AS v, pm.match_id, pm.date, pm.opponent, pm.runs_conceded
                    FROM player_match pm JOIN players p USING (player_id)
                    WHERE competition = ? ORDER BY v DESC, runs_conceded ASC LIMIT ?""", [comp, top_n]).df()
            for rank, (_, h) in enumerate(hist.iterrows(), start=1):
                if h.match_id in set(self.window.match_ids):
                    r = self.pm[(self.pm.match_id == h.match_id) & (self.pm.player_id == h.player_id)].iloc[0]
                    m = self.matches_by_id.loc[h.match_id]
                    total = self.prior_count("SELECT COUNT(DISTINCT match_id) FROM player_match WHERE competition = ?", [comp])
                    v = f"{int(h.v)} runs" if col == "runs" else f"{int(h.v)}/{int(h.runs_conceded)}"
                    c = self._base(h.player_id, f"COMPETITION_RECORD_{col.upper()}",
                                   f"{h['name']}'s {v} v {h.opponent} is the #{rank} {label} in {comp} history ({total} matches in the graph)",
                                   rarity=rank - 1, stakes=stakes_for(comp, m.stage), match_id=h.match_id)
                    c.facts = self.match_facts(r) + [self.fact("all_time_rank", f"all-time rank of this {label} in {comp}: {rank}", rank, "graph:history"),
                                                     self.fact("competition_matches", f"matches of {comp} in the graph", total, "graph:history")]
                    out.append(c)
        return out

    def p_team_first_win(self) -> list[Candidate]:
        out = []
        comp = self.window.competition
        if not comp:
            return out
        wins = self.matches[self.matches.result == "win"]
        for _, m in wins.iterrows():
            prior = self.prior_count("SELECT COUNT(*) FROM matches WHERE competition = ? AND winner = ? AND date < ?",
                                     [comp, m.winner, m.date])
            if prior == 0:
                top = self.pm[(self.pm.match_id == m.match_id) & (self.pm.team == m.winner)].sort_values("impact", ascending=False).head(2)
                for _, r in top.iterrows():
                    c = self._base(r.player_id, "TEAM_FIRST_WIN",
                                   f"{r['name']} led {m.winner}'s first-ever win in the {comp} (v {r.opponent})",
                                   rarity=0, stakes=stakes_for(comp, m.stage), arc=["team_first"], match_id=m.match_id)
                    c.facts = self.match_facts(r) + [self.fact("prior_occurrences_team", f"{m.winner} wins in {comp} before {pd.to_datetime(m.date).date().isoformat()}: 0", 0, "graph:history")]
                    out.append(c)
        return out

    def p_associate_upset(self) -> list[Candidate]:
        out = []
        for _, m in self.matches[self.matches.result == "win"].iterrows():
            loser = m.team2 if m.winner == m.team1 else m.team1
            if m.winner not in self.full_members and loser in self.full_members:
                prior = self.prior_count(
                    "SELECT COUNT(*) FROM matches WHERE winner = ? AND (team1 = ? OR team2 = ?) AND date < ?",
                    [m.winner, loser, loser, m.date])
                top = self.pm[(self.pm.match_id == m.match_id) & (self.pm.team == m.winner)].sort_values("impact", ascending=False).head(1)
                for _, r in top.iterrows():
                    c = self._base(r.player_id, "ASSOCIATE_UPSET",
                                   f"{r['name']} starred as Associate Member {m.winner} beat Full Member {loser}",
                                   rarity=prior, stakes=stakes_for(m.competition, m.stage), arc=["associate"], match_id=m.match_id)
                    c.facts = self.match_facts(r) + [self.fact("prior_occurrences", f"{m.winner} wins over {loser} before this match: {prior}", prior, "graph:history")]
                    out.append(c)
        return out

    def p_streak(self) -> list[Candidate]:
        out = []
        for pid in self.players.player_id:
            hist = self.con.execute(
                "SELECT match_id, date, runs, wickets, opponent FROM player_match WHERE player_id = ? AND date <= ? ORDER BY date DESC LIMIT 12",
                [pid, self.window.end]).df()
            n = 0
            for _, h in hist.iterrows():
                if h.runs >= 30 or h.wickets >= 2:
                    n += 1
                else:
                    break
            if n >= 3 and hist.iloc[0].match_id in set(self.window.match_ids):
                c = self._base(pid, "STREAK", f"{self.namemap[pid]} has delivered 30+ runs or 2+ wickets in {n} consecutive matches",
                               rarity=max(0, 6 - n), stakes=stakes_for(self.window.competition or "", None), arc=["streak"])
                c.facts = [self.fact("streak_length", "consecutive matches with 30+ runs or 2+ wickets", n, "graph:history")]
                for _, h in hist.head(n).iterrows():
                    c.facts.append(self.fact("streak_match", f"v {h.opponent} on {pd.to_datetime(h.date).date().isoformat()}: {int(h.runs)} runs, {int(h.wickets)} wickets", int(h.runs), f"cricsheet:{h.match_id}"))
                out.append(c)
        return out

    def p_debut_impact(self) -> list[Candidate]:
        out = []
        for _, r in self.pm.iterrows():
            first = self.con.execute("SELECT MIN(date) FROM player_match WHERE player_id = ?", [r.player_id]).fetchone()[0]
            if first is not None and pd.to_datetime(first).date() == pd.to_datetime(r.date).date() and (r.runs >= 30 or r.wickets >= 2):
                c = self._base(r.player_id, "DEBUT_IMPACT", f"{r['name']} made an immediate impact on debut v {r.opponent}",
                               rarity=1, stakes=stakes_for(self.matches_by_id.loc[r.match_id].competition, None), arc=["debut"], match_id=r.match_id)
                c.facts = self.match_facts(r) + [self.fact("debut_date", "first match in the graph", pd.to_datetime(first).date().isoformat(), "graph:history")]
                out.append(c)
        return out

    def p_comeback(self) -> list[Candidate]:
        out = []
        for _, p in self.players.iterrows():
            prev = self.con.execute("SELECT MAX(date) FROM player_match WHERE player_id = ? AND date < ?", [p.player_id, self.window.start]).fetchone()[0]
            if prev is not None:
                gap = (self.window.start - pd.to_datetime(prev).date()).days
                if gap >= 365 and p.impact >= 60:
                    c = self._base(p.player_id, "COMEBACK", f"{p['name']} returned after {gap} days without a match and ranked #{int(p.impact_rank)} by impact",
                                   rarity=2, stakes=stakes_for(self.window.competition or "", None), arc=["comeback"])
                    c.facts = self.aggregate_facts(p) + [self.fact("days_since_previous_match", "days between previous match and window start", gap, "graph:history")]
                    out.append(c)
        return out

    def p_career_milestone(self) -> list[Candidate]:
        out = []
        for _, p in self.players.iterrows():
            before = self.con.execute(
                "SELECT COALESCE(SUM(runs),0), COALESCE(SUM(wickets),0), COUNT(*) FROM player_match WHERE player_id = ? AND date < ?",
                [p.player_id, self.window.start]).fetchone()
            after = (before[0] + p.runs, before[1] + p.wickets, before[2] + p.matches)
            for idx, (thr, label) in enumerate(((1000, "career runs"), (50, "career wickets"), (50, "career matches"))):
                if idx == 0:
                    b, a = before[0], after[0]
                elif idx == 1:
                    b, a = before[1], after[1]
                else:
                    b, a = before[2], after[2]
                for t in (thr, thr * 2, thr * 3, thr * 4):
                    if b < t <= a:
                        c = self._base(p.player_id, "CAREER_MILESTONE", f"{p['name']} passed {t} {label} (in the formats covered by the graph) during {self.window.label}",
                                       rarity=int(self.prior_count(f"SELECT COUNT(*) FROM (SELECT player_id FROM player_match GROUP BY 1 HAVING {'SUM(runs)' if idx==0 else 'SUM(wickets)' if idx==1 else 'COUNT(*)'} >= ?)", [t])),
                                       stakes=stakes_for(self.window.competition or "", None), arc=["milestone"])
                        c.facts = [self.fact("milestone", f"milestone passed: {t} {label}", int(t), "graph:history"),
                                   self.fact("career_total", f"{label} after the window (graph coverage only)", int(a), "graph:history"),
                                   self.fact("career_total_before", f"{label} before the window", int(b), "graph:history")]
                        out.append(c)
        return out
