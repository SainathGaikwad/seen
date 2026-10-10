"""Unit tests for the parts that must never silently break: parsing, claim checking, gap fitting, XI constraints."""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seen import db
from seen.ingest.cricsheet import parse_match
from seen.intelligence.gap import fit_gap
from seen.intelligence.unseen_xi import select_xi
from seen.stories import claim_check

SAMPLE = {
    "info": {
        "dates": ["2026-06-13"], "event": {"name": "ICC Women's T20 World Cup", "match_number": 2}, "season": "2026",
        "match_type": "IT20", "gender": "female", "teams": ["Ireland", "Scotland"], "venue": "Old Trafford", "city": "Manchester",
        "outcome": {"winner": "Scotland", "by": {"runs": 40}},
        "players": {"Ireland": ["A Player", "B Bowler"], "Scotland": ["C Bat", "D Spin"]},
        "registry": {"people": {"A Player": "p1", "B Bowler": "p2", "C Bat": "p3", "D Spin": "p4"}},
    },
    "innings": [
        {"team": "Scotland", "overs": [{"over": 0, "deliveries": [
            {"batter": "C Bat", "bowler": "B Bowler", "non_striker": "D Spin", "runs": {"batter": 4, "extras": 0, "total": 4}},
            {"batter": "C Bat", "bowler": "B Bowler", "non_striker": "D Spin", "runs": {"batter": 0, "extras": 1, "total": 1}, "extras": {"wides": 1}},
            {"batter": "C Bat", "bowler": "B Bowler", "non_striker": "D Spin", "runs": {"batter": 0, "extras": 0, "total": 0},
             "wickets": [{"kind": "bowled", "player_out": "C Bat"}]},
        ]}]},
        {"team": "Ireland", "overs": [{"over": 0, "deliveries": [
            {"batter": "A Player", "bowler": "D Spin", "non_striker": "B Bowler", "runs": {"batter": 6, "extras": 0, "total": 6}},
        ]}]},
    ],
}


def test_parse_match_and_player_match(tmp_path):
    parsed = parse_match(SAMPLE, "1234567.json")
    assert parsed["match"]["match_id"] == "1234567"
    assert parsed["match"]["winner"] == "Scotland" and parsed["match"]["margin"] == "40 runs"
    assert len(parsed["deliveries"]) == 4
    wide = parsed["deliveries"][1]
    assert wide[11] is True and wide[13] is False  # is_wide, legal_ball
    con = db.connect(str(tmp_path / "t.duckdb"))
    from seen.ingest.cricsheet import _insert
    _insert(con, parsed)
    db.build_player_match(con)
    pm = con.execute("SELECT player_id, runs, balls_faced, wickets, balls_bowled, runs_conceded FROM player_match ORDER BY player_id").df()
    row = pm.set_index("player_id")
    assert row.loc["p3", "runs"] == 4 and row.loc["p3", "balls_faced"] == 2   # wide not a ball faced
    assert row.loc["p2", "wickets"] == 1 and row.loc["p2", "balls_bowled"] == 2 and row.loc["p2", "runs_conceded"] == 5
    assert row.loc["p1", "runs"] == 6


def test_parse_match_filters_gender():
    male = json.loads(json.dumps(SAMPLE))
    male["info"]["gender"] = "male"
    assert parse_match(male, "x.json") is None


def test_claim_check_blocks_invented_numbers():
    facts = [{"id": "F1", "type": "window_runs", "text": "scored 145 runs", "value": 145, "source": "x"},
             {"id": "F2", "type": "strike_rate", "text": "strike rate 99.3", "value": 99.3, "source": "x"}]
    ok = claim_check.check("She scored 145 runs [F1] at 99.3 [F2].", facts, ["Hayley Matthews"])
    assert ok.passed
    bad = claim_check.check("She scored 150 runs [F1].", facts, ["Hayley Matthews"])
    assert not bad.passed and any(c["status"] == "unmatched" for c in bad.claims)
    banned = claim_check.check("She scored 145 runs despite an injury.", facts, ["Hayley Matthews"])
    assert not banned.passed and "health or medical speculation" in banned.banned


def test_claim_check_ignores_structure():
    facts = [{"id": "F1", "type": "window_runs", "text": "scored 12 runs", "value": 12, "source": "cricsheet:1490703"}]
    txt = "[00:00-00:05] Intro.\nPost 1: scored 12 runs [F1] (source: cricsheet:1490703) on 2026-06-27"
    assert claim_check.check(txt, facts, []).passed


