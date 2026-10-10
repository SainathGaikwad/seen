"""Fact-locked story compiler: one verified story opportunity → eight formats.

Two modes:
- TEMPLATE (always available): deterministic Jinja2 templates filled only with facts.
- LLM (when a key is configured): the model writes connective prose from the same fact bundle;
  every number must carry a fact citation [F#]; the claim checker blocks anything it cannot match
  and the format falls back to the template.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone

from jinja2 import Environment, BaseLoader

from .. import llm
from . import claim_check

log = logging.getLogger(__name__)

FORMATS = ["video_script", "social_posts", "article", "infographic", "creator_brief", "commentator_note", "quiz", "sponsor_hook"]

env = Environment(loader=BaseLoader(), autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _f(facts: list[dict], ftype: str, default=None):
    for f in facts:
        if f["type"] == ftype:
            return f
    return default


def _all(facts: list[dict], ftype: str) -> list[dict]:
    return [f for f in facts if f["type"] == ftype]


def cite(f: dict | None) -> str:
    return f"[{f['id']}]" if f else ""


T_VIDEO = env.from_string(
    """[00:00-00:05] {{ name }}. {{ team }}. {{ competition }}.
[00:05-00:20] {{ headline }} {{ c_head }}
[00:20-00:40] {{ match_lines | join(' ') }}
[00:40-00:55] Across the tournament: {{ agg_line }}
[00:55-01:00] Remember the name: {{ name }}. Follow her — the next match is in the app."""
)

GUIDANCE_MARKER = "\n--- guidance (not claims) ---\n"

T_ARTICLE = env.from_string(
    """{{ headline }} {{ c_head }}

{{ name }} of {{ team }} finished {{ competition }} ranked {{ rank }} of {{ n_players }} players by impact {{ c_rank }}. {{ agg_line }}

{% for m in match_lines %}{{ m }} {% endfor %}

{% if rarity_line %}{{ rarity_line }}{% endif %}

