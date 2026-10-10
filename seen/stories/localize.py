"""Localisation of an approved kit: LLM translation with a locked cricket glossary, claim re-check, optional TTS.

Without an LLM key the kit is returned untranslated with a clear status, so the UI never
pretends a translation exists. Numbers and [F#] citations must survive translation unchanged.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import llm
from . import claim_check

log = logging.getLogger(__name__)

GLOSSARY = {
    "hi": {"wicket": "विकेट", "run": "रन", "over": "ओवर", "strike rate": "स्ट्राइक रेट", "economy": "इकॉनमी", "all-rounder": "ऑलराउंडर", "half-century": "अर्धशतक"},
    "ur": {"wicket": "وکٹ", "run": "رن", "over": "اوور", "strike rate": "اسٹرائیک ریٹ", "economy": "اکانومی", "all-rounder": "آل راؤنڈر", "half-century": "نصف سنچری"},
    "ta": {"wicket": "விக்கெட்", "run": "ரன்", "over": "ஓவர்", "strike rate": "ஸ்டிரைக் ரேட்", "economy": "எக்கானமி"},
    "bn": {"wicket": "উইকেট", "run": "রান", "over": "ওভার", "strike rate": "স্ট্রাইক রেট", "economy": "ইকোনমি"},
}

SYSTEM = """You translate cricket stories for SEEN. Translate the given texts into the target language for fans of that language.
Rules: keep every number exactly as written and keep every [F#] citation immediately after its number; keep player and team names
in Latin script followed by the local script in brackets on first mention; use the glossary terms exactly; do not add facts.
Return ONLY a JSON object with the same keys as the input texts."""


def localize_kit(kit: dict, lang: str, lang_name: str, out_dir: Path, tts: bool = False) -> dict:
    keys = ["video_script", "social_posts", "article", "creator_brief"]
    result = {"language": lang, "language_name": lang_name, "status": "not translated", "formats": {}, "checks": {}, "audio": None}
    if not llm.available():
        result["status"] = "needs LLM key (LLM_PROVIDER in .env) — English kit shown"
        result["formats"] = {k: kit["formats"][k] for k in keys}
        return result
    payload = {"target_language": lang_name, "glossary": GLOSSARY.get(lang, {}), "texts": {k: kit["formats"][k] for k in keys}}
    try:
        raw = llm.complete(SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=8000)
        data = llm.parse_json(raw) or {}
    except Exception as exc:
        result["status"] = f"translation failed: {exc}"
        result["formats"] = {k: kit["formats"][k] for k in keys}
        return result
    allowed = [kit["name"], kit["team"]]
    ok = True
    for k in keys:
        text = data.get(k)
        if not isinstance(text, str) or not text.strip():
            result["formats"][k] = kit["formats"][k]
            result["checks"][k] = {"passed": False, "summary": "missing in translation; English kept"}
            ok = False
            continue
        res = claim_check.check(text, kit["facts"], allowed)
        result["formats"][k] = text if res.passed else kit["formats"][k]
        result["checks"][k] = {"passed": res.passed, "summary": res.summary(), "claims": res.claims, "banned": res.banned}
        ok = ok and res.passed
    result["status"] = "translated and claim-checked" if ok else "translated; one or more formats failed the claim check and were kept in English"
    if tts:
        result["audio"] = _tts(result["formats"]["video_script"], lang, out_dir / f"{kit['player_id']}_{lang}.mp3")
    return result


def _tts(text: str, lang: str, path: Path) -> str | None:
    try:
        from gtts import gTTS  # type: ignore
    except ImportError:
        log.info("gTTS not installed; skipping audio")
        return None
    try:
        clean = claim_check.CITATION.sub("", text)
        path.parent.mkdir(parents=True, exist_ok=True)
        gTTS(text=clean, lang=lang).save(str(path))
        return str(path)
    except Exception as exc:
        log.warning("TTS failed: %s", exc)
        return None


def rank_languages(player: dict, cfg: dict) -> list[dict]:
    """Rank candidate languages for a player by (documented) market opportunity heuristics."""
    team = player.get("team", "")
    base = {"hi": 0.6, "ur": 0.3, "ta": 0.35, "bn": 0.35, "si": 0.2, "mr": 0.25, "te": 0.25, "ne": 0.15, "th": 0.05, "en": 0.5}
    home = {"India": {"hi": 0.4, "ta": 0.2, "bn": 0.15, "mr": 0.2, "te": 0.2}, "Pakistan": {"ur": 0.6}, "Bangladesh": {"bn": 0.6},
            "Sri Lanka": {"si": 0.6, "ta": 0.3}, "Nepal": {"ne": 0.7, "hi": 0.2}, "Thailand": {"th": 0.7}}
    for k, v in home.get(team, {}).items():
        base[k] = base.get(k, 0) + v
    ed_raw = player.get("editions")
    editions = set(str(ed_raw).split(",")) if isinstance(ed_raw, str) and ed_raw else set()
    out = []
    for code, score in base.items():
        reason = []
        if code in home.get(team, {}):
            reason.append("home-market language")
        if code != "en" and code not in editions:
            reason.append("no Wikipedia article in this language yet")
            score += 0.1
        out.append({"language": code, "name": cfg["localisation"]["language_names"].get(code, code), "score": round(score, 2), "reason": ", ".join(reason) or "large cricket audience"})
    out.sort(key=lambda r: -r["score"])   # sort on the final score (after the no-article bonus)
    return out
