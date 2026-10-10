"""SEEN pipeline CLI.

  python -m seen.pipeline load --source cricsheet            # download Cricsheet zips + register, build graph
  python -m seen.pipeline load --source mirror --mirror-path path/to/cricket.duckdb   # dev only
  python -m seen.pipeline run  --attention live              # patterns → significance → attention → gap → XI → kits
  python -m seen.pipeline run  --attention fixture           # same, with a labelled synthetic attention fixture (UI dev)
  python -m seen.pipeline all  --source cricsheet --attention live
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import db
from .config import load_config
from .ingest import cricsheet, mirror
from .intelligence import attention as att_mod
from .intelligence import gap as gap_mod
from .intelligence import significance as sig_mod
from .intelligence import unseen_xi as xi_mod
from .intelligence.patterns import PatternEngine
from .intelligence.windows import resolve_window, window_players
from .stories import compiler, localize

log = logging.getLogger("seen")


def cmd_load(cfg: dict, source: str, mirror_path: str | None) -> dict:
    con = db.connect(cfg["paths"]["db"])
    if source == "mirror":
        if not mirror_path:
            raise SystemExit("--mirror-path is required for --source mirror")
        counts = mirror.run(con, mirror_path, cfg["cricsheet"].get("gender", "female"))
    else:
        db.reset(con)
        counts = cricsheet.run(con, cfg)
    counts["competition_aliases_applied"] = db.apply_competition_aliases(con, cfg.get("competition_aliases", {}))
    names_csv = Path(cfg["paths"]["manual"]) / "names.csv"
    if names_csv.exists():
        nd = pd.read_csv(names_csv)
        db.upsert_display_names(con, [(str(r.player_id), str(r.display_name), "manual") for _, r in nd.iterrows()])
    db.build_player_match(con)
    counts["player_match_rows"] = con.execute("SELECT COUNT(*) FROM player_match").fetchone()[0]
    con.close()
    log.info("load complete: %s", counts)
    return counts


def cmd_run(cfg: dict, attention_mode: str, story_mode: str, languages: list[str] | None, top_kits: int | None = None) -> dict:
    derived = Path(cfg["paths"]["derived"])
    con = db.connect(cfg["paths"]["db"])  # one read-write connection for the whole run (DuckDB allows one config per file per process)
    window = resolve_window(con, cfg)
    log.info("window: %s (%s → %s, %s matches)", window.label, window.start, window.end, len(window.match_ids))
    players = window_players(con, window)

    # attention first: live mode also returns Wikidata labels, which become display names
    att, daily = att_mod.build_attention(con, cfg, window, players, mode=attention_mode)
    import re as _re
    def _display(label, title):
        # the English article title is kept current (e.g. a married name); the Wikidata label may lag
        if isinstance(title, str) and title.strip():
            return _re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
        return label if isinstance(label, str) and label.strip() else None
    labels = ({pid: _display(lab, title) for pid, lab, title in zip(att["player_id"], att.get("label", [None] * len(att)), att.get("article_en", [None] * len(att)))}
              if "label" in att.columns else {})
    players["name"] = [lab if isinstance(lab, str) and lab.strip() else nm
                       for lab, nm in ((labels.get(pid), nm) for pid, nm in zip(players["player_id"], players["name"]))]
    att["name"] = att["player_id"].map(dict(zip(players["player_id"], players["name"])))
    if labels and any(labels.values()):
        db.upsert_display_names(con, [(pid, lab, "wikidata") for pid, lab in labels.items() if isinstance(lab, str) and lab.strip()])

    engine = PatternEngine(con, cfg, window, players)
    cands = engine.run()
    cands_df = sig_mod.score_all(cands, cfg["significance"])
    from .intelligence.patterns import stakes_for
    psig = sig_mod.player_significance(cands_df, players, cfg["significance"], stakes_for(window.competition or "", None))

    gap_df, summary = gap_mod.fit_gap(players, psig, att, window.days)
    xi, notes = xi_mod.select_xi(gap_df, cfg, window.end, Path(cfg["paths"]["manual"]), window_start=window.start)
    con.close()

    # persist (kits and localisations are rebuilt every run; model-written ones are kept when their facts have not changed
    # and the model cannot answer this run, so a day without LLM quota never erases finished work)
    import shutil
    old_kits, old_locs = _load_previous(derived)
    for sub in ("kits", "localized"):
        shutil.rmtree(derived / sub, ignore_errors=True)
        (derived / sub).mkdir(parents=True, exist_ok=True)
    json.dump({"kind": window.kind, "label": window.label, "start": window.start.isoformat(), "end": window.end.isoformat(),
               "n_matches": len(window.match_ids), "competition": window.competition, "season": window.season},
              open(derived / "window.json", "w", encoding="utf-8"), indent=1)
    players.to_csv(derived / "players.csv", index=False)
    json.dump([c.as_dict() for c in cands], open(derived / "candidates.json", "w", encoding="utf-8"), indent=1, default=str)
    cands_df.to_csv(derived / "candidates_scored.csv", index=False)
    psig.to_csv(derived / "player_significance.csv", index=False)
    att.to_csv(derived / "attention.csv", index=False)
    daily.to_csv(derived / "attention_daily.csv", index=False)
    gap_df.to_csv(derived / "gap.csv", index=False)
    json.dump(summary, open(derived / "gap_summary.json", "w", encoding="utf-8"), indent=1)
    xi.to_csv(derived / "unseen_xi.csv", index=False)
    json.dump(notes, open(derived / "xi_notes.json", "w", encoding="utf-8"), indent=1)

    # kits for the XI (best candidate per player); priority athletes first so a small LLM budget goes to the demo
    from . import llm as llm_mod
    llm_cfg = cfg.get("llm", {}) or {}
    llm_mod.configure(max_calls=llm_cfg.get("max_calls_per_run", 18), cache_dir=Path(cfg["paths"]["cache"]) / "llm")
    cand_by_id = {c.candidate_id: c.as_dict() for c in cands}
    kits_built = 0
    langs = languages if languages is not None else cfg["localisation"]["languages"]
    priority = [n.lower() for n in (llm_cfg.get("priority_players") or [])]
    ordered = xi if top_kits is None else xi.head(top_kits)
    if ordered.empty:
        log.warning("the XI is empty (no eligible athletes: check the attention data and the constraints in config.yaml); no kits built")
        ordered = ordered.assign(_prio=[])
    else:
        ordered = ordered.assign(_prio=ordered["name"].str.lower().isin(priority)).sort_values(["_prio", "xi_slot"], ascending=[False, True])
    for _, p in ordered.iterrows():
        cid = p.best_candidate if isinstance(p.best_candidate, str) else None
        cand = cand_by_id.get(cid) if cid else None
        if cand is None:
            # player with no pattern candidate: build a TOP_PERFORMER-style bundle from aggregates
            cand = _fallback_candidate(engine, p)
        cand = _ensure_aggregates(engine, cand, p.player_id)
        kit = compiler.build_kit(cand, p.to_dict(), len(players), mode=story_mode)
        kit = _reuse_kit(kit, old_kits.get(p.player_id))
        json.dump(kit, open(derived / "kits" / f"{p.player_id}.json", "w", encoding="utf-8"), indent=1, default=str)
        kits_built += 1
        for lang in langs:
            loc = _reuse_loc(kit, old_kits.get(p.player_id), old_locs.get((p.player_id, lang)))
            if loc is None:
                loc = localize.localize_kit(kit, lang, cfg["localisation"]["language_names"].get(lang, lang), derived / "localized",
                                            tts=bool(cfg["localisation"].get("tts")))
            json.dump(loc, open(derived / "localized" / f"{p.player_id}_{lang}.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)

    meta = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "window": window.label,
            "attention_mode": attention_mode, "attention_source": (att["attention_source"].iloc[0] if not att.empty else None),
            "story_mode": story_mode, "llm_provider": __import__("seen.llm", fromlist=["provider"]).provider(),
            "n_players": int(len(players)), "n_candidates": int(len(cands)), "n_xi": int(len(xi)), "kits": kits_built,
            "languages": langs, "llm_usage": llm_mod.usage(), "gap_model": summary}
    json.dump(meta, open(derived / "run_meta.json", "w", encoding="utf-8"), indent=1)
    log.info("run complete: %s", {k: v for k, v in meta.items() if k != "gap_model"})
    return meta


def _load_previous(derived: Path) -> tuple[dict, dict]:
    """Kits and localisations from the last run, keyed by player (and language)."""
    kits, locs = {}, {}
    for f in (derived / "kits").glob("*.json"):
        try:
            k = json.loads(f.read_text(encoding="utf-8"))
            kits[k["player_id"]] = k
        except Exception:
            continue
    for f in (derived / "localized").glob("*_*.json"):
        try:
            pid, lang = f.stem.rsplit("_", 1)
            locs[(pid, lang)] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    return kits, locs


def _fact_key(kit: dict) -> list:
    return [(f.get("id"), f.get("type"), str(f.get("value"))) for f in kit.get("facts", [])]


LLM_KEYS = ("video_script", "social_posts", "article")   # the formats the model writes; the rest come from templates


def _reuse_kit(kit: dict, old: dict | None) -> dict:
    """If this run produced a template kit but the previous run had a model-written one for the same facts, keep the
    model-written prose for the model's formats (re-checked against the current bundle); template formats stay fresh."""
    if kit.get("mode") != "template" or not old or old.get("mode") != "llm+template" or _fact_key(old) != _fact_key(kit):
        return kit
    trial = dict(kit)
    trial["formats"] = dict(kit["formats"])
    trial["formats"].update({k: old["formats"][k] for k in LLM_KEYS if k in old.get("formats", {})})
    trial["checks"] = compiler.run_checks(trial)
    if all(v["passed"] for v in trial["checks"].values()):
        trial["mode"] = "llm+template"
        trial["reused_from"] = old.get("generated_at")
        log.info("kept the model-written kit for %s from %s (facts unchanged; no model answer this run)", kit["name"], old.get("generated_at"))
        return trial
    return kit


