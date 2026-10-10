"""Weekly Unseen XI: constrained greedy selection by visibility gap."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def load_manual(manual_dir: Path) -> tuple[dict, dict]:
    """consent.csv: player_id,consent(yes/no)   featured_log.csv: player_id,featured_date"""
    consent, featured = {}, {}
    cf = manual_dir / "consent.csv"
    if cf.exists():
        for _, r in pd.read_csv(cf).iterrows():
            consent[str(r.player_id)] = str(r.consent).strip().lower() in ("yes", "true", "1")
    ff = manual_dir / "featured_log.csv"
    if ff.exists():
        for _, r in pd.read_csv(ff).iterrows():
            featured[str(r.player_id)] = max(featured.get(str(r.player_id), date.min), pd.to_datetime(r.featured_date).date())
    return consent, featured


def select_xi(gap_df: pd.DataFrame, cfg: dict, as_of: date, manual_dir: Path, min_matches: int = 2,
              window_start: date | None = None) -> tuple[pd.DataFrame, list[str]]:
    c = cfg["unseen_xi"]
    big3 = set(cfg["big_three"])
    consent, featured = load_manual(manual_dir)
    if window_start is not None:
        # a feature dated inside this window is this release's own publication, not an earlier one: the cooldown
        # only applies to athletes featured before the window (re-running the same window keeps the same XI)
        featured = {pid: d for pid, d in featured.items() if d < window_start}
    notes = []
    min_m = int(c.get("min_matches", min_matches))
    max_rank = int(c.get("max_impact_rank", 10**6))
    positive = gap_df[gap_df["gap"] > 0]
    pool = positive[(positive["matches"] >= min_m) & (positive["impact_rank"] <= max_rank)].copy()
    # say who was never eligible, so the gap explorer's top rows are not a mystery
    too_low = positive[positive["impact_rank"] > max_rank].sort_values("gap", ascending=False)
    if not too_low.empty:
        names = ", ".join(f"{r['name']} (impact #{int(r.impact_rank)})" for _, r in too_low.head(6).iterrows())
        notes.append(f"not eligible — the XI is drawn from the top {max_rank} performers by impact; {len(too_low)} athletes with a positive gap "
                     f"ranked below that: {names}{'…' if len(too_low) > 6 else ''}")
    few = positive[(positive["impact_rank"] <= max_rank) & (positive["matches"] < min_m)]
    if not few.empty:
        notes.append(f"not eligible — fewer than {min_m} matches in the window: " + ", ".join(few["name"].head(6).tolist()))
    chosen, per_country = [], {}
    n_outside, n_bat, n_bowl, n_noart = 0, 0, 0, 0

    def ok(r) -> tuple[bool, str]:
        pid = str(r.player_id)
        if pid in consent and not consent[pid]:
            return False, "consent withheld"
        if pid in featured and (as_of - featured[pid]).days < c["cooldown_days"]:
            return False, "featured recently"
        if per_country.get(r.team, 0) >= c["max_per_country"]:
            return False, f"{r.team} already has {c['max_per_country']}"
        if bool(r.no_article) and n_noart >= int(c.get("max_no_article", 99)):
            return False, "cap on no-article athletes reached"
        if bool(getattr(r, "attention_incomplete", False)):
            return False, "attention data incomplete (a pageview fetch failed) — re-run to refetch"
        return True, ""

    for _, r in pool.iterrows():
        if len(chosen) >= c["size"]:
            break
        good, why = ok(r)
        if not good:
            notes.append(f"skipped {r['name']}: {why}")
            continue
        remaining = c["size"] - len(chosen)
        need_outside = max(0, c["min_outside_big_three"] - n_outside)
        if r.team in big3 and remaining <= need_outside:
            notes.append(f"held {r['name']}: reserving slots for players outside the big three")
            continue
        is_bat = r.role in ("batter", "all-rounder")
        is_bowl = r.role in ("bowler", "all-rounder")
        need_bat = max(0, c["min_batters"] - n_bat)
        need_bowl = max(0, c["min_bowlers"] - n_bowl)
        if remaining <= need_bat + need_bowl - (need_bat if is_bat else 0) - (need_bowl if is_bowl else 0) and not (is_bat and is_bowl):
            if (need_bat and not is_bat) or (need_bowl and not is_bowl):
                notes.append(f"held {r['name']}: role balance")
                continue
        chosen.append(r)
        per_country[r.team] = per_country.get(r.team, 0) + 1
        n_noart += 1 if bool(r.no_article) else 0
        n_outside += 0 if r.team in big3 else 1
        n_bat += 1 if is_bat else 0
        n_bowl += 1 if is_bowl else 0

    xi = pd.DataFrame(chosen).reset_index(drop=True)
    if not xi.empty:
        xi["xi_slot"] = range(1, len(xi) + 1)
        xi["why_now"] = xi.apply(_why, axis=1)
    return xi, notes


def _why(r) -> str:
    bits = [f"impact #{int(r.impact_rank)}", f"attention #{int(r.attention_rank)}"]
    if bool(r.no_article):
        bits.append("no Wikipedia article in any tracked language")
    elif r.expected_views and r.views_window_total:
        bits.append(f"{int(r.views_window_total):,} views vs ~{int(r.expected_views):,} expected")
    if isinstance(r.best_headline, str) and r.best_headline:
        bits.append(r.best_headline)
    return "; ".join(bits)


def record_featured(manual_dir: Path, player_ids: list[str], on: date) -> None:
    ff = manual_dir / "featured_log.csv"
    df = pd.read_csv(ff) if ff.exists() else pd.DataFrame(columns=["player_id", "featured_date"])
    new = pd.DataFrame({"player_id": player_ids, "featured_date": [on.isoformat()] * len(player_ids)})
    pd.concat([df, new], ignore_index=True).to_csv(ff, index=False)