Source: Cricsheet ball-by-ball data (ODC-BY). Every figure above carries a fact reference."""
)


def build_kit(candidate: dict, player: dict, n_players: int, mode: str = "auto") -> dict:
    """candidate: dict from patterns (with facts); player: row from the gap table (dict)."""
    facts = list(candidate["facts"])
    name, team = candidate["player_name"], candidate["team"]
    # attention facts from the gap table, so the sponsor hook and briefs can cite them
    next_id = max([int(f["id"][1:]) for f in facts if str(f.get("id", "")).startswith("F")] + [0]) + 1
    if player.get("views_window_total") is not None:
        facts.append({"id": f"F{next_id}", "type": "attention_views",
                      "text": f"{name}'s Wikipedia article views during the window: {int(player['views_window_total'])}",
                      "value": int(player["views_window_total"]), "source": str(player.get("attention_source", "attention index"))})
        next_id += 1
    if player.get("expected_views"):
        # a model estimate, cited to three significant figures: the OLS fit drifts by a few views between runs as
        # pageview data is backfilled, and an exact figure would change every prompt (and miss the LLM cache) for nothing
        exp_val = round_sig(player["expected_views"])
        facts.append({"id": f"F{next_id}", "type": "expected_views",
                      "text": f"expected views for this level of performance (SEEN gap model estimate, rounded): {exp_val}",
                      "value": exp_val, "source": "SEEN gap model (OLS on significance, market tier, prior fame)"})
        next_id += 1
    if player.get("attention_rank"):
        facts.append({"id": f"F{next_id}", "type": "attention_rank", "text": f"attention rank in the window: {int(player['attention_rank'])}",
                      "value": int(player["attention_rank"]), "source": str(player.get("attention_source", "attention index"))})
    comp = _f(facts, "competition", {"value": "the tournament"})["value"]
    head = candidate["headline"]
    # the headline is a pattern output: cite the fact that supports it (first history fact or first match fact)
    head_fact = _f(facts, "prior_occurrences_team") or _f(facts, "prior_occurrences") or _f(facts, "impact_rank") or (facts[0] if facts else None)
    c_head = cite(head_fact)

    match_lines = []
    seen_match: set = set()   # the same match can arrive from a pattern and from the "best match" aggregates: cite it once
    for ftype in ("runs_in_match", "wickets_in_match"):
        n = 0
        for f in _all(facts, ftype):
            key = (ftype, str(f.get("source")), f.get("value"))
            if key in seen_match or n >= 2:
                continue
            seen_match.add(key)
            n += 1
            match_lines.append(f"{f['text']} {cite(f)}.")
    runs, balls, wk, bb = _f(facts, "window_runs"), _f(facts, "window_balls_faced"), _f(facts, "window_wickets"), _f(facts, "window_balls_bowled")
    sr, econ, rank = _f(facts, "strike_rate"), _f(facts, "economy"), _f(facts, "impact_rank")
    agg_bits = []
    if runs and runs["value"]:
        agg_bits.append(f"{runs['value']} runs off {balls['value']} balls {cite(runs)}" + (f" at a strike rate of {sr['value']} {cite(sr)}" if sr else ""))
    if wk and wk["value"]:
        agg_bits.append(f"{wk['value']} wickets from {bb['value']} balls {cite(wk)}" + (f" at an economy of {econ['value']} {cite(econ)}" if econ else ""))
    agg_line = "; ".join(agg_bits) + "." if agg_bits else ""
    rarity_f = _f(facts, "prior_occurrences_team") or _f(facts, "prior_occurrences")
    rarity_line = f"{rarity_f['text']} {cite(rarity_f)}." if rarity_f else ""

    ctx = dict(name=name, team=team, competition=comp, headline=head, c_head=c_head, match_lines=match_lines,
               agg_line=agg_line, rank=rank["value"] if rank else "", c_rank=cite(rank), n_players=n_players, rarity_line=rarity_line)

    kit = {
        "player_id": candidate["player_id"], "name": name, "team": team, "candidate_id": candidate["candidate_id"],
        "pattern": candidate["pattern"], "headline": head, "facts": facts, "language": "en",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "template", "formats": {}, "checks": {},
        "gap_summary": {k: player.get(k) for k in ("impact_rank", "attention_rank", "gap_rank", "views_window_total", "expected_views", "no_article", "gap_confidence")},
    }
    kit["formats"]["video_script"] = T_VIDEO.render(**ctx)
    kit["formats"]["article"] = T_ARTICLE.render(**ctx)
    kit["formats"]["social_posts"] = _social(ctx, facts)
    kit["formats"]["infographic"] = _infographic(ctx, facts)
    kit["formats"]["creator_brief"] = _creator_brief(ctx, facts, candidate)
    kit["formats"]["commentator_note"] = _commentator_note(ctx, facts)
    kit["formats"]["quiz"] = _quiz(ctx, facts)
    kit["formats"]["sponsor_hook"] = _sponsor_hook(ctx, facts, player)

    if mode in ("auto", "llm") and llm.available():
        kit = _llm_enrich(kit, ctx)
    kit["checks"] = run_checks(kit)
    return kit


def _social(ctx, facts) -> str:
    rank = _f(facts, "impact_rank")
    rank_txt = f" Ranked #{rank['value']} of {ctx['n_players']} by impact in {ctx['competition']} {cite(rank)}." if rank else ""
    posts = [
        f"{ctx['headline']} {ctx['c_head']} #{ctx['team'].replace(' ', '')} #WomensCricket",
        f"{ctx['name']} ({ctx['team']}) — {ctx['agg_line']}{rank_txt}",
        f"Know her name: {ctx['name']}. {ctx['match_lines'][0] if ctx['match_lines'] else ctx['agg_line']} Follow for the next match.",
    ]
    return "\n\n".join(f"Post {i+1}: {p}" for i, p in enumerate(posts))


def _infographic(ctx, facts) -> str:
    stats = []
    for ftype, label in (("window_runs", "Runs"), ("window_wickets", "Wickets"), ("strike_rate", "Strike rate"), ("economy", "Economy"), ("impact_rank", "Impact rank")):
        f = _f(facts, ftype)
        if f and f["value"] not in (None, 0, ""):
            stats.append({"label": label, "value": f["value"], "fact": f["id"]})
    spec = {"title": ctx["name"], "subtitle": f"{ctx['team']} · {ctx['competition']}", "headline": ctx["headline"],
            "stats": stats, "footer": "Source: Cricsheet ball-by-ball data (ODC-BY) · SEEN Unseen XI"}
    return json.dumps(spec, indent=1)


def _creator_brief(ctx, facts, candidate) -> str:
    angles = [ctx["headline"]]
    if ctx["match_lines"]:
        angles.append("The match that made it: " + ctx["match_lines"][0])
    if ctx["rarity_line"]:
        angles.append("Why it is rare: " + ctx["rarity_line"])
    lines = [f"CREATOR BRIEF — {ctx['name']} ({ctx['team']})", "",
             "Angles:"] + [f"  {i+1}. {a}" for i, a in enumerate(angles)] + [
             "", "Verified facts (use only these numbers, keep the [F#] tags in your notes):"]
    lines += [f"  [{f['id']}] {f['text']} (source: {f['source']})" for f in facts if f["type"] not in ("team", "competition")][:12]
    guidance = ["Do: name her, name the country, say the number with its context, link the official highlight.",
                "Don't: speculate about fitness, selection or anything personal; nothing about odds or bookmakers.",
                "Assets: infographic spec (JSON), sixty-second script, quiz. Clip slot: ICC-cleared highlight required (not included).",
                f"Hashtags: #{ctx['team'].replace(' ', '')} #WomensCricket #{ctx['competition'].replace(' ', '').replace(chr(39), '')}",
                "Sponsor tag: [available slot — presented by ...]", "Attribution: submit your post link in the SEEN creator page."]
    return "\n".join(lines) + GUIDANCE_MARKER + "\n".join(guidance)


def _commentator_note(ctx, facts) -> str:
    lines = [f"COMMENTATOR NOTE — {ctx['name']} ({ctx['team']})", f"Pronunciation: {ctx['name']} (confirm with team media manager)", ""]
    for f in facts:
        if f["type"] in ("impact_rank", "window_runs", "window_wickets", "strike_rate", "economy", "prior_occurrences_team", "prior_occurrences", "runs_in_match", "wickets_in_match", "streak_length", "career_total", "days_since_previous_match"):
            lines.append(f"- {f['text']} [{f['id']}]")
    return "\n".join(lines) + GUIDANCE_MARKER + "Milestone watch: check career totals before the next match (graph coverage: the formats loaded into SEEN)."


def _quiz(ctx, facts) -> str:
    rng = random.Random(ctx["name"])
    qs = []
    for ftype, q in (("window_runs", f"How many runs did {ctx['name']} score in {ctx['competition']}?"),
                     ("window_wickets", f"How many wickets did {ctx['name']} take in {ctx['competition']}?"),
                     ("impact_rank", f"Where did {ctx['name']} rank by impact among all players in {ctx['competition']}?")):
        f = _f(facts, ftype)
        if not f or f["value"] in (None, 0):
            continue
        v = int(f["value"])
        opts = sorted({v, max(0, v - rng.randint(1, 9)), v + rng.randint(1, 9), max(0, v + rng.randint(10, 25))})
        qs.append({"question": q, "options": opts, "answer": v, "fact": f["id"]})
    return json.dumps(qs, indent=1)


def round_sig(v, sig: int = 3) -> int:
    """Round a positive number to `sig` significant figures (24,548 -> 24,500)."""
    v = float(v)
    if v <= 0:
        return int(v)
    return int(float(f"{v:.{sig}g}"))


def _sponsor_hook(ctx, facts, player) -> str:
    vf, ef = _f(facts, "attention_views"), _f(facts, "expected_views")   # the cited facts, so the numbers always match the bundle
    gap_txt = ""
    if vf is not None and ef:
        gap_txt = (f" Attention gap: {int(vf['value']):,} article views in the window {cite(vf)} against roughly {int(ef['value']):,} "
                   f"expected for this level of performance {cite(ef)}.")
    return (f"{ctx['name']} ({ctx['team']}): {ctx['headline']} {ctx['c_head']}{gap_txt} "
            f"An early-stage partnership opportunity with measurable upside; activation ideas: 'Unseen XI presented by', athlete story series, local-language content.")


SYSTEM_PROMPT = """You are SEEN's story compiler for women's cricket. You write from a FACT BUNDLE only.
Rules: every number you write must come from a fact and be followed by its citation like [F3]; never invent statistics,
ages, injuries, personal details or quotes; never speculate about health, private life or betting; keep cricket terms exact.
Return ONLY a JSON object with keys: video_script, social_posts, article. Keep the given structure and citations."""


def _llm_enrich(kit: dict, ctx: dict) -> dict:
    user = json.dumps({"facts": kit["facts"], "headline": kit["headline"], "player": kit["name"], "team": kit["team"],
                       "competition": ctx["competition"], "template_versions": {k: kit["formats"][k] for k in ("video_script", "social_posts", "article")},
                       "instruction": "Rewrite the three template versions as natural, vivid English for a 60-second vertical video script, three social posts and a 180-word article. Keep every [F#] citation next to its number."}, ensure_ascii=False)
    try:
        raw = llm.complete(SYSTEM_PROMPT, user, max_tokens=6000)
        data = llm.parse_json(raw) or {}
    except Exception as exc:
        log.warning("LLM enrich failed, keeping template: %s", exc)
        return kit
    allowed = [kit["name"], kit["team"]]
    for key in ("video_script", "social_posts", "article"):
        text = data.get(key)
        if not isinstance(text, str) or not text.strip():
            continue
        res = claim_check.check(text, kit["facts"], allowed)
        if res.passed:
            kit["formats"][key] = text
            kit["mode"] = "llm+template"
        else:
            kit.setdefault("rejected", {})[key] = {"text": text, "reason": res.summary(), "claims": res.claims, "banned": res.banned}
            log.info("LLM %s rejected by claim checker: %s", key, res.summary())
    return kit


REWRITE_FORMATS = ("video_script", "social_posts", "article")
REWRITE_BRIEF = {"video_script": "a 60-second vertical video script with timestamps",
                 "social_posts": "three social posts (one line each, no hashtags spam)",
                 "article": "a 180-word article"}


def rewrite_format(kit: dict, fmt: str, angle: str = "") -> dict:
    """Live, single-format rewrite from the same fact bundle (the app's 'Rewrite with <model>' button).

    Returns {"accepted": bool, "text": str, "check": dict, "error": str | None}. The kit is updated only when the
    claim checker passes; a rejected draft is stored under kit["rejected"][fmt] so the UI can show why.
    """
    if fmt not in REWRITE_FORMATS:
        return {"accepted": False, "text": "", "check": {}, "error": f"{fmt} is template-only"}
    comp = _f(kit["facts"], "competition", {"value": "the tournament"})["value"]
    instruction = (f"Write a NEW version of the template text as natural, vivid English for {REWRITE_BRIEF[fmt]}. "
                   "The wording must differ from the template version (do not copy it back); keep every fact and every [F#] citation next to its number.")
    if angle.strip():
        instruction += f" Angle requested by the editor: {angle.strip()[:200]}. Facts and citations stay exactly as given."
    user = json.dumps({"facts": kit["facts"], "headline": kit["headline"], "player": kit["name"], "team": kit["team"], "competition": comp,
                       "template_version": kit["formats"][fmt].split(GUIDANCE_MARKER)[0], "instruction": instruction,
                       "output": f"Return ONLY a JSON object with the single key {fmt}."}, ensure_ascii=False)
    system = SYSTEM_PROMPT.replace("Return ONLY a JSON object with keys: video_script, social_posts, article.",
                                   "Return ONLY a JSON object with the single key named in the request.")
    try:
        raw = llm.complete(system, user, max_tokens=3000)
    except Exception as exc:
        return {"accepted": False, "text": "", "check": {}, "error": str(exc)[:300]}
    data = llm.parse_json(raw) or {}
    text = data.get(fmt) if isinstance(data.get(fmt), str) else None
    if not text or not text.strip():
        return {"accepted": False, "text": raw[:500], "check": {}, "error": "the model did not return the requested JSON"}
    current = kit["formats"][fmt].split(GUIDANCE_MARKER)[0]
    if " ".join(text.split()) == " ".join(current.split()):
        return {"accepted": False, "text": text, "check": {}, "error": "the model returned the current text unchanged; try a different angle"}
    res = claim_check.check(text, kit["facts"], [kit["name"], kit["team"]])
    check = {"passed": res.passed, "summary": res.summary(), "claims": res.claims, "banned": res.banned, "unknown_names": res.unmatched_entities}
    if res.passed:
        kit.setdefault("generated", {}).setdefault(fmt, kit["formats"][fmt])
        kit["formats"][fmt] = text
        kit["mode"] = "llm+template"
        kit["text_rev"] = int(kit.get("text_rev", 0)) + 1   # the editor's text box re-reads the text when this changes
        kit["checks"] = run_checks(kit)
        kit.setdefault("rewrites", []).append({"format": fmt, "angle": angle.strip(), "model": llm.model_label(),
                                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    else:
        kit.setdefault("rejected", {})[fmt] = {"text": text, "reason": res.summary(), "claims": res.claims, "banned": res.banned}
    return {"accepted": res.passed, "text": text, "check": check, "error": None}


def run_checks(kit: dict) -> dict:
    allowed = [kit["name"], kit["team"]] + [f["value"] for f in kit["facts"] if isinstance(f.get("value"), str)]
    out = {}
    for key in FORMATS:
        text = kit["formats"].get(key, "")
        text = text.split(GUIDANCE_MARKER)[0]  # boilerplate guidance is not a claim
        if key in ("infographic", "quiz"):
            # JSON formats: check the numeric values inside
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            nums = []
            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k in ("fact",):
                            continue
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
                elif isinstance(o, (int, float)) and not isinstance(o, bool):
                    nums.append(str(o))
            walk(data)
            text = " ".join(nums) if key == "infographic" else " ".join(str(q.get("answer", "")) for q in (data if isinstance(data, list) else []))
        res = claim_check.check(text, kit["facts"], allowed)
        out[key] = {"passed": res.passed, "summary": res.summary(), "claims": res.claims, "banned": res.banned,
                    "unknown_names": res.unmatched_entities}
    return out