def _translated(loc: dict | None) -> bool:
    return bool(loc and loc.get("checks") and str(loc.get("status", "")).startswith("translated and"))


def _reuse_loc(kit: dict, old_kit: dict | None, old_loc: dict | None) -> dict | None:
    """A finished translation of the same model-written text is kept (no model call) once its numbers re-check
    against the current fact bundle; None means translate afresh."""
    from .stories import claim_check
    same_text = bool(old_kit) and all(old_kit.get("formats", {}).get(k) == kit["formats"].get(k) for k in LLM_KEYS)
    if not (_translated(old_loc) and same_text):
        return None
    allowed = [kit["name"], kit["team"]]
    for k, text in old_loc.get("formats", {}).items():
        if not claim_check.check(text, kit["facts"], allowed).passed:
            return None
    log.info("kept the %s translation for %s (text unchanged, claims re-checked)", old_loc.get("language"), kit["name"])
    return old_loc


def _ensure_aggregates(engine: PatternEngine, cand: dict, player_id: str) -> dict:
    """Every kit needs the window aggregates (runs, wickets, rank) even if the pattern was match-level."""
    if any(f["type"] == "impact_rank" for f in cand["facts"]):
        return cand
    row = engine.players[engine.players.player_id == player_id]
    if row.empty:
        return cand
    cand = dict(cand)
    cand["facts"] = list(cand["facts"]) + [f.as_dict() for f in engine.aggregate_facts(row.iloc[0])]
    return cand


