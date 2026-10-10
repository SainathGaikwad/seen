"""S9 — Impact dashboard: prove it. Attention lift vs matched controls, funnel, breadth, coverage of the long tail."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import CFG, DERIVED, data_banner, inject_css, load_csv, load_json, publications, require_run

from seen.fans.feed import load_events
from seen.impact.measure import attention_lift, breadth, funnel, simulate_funnel

st.set_page_config(page_title="SEEN — Impact", page_icon="🏏", layout="wide")
inject_css()
st.title("Impact intelligence")
data_banner()

if require_run():
    xi = load_csv("unseen_xi.csv")
    gap = load_csv("gap.csv")
    daily = load_csv("attention_daily.csv")
    pubs = publications()
    real_events = load_events(DERIVED)
    m = load_json("run_meta.json", {})

    st.subheader("1 · Attention lift versus matched controls")
    st.caption("Difference-in-differences on mean daily article views, 7 days before and after publication, against five athletes of similar significance in the same market tier who were not featured.")
    if not pubs:
        st.info("Publish a story (Route & publish) to measure it. With historical data, pick a past date to see the method run.")
    for p in pubs[-5:]:
        res = attention_lift(daily, gap, p["player_id"], pd.to_datetime(p["published"]).date())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(p["name"], f"{res.get('lift', 'n/a')}", "lift in daily views vs controls" if res.get("lift") is not None else res.get("note", ""))
        c2.metric("Before → after (featured)", f"{res.get('featured_before', '–')} → {res.get('featured_after', '–')}")
        c3.metric("Control mean change", f"{res.get('control_mean_change', '–')}")
        c4.write("Controls: " + ", ".join(res.get("controls", [])[:5]))
    st.caption("Reading: a positive lift means her attention rose more than comparable, un-featured athletes' did over the same days. Standard errors are shown in the API output; treat single stories as noisy.")

    st.subheader("2 · Fan funnel")
    use_sim = st.toggle("Show SIMULATED funnel (for UI development — clearly not measured)", value=real_events.empty)
    events = simulate_funnel(xi) if use_sim else real_events
    f = funnel(events)
    label = "SIMULATED" if use_sim else "measured in this session"
    st.markdown(f"**Source: {label}.**")
    stages = ["Impressions", "Reads", "Quiz answers", "Follows", "Returns"]
    values = [f["impressions"], f["reads"], f["quiz"], f["follows"], f["returns"]]
    top = values[0] or 1
    # horizontal bars rather than a funnel shape: a stage with zero events still shows as "0", instead of vanishing
    fig = go.Figure(go.Bar(y=stages[::-1], x=values[::-1], orientation="h", text=[f"{v:,} ({v / top * 100:.0f}%)" for v in values[::-1]],
                           textposition="outside", cliponaxis=False, marker=dict(color=["#d97706", "#f59e0b", "#2dd4bf", "#14b8a6", "#0ea5a4"])))
    fig.update_layout(height=300, margin=dict(l=10, r=90, t=10, b=10), xaxis=dict(title="events", range=[0, top * 1.25]))
    st.plotly_chart(fig, width="stretch")
    if not events.empty:
        by_lang = events[events.event == "follow"].groupby("language")["fan_id"].count().rename("follows")
        b = breadth(events)
        c1, c2, c3 = st.columns(3)
        c1.metric("Follow conversion", f"{(f['follows'] / f['impressions'] * 100) if f['impressions'] else 0:.1f}%", label)
        c2.metric("Athletes engaged per fan", b["athletes_per_fan"], "discovery breadth")
        c3.metric("Engagement Gini across athletes", b["gini"] if b["gini"] is not None else "–", "lower = broader")
        if by_lang.empty:
            st.caption("No follows yet in this session — press Follow on a card in the fan feed and this page updates.")
        else:
            st.markdown("**Follows by language**")
            st.bar_chart(by_lang, height=220)

    st.subheader("3 · Who the XI reaches")
    if not xi.empty:
        outside = int((~xi.team.isin(CFG["big_three"])).sum())
        noart = int(xi.no_article.sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("XI outside IND/ENG/AUS", f"{outside}/{len(xi)}")
        c2.metric("Countries in the XI", int(xi.team.nunique()))
        c3.metric("Without a Wikipedia article", noart, "knowledge gap")
        c4.metric("Languages per kit", len(m.get("languages", [])), ", ".join(m.get("languages", [])))
        st.markdown("**Athletes in this week's XI, by country**")
        by_team = xi.groupby("team")["player_id"].count().rename("athletes")
        try:
            st.bar_chart(by_team, height=260, horizontal=True)
        except TypeError:                      # older Streamlit without the horizontal option
            st.bar_chart(by_team, height=260)

    st.subheader("4 · Stories being missed")
    st.caption("High gap, high significance, not yet published — the next XI's shortlist.")
    pub_ids = {p["player_id"] for p in pubs}
    missed = gap[(~gap.player_id.isin(pub_ids)) & (gap.gap > 0)].sort_values(["significance", "gap"], ascending=False).head(10).copy()
    missed.insert(2, "status", missed.player_id.isin(set(xi.player_id)).map({True: "in this week's XI, not published", False: "not selected"}))
    missed["gap"] = missed["gap"].round(2)
    st.dataframe(missed[["name", "team", "status", "impact_rank", "attention_rank", "significance", "gap", "gap_confidence", "best_headline"]], width="stretch", hide_index=True)

    st.subheader("5 · Learning loop (weights in use)")
    st.dataframe(pd.DataFrame({"component": list(CFG["significance"].keys()), "weight": list(CFG["significance"].values())}), hide_index=True)
    st.caption("In pilot, weights update from measured lift by pattern and market (Bayesian updating with an exploration floor); the current weights are hand-set and published here for transparency.")
