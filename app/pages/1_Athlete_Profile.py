"""S2 — Athlete visibility profile: performance events against attention, with the expected band."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import DERIVED, data_banner, fmt_int, inject_css, load_csv, load_json, require_run

st.set_page_config(page_title="SEEN — Athlete profile", page_icon="🏏", layout="wide")
inject_css()
st.title("Athlete visibility profile")
data_banner()

if require_run():
    gap = load_csv("gap.csv")
    daily = load_csv("attention_daily.csv")
    players = load_csv("players.csv")
    xi = load_csv("unseen_xi.csv")
    w = load_json("window.json", {})

    names = gap.sort_values("gap_rank")["name"].tolist()
    pre = st.session_state.get("selected_player")
    if pre in set(gap.player_id):
        default = gap[gap.player_id == pre]["name"].iloc[0]       # the athlete chosen on another page
    else:
        with_article = xi[~xi.no_article.astype(bool)] if not xi.empty else xi
        if not with_article.empty:
            default = with_article.sort_values("impact_rank").iloc[0]["name"]   # the XI's best performer opens first
        else:
            default = xi.iloc[0]["name"] if not xi.empty else names[0]
    pick = st.selectbox("Athlete", names, index=names.index(default) if default in names else 0)
    r = gap[gap.name == pick].iloc[0]
    st.session_state["selected_player"] = r.player_id

    a, b, c, d, e = st.columns(5)
    a.metric("Impact rank", f"#{int(r.impact_rank)}", f"{int(r.runs)} runs · {int(r.wickets)} wkts")
    b.metric("Attention rank", f"#{int(r.attention_rank)}", "no article" if bool(r.no_article) else f"{fmt_int(r.views_window_total)} views")
    c.metric("Expected views", fmt_int(r.expected_views), "for this level of performance")
    d.metric("Gap", f"{float(r.gap):.2f}", f"confidence {r.gap_confidence}")
    e.metric("Significance", f"{float(r.significance):.2f}", str(r.best_pattern) if isinstance(r.best_pattern, str) else "no pattern")

    # timeline
    _pm = None
    try:
        import duckdb
        con = duckdb.connect(str(DERIVED.parent / "seen.duckdb"), read_only=True)
        _pm = con.execute("SELECT date, opponent, runs, wickets, balls_faced, runs_conceded FROM player_match WHERE player_id = ? AND date BETWEEN ? AND ? ORDER BY date",
                          [r.player_id, w.get("start"), w.get("end")]).df()
        con.close()
    except Exception:
        _pm = pd.DataFrame()

    fig = go.Figure()
    d_me = daily[daily.player_id == r.player_id].copy()
    if not d_me.empty:
        d_me["date"] = pd.to_datetime(d_me["date"])
        groups = sorted(d_me.groupby("edition"), key=lambda kv: (kv[0] != "en", kv[0]))   # English first: it carries the main line
        for ed, grp in groups:
            g = grp.groupby("date")["views"].sum().reset_index()
            fig.add_trace(go.Scatter(x=g["date"], y=g["views"], mode="lines", name=f"views ({ed})", line=dict(width=2.2 if ed == "en" else 1.2)))
        base = float(r.baseline_daily or 0)
        window_days = (pd.to_datetime(w["end"]) - pd.to_datetime(w["start"])).days + 1 if w.get("start") and w.get("end") else 1
        exp_daily = float(r.expected_views or 0) / max(1, window_days)
        fig.add_hrect(y0=0, y1=exp_daily, fillcolor="#f59e0b", opacity=0.08, line_width=0)
        fig.add_hline(y=exp_daily, line_dash="dash", line_color="#b45309",
                      annotation_text=f"expected for this performance ≈ {exp_daily:,.0f} views/day", annotation_position="top left",
                      annotation_font_color="#b45309")
        if base:
            fig.add_hline(y=base, line_dash="dot", line_color="#64748b", annotation_text=f"60-day baseline ≈ {base:,.0f}/day",
                          annotation_position="bottom right", annotation_font_color="#64748b")
    if _pm is not None and not _pm.empty:
        _pm["date"] = pd.to_datetime(_pm["date"])
        ymax = float(d_me.groupby("date")["views"].sum().max()) if not d_me.empty else 1.0
        # labels on hover only: tournament matches are a few days apart and text labels overlap
        fig.add_trace(go.Scatter(x=_pm["date"], y=[ymax * 1.05] * len(_pm), mode="markers", name="matches",
                                 marker=dict(size=12, symbol="diamond", color="#0ea5a4"),
                                 hovertext=[f"{int(x.runs)} runs / {int(x.wickets)} wkts v {x.opponent} ({x.date.date().isoformat()})" for _, x in _pm.iterrows()],
                                 hoverinfo="text"))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=40), legend=dict(orientation="h", y=-0.18), yaxis_title="daily article views", xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption("Daily Wikipedia article views across the tracked editions. Diamonds mark her matches (hover for the scorecard line); the shaded band is the attention "
               "an athlete with this performance would be expected to draw, so the space between the band's top and her line is the gap.")
    if "gap_structural" in gap.columns and pd.notna(r.gap_structural):
        gs, ga = float(r.gap_structural), float(r.gap_anomaly)
        st.markdown(f"**Why the gap:** {float(r.gap):+.2f} = **{gs:+.2f} structural** (small home market, low prior fame: the part ICC's distribution can change) "
                    f"+ **{ga:+.2f} unexplained** (what a story could still move). Expected views with market and fame priced in: {fmt_int(r.expected_views_full)}.")
    if bool(r.no_article):
        st.error("No Wikipedia article in any tracked language edition. This is the maximum possible visibility gap — and a Women in Red statistic in itself.")
    else:
        st.caption(f"Editions with an article: {r.editions}. Uplift during the window vs the 60-day baseline: {float(r.uplift):.1f}×" if pd.notna(r.uplift) else f"Editions with an article: {r.editions}.")

    st.subheader("Where the significance comes from")
    cands = load_csv("candidates_scored.csv")
    mine = cands[cands.player_id == r.player_id].sort_values("significance", ascending=False)
    if mine.empty:
        st.info("No narrative pattern fired for this athlete in the window; her significance is the impact-only fallback.")
    else:
        st.dataframe(mine[["pattern", "significance", "part_rarity", "part_stakes", "part_magnitude", "part_arc", "rarity_count", "headline"]],
                     width="stretch", hide_index=True)
    try:
        st.page_link("pages/2_Story_Opportunity.py", label="→ Find stories for this athlete", icon="🔎")
    except Exception:
        st.caption("Next: open the Story opportunity page for this athlete.")