def _fallback_candidate(engine: PatternEngine, p) -> dict:
    row = engine.players[engine.players.player_id == p.player_id].iloc[0]
    from .intelligence.patterns import Candidate
    c = Candidate(candidate_id=f"X-{p.player_id}", player_id=p.player_id, player_name=row["name"], team=row.team, pattern="TOP_PERFORMER",
                  headline=f"{row['name']} ranked #{int(row.impact_rank)} of {len(engine.players)} players by impact in {engine.window.label}",
                  rarity_count=int(row.impact_rank) - 1, stakes=0.9, magnitude=float(min(engine.zmap.get(p.player_id, 0.0) / 3.0, 1.0)))
    c.facts = engine.aggregate_facts(row)
    return c.as_dict()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="SEEN pipeline")
    ap.add_argument("command", choices=["load", "run", "all"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--source", choices=["cricsheet", "mirror"], default="cricsheet")
    ap.add_argument("--mirror-path", default=None)
    ap.add_argument("--attention", choices=["live", "fixture"], default="live")
    ap.add_argument("--story-mode", choices=["auto", "template", "llm"], default="auto")
    ap.add_argument("--languages", default=None, help="comma-separated, e.g. hi,ur (default from config)")
    ap.add_argument("--top-kits", type=int, default=None, help="build kits for only the first N of the XI")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    langs = args.languages.split(",") if args.languages else None
    if args.command in ("load", "all"):
        print(json.dumps(cmd_load(cfg, args.source, args.mirror_path), indent=1, default=str))
    if args.command in ("run", "all"):
        print(json.dumps(cmd_run(cfg, args.attention, args.story_mode, langs, args.top_kits), indent=1, default=str))


if __name__ == "__main__":
    main()
