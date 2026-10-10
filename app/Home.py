"""S1 — The Unseen XI (operator home)."""
import pandas as pd
import streamlit as st

from common import CFG, data_banner, inject_css, load_csv, load_json, meta, require_run, xi_card

st.set_page_config(page_title="SEEN — Unseen XI", page_icon="🏏", layout="wide")
inject_css()
st.title("SEEN · The Unseen XI")
st.caption("The eleven women cricketers whose performance most exceeds the attention they receive — rebuilt from public data every week.")
data_banner()

if require_run():
    xi = load_csv("unseen_xi.csv")
    gap = load_csv("gap.csv")
    w = load_json("window.json", {})
    m = meta()
    xc = CFG.get("unseen_xi", {})
    max_rank, min_m = int(xc.get("max_impact_rank", 10**6)), int(xc.get("min_matches", 2))
    eligible = (gap.gap > 0) & (gap.impact_rank <= max_rank) & (gap.matches >= min_m)
    ineligible = gap[(gap.gap > 0) & ~eligible].sort_values("gap", ascending=False)

    c1, c2, c3, c4 = st.columns(4)
    try:
        s0, s1 = pd.to_datetime(w["start"]), pd.to_datetime(w["end"])
        span = f"{s0.day} {s0:%b} – {s1.day} {s1:%b %Y}"   # no %-d: it is not portable to Windows
    except Exception:
        span = str(w.get("label", ""))
    c1.metric("Matches in the window", int(w.get("n_matches", 0)), span)
    c2.metric("Athletes ranked", int(m.get("n_players", 0)), f"{int(m.get('n_candidates', 0))} story candidates")
    outside = int((~xi.team.isin(CFG["big_three"])).sum()) if not xi.empty else 0
    c3.metric("XI from outside IND/ENG/AUS", outside, "constraint ≥ 3")
    gm = m.get("gap_model") or {}
    r2s = (gm.get("structural_model") or {}).get("r2")
    c4.metric("Attention explained", f"R² {r2s:.2f}" if isinstance(r2s, (int, float)) else "n/a", f"by market + prior fame, n={gm.get('n_fit', 0)}")

    st.subheader("This week's XI")
    if xi.empty:
        st.info("The selector found no eligible athletes (check constraints in config.yaml).")
    else:
        rows = [xi.iloc[i:i + 4] for i in range(0, len(xi), 4)]
        for chunk in rows:
            cols = st.columns(4)
            for col, (_, r) in zip(cols, chunk.iterrows()):
                with col:
                    st.markdown(xi_card(r), unsafe_allow_html=True)
        notes = load_json("xi_notes.json", []) or []
        held = [n for n in notes if not n.startswith("not eligible")]
        with st.expander(f"Selection notes — {len(ineligible)} athletes with a positive gap were not eligible; {len(held)} held back by the constraints"):
            st.write(f"· The XI is drawn from the top {max_rank} performers by impact with at least {min_m} matches in the window, so a large gap "
                     f"alone does not qualify: {len(ineligible)} athletes with a positive gap ranked below that cut"
                     + (" — " + ", ".join(f"{r['name']} (impact #{int(r.impact_rank)})" for _, r in ineligible.head(6).iterrows()) + ("…" if len(ineligible) > 6 else "") if not ineligible.empty else "")
                     + ". Constraints on the eligible pool: at most 3 per country, at least 3 from outside India, England and Australia, "
                     "4 batters and 4 bowlers, consent, a 14-day cooldown after being featured, and a cap on athletes without a Wikipedia article.")
            for n in held[:40]:
                st.write("· " + n)
            if not held:
                st.write("· No eligible athlete was held back by a constraint in this run.")
        st.download_button("Export XI (CSV)", xi.to_csv(index=False).encode(), "unseen_xi.csv", "text/csv")

    st.subheader("Performance against attention — every athlete in the window")
    try:
        import numpy as np
        import plotly.graph_objects as go
        pts = gap[(~gap.no_article.astype(bool)) & (gap.views_window_total > 0)].copy()
        if "attention_incomplete" in pts.columns:
            pts = pts[~pts.attention_incomplete.astype(bool)]
        pm = gm.get("performance_model") or {}
        beta = pm.get("beta") or gm.get("beta") or {}
        in_xi = pts.player_id.isin(set(xi.player_id)) if not xi.empty else pd.Series(False, index=pts.index)
        hover = (pts["name"].astype(str) + " · " + pts["team"].astype(str) + "<br>impact #" + pts["impact_rank"].astype(int).astype(str)
                 + " · attention #" + pts["attention_rank"].astype(int).astype(str) + "<br>" + pts["views_window_total"].astype(int).map("{:,}".format)
                 + " views vs " + pts["expected_views"].fillna(0).astype(int).map("{:,}".format) + " expected")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pts.significance[~in_xi], y=pts.views_window_total[~in_xi], mode="markers", name="other athletes",
                                 marker=dict(size=7, color="#8A94A3", opacity=0.8), text=hover[~in_xi], hoverinfo="text"))
        fig.add_trace(go.Scatter(x=pts.significance[in_xi], y=pts.views_window_total[in_xi], mode="markers", name="Unseen XI",
                                 marker=dict(size=12, color="#F4B942", line=dict(color="#10192B", width=1)), text=hover[in_xi], hoverinfo="text"))
        if "intercept" in beta and "significance" in beta:
            xs = np.linspace(0.02, 1.0, 60)
            fig.add_trace(go.Scatter(x=xs, y=np.exp(beta["intercept"] + beta["significance"] * xs), mode="lines",
                                     name="expected attention for this performance", line=dict(color="#10192B", width=2), hoverinfo="skip"))
        fig.update_yaxes(type="log", title="article views in the window (all tracked editions)")
        fig.update_xaxes(title="performance significance (0–1, from ball-by-ball data)", range=[0, 1.02])
        fig.update_layout(height=460, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, width="stretch")
        r2p = pm.get("r2")
        st.caption((f"Performance alone explains R² {r2p:.2f} of attention; adding market size and prior fame reaches R² {r2s:.2f}. " if isinstance(r2p, (int, float)) and isinstance(r2s, (int, float)) else "")
                   + "The Unseen XI are the largest gaps below the line, subject to the selection constraints. Hover a point for the athlete.")
    except Exception as exc:  # the chart is illustrative; never block the page
        st.caption(f"Scatter unavailable: {exc}")

    st.subheader("Gap explorer — every athlete in the window")
    st.caption("gap = attention below what athletes who performed similarly received (log scale). It splits into gap_structural "
               "(the part explained by a small home market and low prior fame) and gap_anomaly (unexplained even after that). Sort any column.")
    only_eligible = st.checkbox(f"Only athletes eligible for the XI (top {max_rank} by impact, at least {min_m} matches)", value=True)
    cols = ["gap_rank", "name", "team", "role", "impact_rank", "attention_rank", "views_window_total", "expected_views", "no_article", "gap", "gap_structural", "gap_anomaly", "gap_confidence", "best_pattern", "best_headline"]
    view = gap[eligible][[c for c in cols if c in gap.columns]].copy() if only_eligible else gap[[c for c in cols if c in gap.columns]].copy()
    view.insert(1, "in_xi", view["name"].isin(set(xi["name"])) if not xi.empty else False)
    for c in ("gap", "gap_structural", "gap_anomaly"):
        if c in view.columns:
            view[c] = view[c].round(2)
    st.dataframe(view, width="stretch", hide_index=True, height=420,
                 column_config={"in_xi": st.column_config.CheckboxColumn("in XI", help="Selected for this week's Unseen XI"),
                                "no_article": st.column_config.CheckboxColumn("no article")})
    st.caption("How to read: impact = runs + 20 × wickets in the window (Cricsheet). Attention = log(1 + article views across tracked language editions). "
               "expected_views = what the performance-only line predicts; the structural line (significance + market tier + prior fame) explains how much of each gap is structural. Details in gap_summary.json.")