def _players(n=40, seed=1):
    rng = np.random.default_rng(seed)
    teams = rng.choice(["India", "England", "Australia", "Ireland", "Scotland", "Pakistan", "Thailand"], n)
    df = pd.DataFrame({"player_id": [f"p{i}" for i in range(n)], "name": [f"Player {i}" for i in range(n)], "team": teams,
                       "role": rng.choice(["batter", "bowler", "all-rounder"], n), "impact": rng.integers(10, 300, n),
                       "matches": rng.integers(2, 7, n), "runs": rng.integers(0, 250, n), "wickets": rng.integers(0, 12, n)})
    df = df.sort_values("impact", ascending=False).reset_index(drop=True)
    df["impact_rank"] = range(1, n + 1)
    return df


def test_gap_fit_and_xi_constraints(tmp_path):
    players = _players()
    sig = pd.DataFrame({"player_id": players.player_id, "significance": np.linspace(0.9, 0.1, len(players)),
                        "best_candidate": "C1", "best_pattern": "TOP_PERFORMER", "best_headline": "h", "n_candidates": 1})
    rng = np.random.default_rng(3)
    tier = players.team.map({"India": 3, "England": 2, "Australia": 2}).fillna(1).astype(int)
    views = (np.exp(3 + 1.2 * sig.significance + 0.8 * np.log(tier) + rng.normal(0, 0.3, len(players)))).astype(int)
    att = pd.DataFrame({"player_id": players.player_id, "name": players.name, "team": players.team, "market_tier": tier,
                        "views_window_total": views, "baseline_daily": views / 30, "no_article": False, "editions": "en",
                        "attention_source": "test", "expected_views": None})
    att.loc[att.index[:3], ["views_window_total", "no_article"]] = [0, True]
    gap, summary = fit_gap(players, sig, att, 24)
    assert summary["n_fit"] == len(players) - 3
    assert summary["structural_model"]["r2"] > 0.5          # market + fame explain most of the synthetic attention
    assert summary["performance_model"]["r2"] is not None
    assert (gap["gap"] - (gap["gap_structural"] + gap["gap_anomaly"])).abs().max() < 1e-9  # decomposition adds up
    assert gap.iloc[0].no_article  # no-article athletes have the largest gap
    cfg = {"unseen_xi": {"size": 11, "max_per_country": 3, "min_outside_big_three": 3, "min_batters": 4, "min_bowlers": 4,
                         "cooldown_days": 14, "max_impact_rank": 60, "max_no_article": 2, "min_matches": 2}, "big_three": ["India", "England", "Australia"]}
    xi, notes = select_xi(gap, cfg, date(2026, 7, 5), tmp_path)
    assert len(xi) == 11
    assert xi.team.value_counts().max() <= 3
    assert (~xi.team.isin(cfg["big_three"])).sum() >= 3
    assert xi.no_article.sum() <= 2
    # a publication dated inside the window is this release's own: re-running the window keeps the XI;
    # a feature before the window (within the cooldown) drops her
    first = xi.iloc[0].player_id
    pd.DataFrame({"player_id": [first], "featured_date": ["2026-06-28"]}).to_csv(tmp_path / "featured_log.csv", index=False)
    same, _ = select_xi(gap, cfg, date(2026, 7, 5), tmp_path, window_start=date(2026, 6, 12))
    assert same.iloc[0].player_id == first
    pd.DataFrame({"player_id": [first], "featured_date": ["2026-06-30"]}).to_csv(tmp_path / "featured_log.csv", index=False)
    dropped, notes2 = select_xi(gap, cfg, date(2026, 7, 5), tmp_path, window_start=date(2026, 7, 1))
    assert first not in set(dropped.player_id) and any("featured recently" in n for n in notes2)


