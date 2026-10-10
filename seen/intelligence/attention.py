"""Attention index per athlete for the window (live public signals or a labelled synthetic fixture).

Live signals: Wikipedia pageviews across configured language editions (window and a 60-day
baseline) and, optionally, GDELT news-article counts. The index is log1p(total window views).
Everything is stored per player with the signal source written next to it.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import market_tier
from ..ingest import gdelt, pageviews, wikidata
from .windows import Window

log = logging.getLogger(__name__)

FIXTURE_LABEL = "SYNTHETIC FIXTURE — not real attention data (for UI development only)"
LIVE_LABEL = "Wikimedia pageviews (public API)"
LIVE_LABEL_GDELT = "Wikimedia pageviews (public API) + GDELT news counts"


def build_attention(con, cfg: dict, window: Window, players: pd.DataFrame, mode: str = "live",
                    seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (attention table, daily series). mode: 'live' | 'fixture'."""
    editions = cfg["attention"]["editions"]
    base_days = int(cfg["window"]["baseline_days"])
    b_start = window.start - timedelta(days=base_days)
    b_end = window.start - timedelta(days=1)
    cache = Path(cfg["paths"]["cache"])

    rows, daily = [], []
    if mode == "fixture":
        rng = np.random.default_rng(seed)
        dates_b = pd.date_range(b_start, b_end)
        dates_w = pd.date_range(window.start, window.end)
        imp = players["impact"].astype(float)
        imp_share = (imp / (imp.max() or 1.0)).fillna(0)
        for (_, p), share in zip(players.iterrows(), imp_share):
            tier = market_tier(p.team, cfg)
            no_article = rng.random() < {1: 0.35, 2: 0.05, 3: 0.02}[tier]
            base = {1: 60, 2: 500, 3: 2500}[tier] * float(np.exp(rng.normal(0, 0.9)))
            titles = {} if no_article else {"en": p["name"]}
            if not no_article:
                b_series = rng.poisson(base, len(dates_b))
                w_series = rng.poisson(base * (1 + 6 * share) , len(dates_w))
                for d, v in zip(dates_b, b_series):
                    daily.append((p.player_id, "en", d.date(), int(v), "baseline"))
                for d, v in zip(dates_w, w_series):
                    daily.append((p.player_id, "en", d.date(), int(v), "window"))
                vw, vb = int(w_series.sum()), int(b_series.sum())
            else:
                vw = vb = 0
            rows.append(_row(p, tier, None, titles, vw, vw, 0, vb, len(dates_b), None, FIXTURE_LABEL))
    else:
        ids = [str(i) for i in players["key_cricinfo"].fillna("") if i]
        mapping = wikidata.map_players(ids, editions, cache)
        # fetch every (edition, title, range) with a small thread pool: latency, not rate limits, dominates
        from concurrent.futures import ThreadPoolExecutor
        jobs = []
        for _, p in players.iterrows():
            cid = str(p.key_cricinfo) if pd.notna(p.key_cricinfo) else ""
            for e, title in mapping.get(cid, {"titles": {}}).get("titles", {}).items():
                jobs.append((e, title))
        log.info("fetching pageviews for %s (edition, article) pairs across %s athletes — one request each, gently rate-limited",
                 len(jobs), len(players))
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda j: pageviews.fetch_baseline_and_window(j[0], j[1], b_start, b_end, window.start, window.end, cache, pause=0.25), jobs))
        series = {}
        for (e, title), (b_series, w_series) in zip(jobs, results):
            series[(e, title, window.start, window.end)] = w_series
            series[(e, title, b_start, b_end)] = b_series
        n_failed = sum(1 for b_series, _ in results if b_series is None)
        if n_failed:
            log.warning("%s of %s pageview series failed after retries; affected athletes are flagged attention_incomplete "
                        "and excluded from the XI — re-run to refetch only the failures (successes are cached)", n_failed, len(jobs))
        for _, p in players.iterrows():
            tier = market_tier(p.team, cfg)
            cid = str(p.key_cricinfo) if pd.notna(p.key_cricinfo) else ""
            m = mapping.get(cid, {"qid": None, "titles": {}})
            titles = m.get("titles", {})
            vw_total = vb_total = vw_en = 0
            incomplete = False
            for e, title in titles.items():
                w = series.get((e, title, window.start, window.end), {})
                b = series.get((e, title, b_start, b_end), {})
                if w is None or b is None:
                    incomplete = True
                    w, b = w or {}, b or {}
                for d, v in w.items():
                    daily.append((p.player_id, e, pd.to_datetime(d).date(), v, "window"))
                for d, v in b.items():
                    daily.append((p.player_id, e, pd.to_datetime(d).date(), v, "baseline"))
                vw_total += sum(w.values())
                vb_total += sum(b.values())
                if e == "en":
                    vw_en = sum(w.values())
            news = None
            if cfg["attention"].get("gdelt"):
                g = gdelt.article_count(p["name"], window.start, window.end, cache)
                news = g.get("count")
            row = _row(p, tier, m.get("qid"), titles, vw_total, vw_en, vw_total - vw_en, vb_total, base_days, news,
                       LIVE_LABEL_GDELT if cfg["attention"].get("gdelt") else LIVE_LABEL)
            row["label"] = m.get("label")
            row["attention_incomplete"] = incomplete
            rows.append(row)

    att = pd.DataFrame(rows)
    if "label" not in att.columns:
        att["label"] = None
    if "attention_incomplete" not in att.columns:
        att["attention_incomplete"] = False
    daily_df = pd.DataFrame(daily, columns=["player_id", "edition", "date", "views", "period"])
    return att, daily_df


def _row(p, tier, qid, titles, vw_total, vw_en, vw_other, vb_total, base_days, news, source) -> dict:
    baseline_daily = vb_total / max(base_days, 1)
    no_article = len(titles) == 0
    return {
        "player_id": p.player_id, "name": p["name"], "team": p.team, "key_cricinfo": p.key_cricinfo,
        "market_tier": tier, "qid": qid, "article_en": titles.get("en"), "editions": ",".join(sorted(titles.keys())),
        "n_editions": len(titles), "no_article": no_article,
        "views_window_total": int(vw_total), "views_window_en": int(vw_en), "views_window_other": int(vw_other),
        "views_baseline_total": int(vb_total), "baseline_daily": round(baseline_daily, 2),
        "news_count": news,
        "attention_index": round(float(np.log1p(vw_total)), 4),
        "attention_source": source,
    }
