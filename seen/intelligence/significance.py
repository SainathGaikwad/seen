"""Significance score with an explainable breakdown.

S = w_rarity * rarity + w_stakes * stakes + w_magnitude * magnitude + w_arc * arc
rarity    = 1 / (1 + prior occurrences)          (a genuine first scores 1.0)
stakes    = competition and stage weight (0-1)
magnitude = z-score of window impact / 3, clipped to [-0.5, 1] (a below-average performance lowers the score, gradually)
arc       = 0.5 per career-arc flag, capped at 1 (first for country, debut, comeback, streak, team first, associate)
"""
from __future__ import annotations

import math

import pandas as pd

from .patterns import Candidate

MAGNITUDE_FLOOR = -0.5   # z/3 is clipped to [MAGNITUDE_FLOOR, 1]: below-average impact grades the score down instead of stacking at one value


def magnitude_from_z(z):
    """Impact z-score -> magnitude term. Works on floats and pandas Series."""
    try:
        return (z / 3.0).clip(lower=MAGNITUDE_FLOOR, upper=1.0)
    except AttributeError:
        return max(MAGNITUDE_FLOOR, min(1.0, z / 3.0))


def score_candidate(c: Candidate, weights: dict) -> dict:
    rarity = 1.0 / (1.0 + c.rarity_count)
    arc = min(1.0, 0.5 * len(set(c.arc_flags)))
    parts = {
        "rarity": round(weights["rarity"] * rarity, 4),
        "stakes": round(weights["stakes"] * c.stakes, 4),
        "magnitude": round(weights["magnitude"] * c.magnitude, 4),
        "arc": round(weights["arc"] * arc, 4),
    }
    total = round(sum(parts.values()), 4)
    return {"significance": total, "breakdown": parts,
            "inputs": {"rarity_count": c.rarity_count, "stakes": c.stakes, "magnitude": round(c.magnitude, 3), "arc_flags": c.arc_flags}}


def score_all(candidates: list[Candidate], weights: dict) -> pd.DataFrame:
    rows = []
    for c in candidates:
        s = score_candidate(c, weights)
        rows.append({
            "candidate_id": c.candidate_id, "player_id": c.player_id, "player_name": c.player_name, "team": c.team,
            "pattern": c.pattern, "headline": c.headline, "match_id": c.match_id,
            "significance": s["significance"], **{f"part_{k}": v for k, v in s["breakdown"].items()},
            "rarity_count": c.rarity_count, "stakes": c.stakes, "magnitude": round(c.magnitude, 3),
            "arc_flags": ",".join(c.arc_flags), "n_facts": len(c.facts),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("significance", ascending=False).reset_index(drop=True)


def player_significance(cands: pd.DataFrame, players: pd.DataFrame | None = None, weights: dict | None = None,
                        stakes: float = 0.9) -> pd.DataFrame:
    """Per player: the best candidate (plus a small bonus for several stories), floored by an impact-only score
    so that athletes with no fired pattern still carry the significance their performance implies."""
    cols = ["player_id", "significance", "best_candidate", "best_pattern", "best_headline", "n_candidates"]
    if cands.empty:
        out = pd.DataFrame(columns=cols)
    else:
        g = cands.groupby("player_id")
        out = g.agg(best=("significance", "max"), n_candidates=("candidate_id", "count")).reset_index()
        best_ids = cands.loc[g["significance"].idxmax(), ["player_id", "candidate_id", "pattern", "headline"]]
        out = out.merge(best_ids, on="player_id")
        out["significance"] = (out["best"] + 0.05 * out["n_candidates"].apply(lambda n: math.log1p(n))).round(4)
        out = out.rename(columns={"candidate_id": "best_candidate", "pattern": "best_pattern", "headline": "best_headline"})[cols]
    if players is not None and weights is not None and not players.empty:
        imp = players["impact"].astype(float)
        z = (imp - imp.mean()) / (imp.std(ddof=0) or 1.0)
        floor = (weights["magnitude"] * magnitude_from_z(z) + weights["stakes"] * stakes).round(4)
        base = pd.DataFrame({"player_id": players["player_id"], "floor": floor.values})
        out = base.merge(out, on="player_id", how="left")
        out["significance"] = out[["significance", "floor"]].max(axis=1).round(4)
        out["n_candidates"] = out["n_candidates"].fillna(0).astype(int)
        out = out[cols]
    return out