def test_kits_and_translations_survive_a_run_without_llm(tmp_path):
    """A model-written kit (and its finished translation) is kept when the facts and text are unchanged and the
    model cannot answer this run; it is rebuilt when a fact changed."""
    from seen import pipeline
    facts = [{"id": "F1", "type": "impact_rank", "text": "ranked 1 of 165", "value": 1, "source": "aggregate"},
             {"id": "F2", "type": "expected_views", "text": "expected views: 24500", "value": 24500, "source": "model"}]
    old = {"player_id": "p1", "name": "A B", "team": "Ireland", "mode": "llm+template", "generated_at": "2026-09-27T00:00:00+00:00", "facts": facts,
           "formats": {k: "She was ranked 1 [F1] of 165 [F1] with 24,500 [F2] expected." for k in pipeline.compiler.FORMATS}}
    old["formats"]["infographic"] = "{}"; old["formats"]["quiz"] = "[]"
    new = {"player_id": "p1", "name": "A B", "team": "Ireland", "mode": "template", "facts": [dict(f) for f in facts],
           "formats": {k: "Template line ranked 1 [F1]." for k in pipeline.compiler.FORMATS}}
    new["formats"]["infographic"] = "{}"; new["formats"]["quiz"] = "[]"
    kept = pipeline._reuse_kit(dict(new), old)
    assert kept["mode"] == "llm+template" and kept["formats"]["article"] == old["formats"]["article"]
    changed = dict(new); changed["facts"] = [dict(facts[0]), dict(facts[1], value=24600, text="expected views: 24600")]
    assert pipeline._reuse_kit(changed, old)["mode"] == "template"
    loc = {"language": "hi", "status": "translated and claim-checked", "checks": {"article": {"passed": True}}, "formats": {"article": "…"}}
    assert pipeline._reuse_loc(kept, old, loc) is loc
    assert pipeline._reuse_loc(new, old, loc) is None                      # English text differs: translate again
    assert pipeline._reuse_loc(kept, old, dict(loc, status="translation failed: quota", checks={})) is None


def test_expected_views_fact_is_rounded():
    from seen.stories.compiler import round_sig
    assert round_sig(24548) == 24500 and round_sig(24546) == 24500 and round_sig(713) == 713 and round_sig(1238.4) == 1240


def test_nebius_provider_is_selected_by_key(monkeypatch):
    from seen import llm
    monkeypatch.setenv("LLM_PROVIDER", "nebius")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert llm.provider() == "none"                       # a provider without its key is not available
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    assert llm.provider() == "nebius"
    assert llm._models("nebius")[0].startswith("nvidia/") and "Nemotron" in llm.model_label()
    monkeypatch.setenv("NEBIUS_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    assert llm._models("nebius") == ["nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"]


def test_live_rewrite_is_gated_by_the_claim_checker(monkeypatch):
    """The app's 'Rewrite with the model' path: a draft with an invented number is blocked and the verified text kept;
    a faithful draft replaces it and the previous version is remembered."""
    from seen import llm
    from seen.stories import compiler
    facts = [{"id": "F1", "type": "impact_rank", "text": "ranked 1 of 165", "value": 1, "source": "aggregate"},
             {"id": "F2", "type": "window_runs", "text": "scored 145 runs", "value": 145, "source": "aggregate"}]
    kit = {"player_id": "p1", "name": "A B", "team": "Ireland", "headline": "h", "mode": "template", "facts": facts,
           "formats": {k: "Ranked 1 [F1] of 165 [F1]; 145 runs [F2]." for k in compiler.FORMATS}, "checks": {}}
    kit["formats"]["infographic"] = "{}"; kit["formats"]["quiz"] = "[]"
    kit["checks"] = compiler.run_checks(kit)
    monkeypatch.setattr(llm, "complete", lambda system, user, max_tokens=2000: json.dumps({"article": "A B scored 150 runs [F2] and was ranked 1 [F1] of 165 [F1]."}))
    monkeypatch.setattr(llm, "model_label", lambda: "test model")
    out = compiler.rewrite_format(kit, "article", angle="playful")
    assert not out["accepted"] and kit["formats"]["article"].startswith("Ranked 1") and kit["rejected"]["article"]["text"].startswith("A B scored 150")
    monkeypatch.setattr(llm, "complete", lambda system, user, max_tokens=2000: json.dumps({"article": "A B, ranked 1 [F1] of 165 [F1], made 145 runs [F2] look easy."}))
    out = compiler.rewrite_format(kit, "article")
    assert out["accepted"] and kit["mode"] == "llm+template" and kit["generated"]["article"].startswith("Ranked 1")
    assert kit["checks"]["article"]["passed"] and kit["rewrites"][-1]["model"] == "test model" and kit["text_rev"] == 1
    assert compiler.rewrite_format(kit, "quiz")["error"]
    # a model that hands the current text back is not a rewrite
    monkeypatch.setattr(llm, "complete", lambda system, user, max_tokens=2000: json.dumps({"article": kit["formats"]["article"] + "  "}))
    same = compiler.rewrite_format(kit, "article")
    assert not same["accepted"] and "unchanged" in same["error"] and kit["text_rev"] == 1
