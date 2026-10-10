"""Impact measurement: attention lift versus matched controls, funnel metrics, breadth.

Lift (difference-in-differences):
  lift = (featured_after - featured_before) - mean(control_after - control_before)
computed on mean daily article views over `days` before/after the publication date, with controls
= athletes of similar significance and the same market tier that were not featured.
The demo funnel is SIMULATED and labelled; only the attention series can be real.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def daily_mean(daily: pd.DataFrame, player_id: str, start: date, end: date) -> float | None:
    d = daily[(daily.player_id == player_id) & (daily.date >= start) & (daily.date <= end)]
    if d.empty:
        return None
    return float(d.groupby("date")["views"].sum().mean())


def attention_lift(daily: pd.DataFrame, gap_df: pd.DataFrame, player_id: str, published: date, days: int = 7, n_controls: int = 5) -> dict:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    before = (published - timedelta(days=days), published - timedelta(days=1))
    after = (published, published + timedelta(days=days - 1))
    me = gap_df[gap_df.player_id == player_id]
    if me.empty:
        return {"error": "player not in gap table"}
    me = me.iloc[0]
    pool = gap_df[(gap_df.player_id != player_id) & (gap_df.market_tier == me.market_tier) & (~gap_df.no_article)].copy()
    pool["dist"] = (pool.significance - me.significance).abs()
    controls = pool.sort_values("dist").head(n_controls)
    f_b, f_a = daily_mean(daily, player_id, *before), daily_mean(daily, player_id, *after)
    diffs = []
    for _, c in controls.iterrows():
        cb, ca = daily_mean(daily, c.player_id, *before), daily_mean(daily, c.player_id, *after)
        if cb is not None and ca is not None:
            diffs.append(ca - cb)
    if f_b is None or f_a is None or not diffs:
        return {"lift": None, "note": "insufficient daily data in the before/after windows", "controls": controls.name.tolist()}
    lift = (f_a - f_b) - float(np.mean(diffs))
    se = float(np.std(diffs, ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else None
    return {"featured_before": round(f_b, 1), "featured_after": round(f_a, 1), "control_mean_change": round(float(np.mean(diffs)), 1),
            "lift": round(lift, 1), "lift_se": round(se, 1) if se is not None else None, "controls": controls.name.tolist(), "days": days}


def funnel(events: pd.DataFrame) -> dict:
    if events.empty:
        return {"impressions": 0, "reads": 0, "quiz": 0, "follows": 0, "returns": 0}
    counts = events.groupby("event")["fan_id"].count().to_dict()
    return {"impressions": int(counts.get("impression", 0)), "reads": int(counts.get("read", 0)), "quiz": int(counts.get("quiz", 0)),
            "follows": int(counts.get("follow", 0)), "returns": int(counts.get("return", 0))}


def breadth(events: pd.DataFrame) -> dict:
    """Discovery breadth: distinct athletes engaged per fan, and a Gini of engagement across athletes."""
    if events.empty:
        return {"athletes_per_fan": 0, "gini": None}
    per_fan = events.groupby("fan_id")["player_id"].nunique().mean()
    per_player = events.groupby("player_id")["fan_id"].count().sort_values().to_numpy(dtype=float)
    if per_player.sum() == 0:
        g = None
    else:
        n = len(per_player)
        idx = np.arange(1, n + 1)
        g = float((2 * (idx * per_player).sum()) / (n * per_player.sum()) - (n + 1) / n)
    return {"athletes_per_fan": round(float(per_fan), 2), "gini": round(g, 3) if g is not None else None}


def simulate_funnel(xi: pd.DataFrame, n_fans: int = 400, seed: int = 7) -> pd.DataFrame:
    """SIMULATED fan events for UI development. Never present as measured."""
    rng = np.random.default_rng(seed)
    rows = []
    langs = ["en", "hi", "ur", "ta", "bn"]
    for fan in range(n_fans):
        fid = f"sim-fan-{fan:04d}"
        lang = rng.choice(langs, p=[0.45, 0.3, 0.1, 0.08, 0.07])
        for _, p in xi.iterrows():
            rows.append(("simulated", fid, p.player_id, "impression", "fan_feed", lang))
            if rng.random() < 0.55:
                rows.append(("simulated", fid, p.player_id, "read", "fan_feed", lang))
                if rng.random() < 0.5:
                    rows.append(("simulated", fid, p.player_id, "quiz", "fan_feed", lang))
                if rng.random() < 0.22:
                    rows.append(("simulated", fid, p.player_id, "follow", "fan_feed", lang))
                    if rng.random() < 0.6:
                        rows.append(("simulated", fid, p.player_id, "return", "notification", lang))
    return pd.DataFrame(rows, columns=["ts", "fan_id", "player_id", "event", "channel", "language"])
