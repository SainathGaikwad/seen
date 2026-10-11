"""What a sponsor can buy, what it costs, and how the money is split. All of it is deterministic policy; the agent
chooses within it and cannot change it."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULTS = {
    "currency": "USD",
    "tip_amount": 2.00,
    "base_price": 60.00,        # one athlete, one language, one week
    "language_addon": 25.00,    # each further language
    "gap_multiplier": 0.35,     # price rises with the visibility gap (z-score, clamped 0..3): the more under-seen, the dearer
    "max_athletes": 4,
    "max_weeks": 4,
    "invoice_threshold": 500.00,
    "split": {"athlete_fund": 0.60, "creator": 0.30, "seen": 0.10},
    "tip_split": {"athlete_fund": 0.70, "creator": 0.20, "seen": 0.10},
}


def policy(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg.get("money") or {}).items() if k in DEFAULTS and k not in ("split", "tip_split")})
    for key in ("split", "tip_split"):
        out[key] = dict(DEFAULTS[key], **((cfg.get("money") or {}).get(key) or {}))
    return out


def _languages_available(derived: Path, player_id: str, langs: list[str]) -> list[str]:
    out = ["en"]
    for lang in langs:
        p = Path(derived) / "localized" / f"{player_id}_{lang}.json"
        if p.exists():
            try:
                loc = json.loads(p.read_text(encoding="utf-8"))
                checks = loc.get("checks") or {}
                if checks and all(v.get("passed") for v in checks.values()):
                    out.append(lang)
            except Exception:
                pass
    return out


def unit_price(gap_z: float, pol: dict) -> float:
    z = max(0.0, min(3.0, float(gap_z) if gap_z == gap_z else 0.0))
    return round(pol["base_price"] * (1.0 + pol["gap_multiplier"] * z), 2)


def catalogue(xi: pd.DataFrame, derived: Path, cfg: dict) -> list[dict]:
    """One line per Unseen XI athlete: who she is, why she is under-seen, which languages her verified kit exists in,
    and the week price of presenting her story in one language."""
    pol = policy(cfg)
    langs = list((cfg.get("localisation") or {}).get("languages") or [])
    names = (cfg.get("localisation") or {}).get("language_names") or {}
    rows = []
    for _, r in xi.iterrows():
        kit_path = Path(derived) / "kits" / f"{r.player_id}.json"
        headline = ""
        verified = False
        if kit_path.exists():
            try:
                kit = json.loads(kit_path.read_text(encoding="utf-8"))
                headline = kit.get("headline", "")
                verified = all(v.get("passed") for v in (kit.get("checks") or {}).values())
            except Exception:
                pass
        if not verified:
            continue   # only claim-checked stories are for sale
        avail = _languages_available(derived, r.player_id, langs)
        rows.append({
            "player_id": r.player_id, "name": r["name"], "team": r.team, "role": r.role,
            "impact_rank": int(r.impact_rank), "attention_rank": int(r.attention_rank),
            "gap_z": round(float(r.gap_z), 2), "gap_confidence": r.get("gap_confidence", ""),
            "headline": headline, "languages": avail, "language_names": {l: names.get(l, l) for l in avail},
            "week_price_usd": unit_price(r.gap_z, pol), "language_addon_usd": pol["language_addon"],
        })
    return rows


class PackageError(ValueError):
    pass


def price_package(items: list[dict], cat: list[dict], cfg: dict, budget: float | None = None) -> dict:
    """items: [{player_id, languages: [...], weeks: n}] → priced lines, total and the split. Raises PackageError on
    anything outside policy (unknown athlete, language without a verified kit, too many athletes/weeks, over budget)."""
    pol = policy(cfg)
    by_id = {c["player_id"]: c for c in cat}
    by_name = {c["name"].lower(): c for c in cat}
    if not items:
        raise PackageError("the package is empty")
    if len(items) > pol["max_athletes"]:
        raise PackageError(f"at most {pol['max_athletes']} athletes per package")
    lines, seen = [], set()
    for it in items:
        key = str(it.get("player_id") or it.get("name") or "").strip()
        c = by_id.get(key) or by_name.get(key.lower())
        if not c:
            raise PackageError(f"'{key}' is not in the Unseen XI catalogue")
        if c["player_id"] in seen:
            raise PackageError(f"{c['name']} appears twice")
        seen.add(c["player_id"])
        langs = [str(l).lower() for l in (it.get("languages") or ["en"])]
        langs = list(dict.fromkeys(langs))
        bad = [l for l in langs if l not in c["languages"]]
        if bad:
            raise PackageError(f"{c['name']} has no verified story in {', '.join(bad)} (available: {', '.join(c['languages'])})")
        weeks = int(it.get("weeks") or 1)
        if not 1 <= weeks <= pol["max_weeks"]:
            raise PackageError(f"weeks must be 1..{pol['max_weeks']}")
        amount = round((c["week_price_usd"] + pol["language_addon"] * (len(langs) - 1)) * weeks, 2)
        lines.append({"player_id": c["player_id"], "name": c["name"], "team": c["team"], "languages": langs, "weeks": weeks,
                      "unit_usd": c["week_price_usd"], "amount_usd": amount,
                      "item_name": f"Presented by: {c['name']} ({c['team']}) story kit · {'+'.join(l.upper() for l in langs)} · {weeks} wk",
                      "description": c["headline"][:120]})
    total = round(sum(l["amount_usd"] for l in lines), 2)
    if budget is not None and total > float(budget) + 1e-9:
        raise PackageError(f"total ${total:,.2f} exceeds the budget ${float(budget):,.2f}")
    # the split is computed per line (that is how the ledger and the payouts are made) and summed, so the figure the
    # sponsor is shown is the figure that is paid out, to the cent
    for l in lines:
        l["split"] = split_amount(l["amount_usd"], pol["split"])
    split = {k: round(sum(l["split"][k] for l in lines), 2) for k in ("athlete_fund", "creator", "seen")}
    return {"lines": lines, "total_usd": total, "split": split, "policy": {"split": pol["split"]}}


def split_amount(amount: float, split: dict) -> dict:
    a = round(float(amount) * split["athlete_fund"], 2)
    c = round(float(amount) * split["creator"], 2)
    s = round(float(amount) - a - c, 2)
    return {"athlete_fund": a, "creator": c, "seen": s}


def tip_lines(athlete: dict, cfg: dict, language: str = "en") -> dict:
    pol = policy(cfg)
    amount = round(float(pol["tip_amount"]), 2)
    return {"lines": [{"player_id": athlete["player_id"], "name": athlete["name"], "team": athlete.get("team", ""), "languages": [language], "weeks": 0,
                       "unit_usd": amount, "amount_usd": amount, "item_name": f"Tip: {athlete['name']}'s story ({language.upper()})",
                       "description": "A fan's thank-you for a verified story; 70% to the athlete fund, 20% to the creator."}],
            "total_usd": amount, "split": split_amount(amount, pol["tip_split"]), "policy": {"split": pol["tip_split"]}}
