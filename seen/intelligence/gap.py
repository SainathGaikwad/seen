"""Visibility gap: how far an athlete's attention sits below what her performance predicts.

Two fitted lines, both ordinary least squares on log(1 + article views in the window):

  performance-only   A_perf = a0 + a1 * S                                   → gap        = A_perf − A   (primary)
  structural         A_full = b0 + b1 * S + b2 * log(market_tier) + b3 * log1p(baseline_daily)
                                                                            → gap_anomaly = A_full − A  (diagnostic)

The primary gap asks: "given how she played, how much attention should she have had, compared with
athletes who played similarly?" — market size and prior fame are NOT allowed to excuse the gap; instead the
structural line decomposes it: gap_structural = A_perf − A_full is the part explained by a small market
and low prior fame, gap_anomaly the part that is unexplained even after that. The Unseen XI is selected on
the primary gap; the dashboard shows the decomposition so editors can see *why* an athlete is under-seen.

Athletes with no Wikipedia article get A = 0 and are flagged: their gap is the maximum possible.
Athletes whose attention fetch failed are flagged attention_incomplete and excluded from fitting and selection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ols(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, dict]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    return beta, {"r2": round(1 - ss_res / ss_tot, 4), "resid_sd": round(float(resid.std(ddof=1)) if len(resid) > 1 else 0.0, 4)}


def fit_gap(players: pd.DataFrame, sig: pd.DataFrame, att: pd.DataFrame, window_days: int) -> tuple[pd.DataFrame, dict]:
    df = players[["player_id", "name", "team", "role", "impact", "impact_rank", "matches", "runs", "wickets"]].merge(
        sig[["player_id", "significance", "best_candidate", "best_pattern", "best_headline", "n_candidates"]], on="player_id", how="left")
    df["significance"] = df["significance"].fillna(0.0)
    df = df.merge(att.drop(columns=["name", "team"]), on="player_id", how="left")
    df["views_window_total"] = df["views_window_total"].fillna(0).astype(int)
    df["baseline_daily"] = df["baseline_daily"].fillna(0.0)
    df["no_article"] = df["no_article"].fillna(True).astype(bool)
    df["market_tier"] = df["market_tier"].fillna(1).astype(int)
    if "attention_incomplete" in df.columns:
        df["attention_incomplete"] = df["attention_incomplete"].fillna(False).astype(bool)
    else:
        df["attention_incomplete"] = False
    df["attention_index"] = np.log1p(df["views_window_total"].astype(float))
    df["window_daily"] = df["views_window_total"] / max(window_days, 1)
    df["uplift"] = np.where(df["baseline_daily"] > 0, df["window_daily"] / df["baseline_daily"].replace(0, np.nan), np.nan)

    fit_mask = (~df["no_article"]) & (df["views_window_total"] > 0) & (~df["attention_incomplete"])
    S = df["significance"].astype(float).to_numpy()
    T = np.log(df["market_tier"].astype(float).to_numpy())
    F = np.log1p(df["baseline_daily"].astype(float).to_numpy())
    y = df["attention_index"].astype(float).to_numpy()
    n_fit = int(fit_mask.sum())
    summary = {"n_fit": n_fit, "n_total": int(len(df))}

    X_perf_all = np.column_stack([np.ones(len(df)), S])
    X_full_all = np.column_stack([np.ones(len(df)), S, T, F])
    if n_fit >= 6:
        m = fit_mask.to_numpy()
        beta_p, stats_p = _ols(X_perf_all[m], y[m])
        beta_f, stats_f = _ols(X_full_all[m], y[m])
        summary["performance_model"] = {"beta": {"intercept": round(float(beta_p[0]), 4), "significance": round(float(beta_p[1]), 4)}, **stats_p}
        summary["structural_model"] = {"beta": {"intercept": round(float(beta_f[0]), 4), "significance": round(float(beta_f[1]), 4),
                                                "log_market_tier": round(float(beta_f[2]), 4), "log1p_baseline_daily": round(float(beta_f[3]), 4)}, **stats_f}
    else:
        mean_y = float(y[fit_mask.to_numpy()].mean()) if n_fit else 0.0
        beta_p, beta_f = np.array([mean_y, 0.0]), np.array([mean_y, 0.0, 0.0, 0.0])
        summary["performance_model"] = {"beta": None, "r2": None, "resid_sd": None, "note": "too few athletes with articles to fit; using mean"}
        summary["structural_model"] = summary["performance_model"]
    # backwards-compatible top-level keys (dashboard)
    summary["beta"] = summary["structural_model"].get("beta")
    summary["r2"] = summary["performance_model"].get("r2")
    summary["resid_sd"] = summary["performance_model"].get("resid_sd")

    df["expected_attention"] = X_perf_all @ beta_p
    df["expected_attention_full"] = X_full_all @ beta_f
    df["gap"] = df["expected_attention"] - df["attention_index"]                 # primary: versus performance peers
    df["gap_anomaly"] = df["expected_attention_full"] - df["attention_index"]   # unexplained after market and fame
    df["gap_structural"] = df["expected_attention"] - df["expected_attention_full"]  # explained by market and fame
    sd = summary["resid_sd"] or 1.0
    df["gap_z"] = df["gap"] / sd
    df["gap_confidence"] = pd.cut(df["gap_z"].abs(), bins=[-1, 0.5, 1.0, 2.0, 99], labels=["low", "medium", "high", "very high"]).astype(str)
    df["expected_views"] = np.expm1(df["expected_attention"]).round(0)
    df["expected_views_full"] = np.expm1(df["expected_attention_full"]).round(0)
    df = df.sort_values("gap", ascending=False).reset_index(drop=True)
    df["gap_rank"] = range(1, len(df) + 1)
    df["attention_rank"] = df["views_window_total"].rank(ascending=False, method="min").astype(int)
    return df, summary
