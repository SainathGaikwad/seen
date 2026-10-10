"""S6 — Route and publish through pipes ICC already owns."""
from datetime import datetime, timezone

import streamlit as st

from common import MANUAL, add_publication, data_banner, inject_css, load_csv, load_kit, publications, require_run, today

from seen.intelligence.unseen_xi import record_featured

st.set_page_config(page_title="SEEN — Route & publish", page_icon="🏏", layout="wide")
inject_css()
st.title("Route and publish")
data_banner()

CHANNELS = {
    "creator_club": ("ICC Creator Club brief", "creator_brief"),
    "app_card": ("ICC app story card + notification", "social_posts"),
    "commentary": ("Commentary production pack", "commentator_note"),
    "social": ("ICC social (post + infographic)", "social_posts"),
    "wcw": ("Women's Cricket Week bundle", "article"),
    "gemini": ("Gemini Insight Card export (JSON)", "infographic"),
    "fan_feed": ("SEEN fan discovery feed", "video_script"),
}

if require_run():
    xi = load_csv("unseen_xi.csv")
    if xi.empty:
        st.stop()
    names = xi["name"].tolist()
    pre = st.session_state.get("selected_player")
    default = xi[xi.player_id == pre]["name"].iloc[0] if pre in set(xi.player_id) else names[0]
    pick = st.selectbox("Athlete (Unseen XI)", names, index=names.index(default))
    pid = xi[xi.name == pick].iloc[0].player_id
    kit = load_kit(pid)
    if not kit:
        st.stop()
    verified = all(v["passed"] for v in kit["checks"].values())
    st.markdown(f"**{kit['headline']}** — claim checker: {'all formats verified ✅' if verified else 'some formats blocked ⛔ (fix them in the Story kit page)'}")

    st.subheader("Channels")
    chosen = []
    cols = st.columns(2)
    for i, (key, (label, fmt)) in enumerate(CHANNELS.items()):
        with cols[i % 2]:
            if st.checkbox(label, value=key in ("creator_club", "app_card", "fan_feed"), key=f"ch_{pid}_{key}"):
                chosen.append(key)
            with st.expander("preview"):
                st.code(kit["formats"][fmt].split("\n\nGuidance")[0][:700], language=None, wrap_lines=True)
    st.caption("Clip slot: **ICC rights required** — the prototype links to official highlights; production attaches rights-cleared clips through ICC's own pipeline.")
    from datetime import timedelta
    when = st.date_input("Publish date", value=today() - timedelta(days=7),
                         help="For the demo, a date at least 7 days before the end of the attention window lets the dashboard compare before and after with real daily views.")
    already = [p for p in publications() if p.get("player_id") == pid]
    if already:
        st.caption(f"Already published on {already[-1].get('published')} to {', '.join(already[-1].get('channels', []))}; publishing again replaces that record.")
    if st.button("Publish", type="primary", disabled=not verified or not chosen):
        rec = {"player_id": pid, "name": kit["name"], "team": kit["team"], "headline": kit["headline"], "channels": chosen,
               "published": when.isoformat(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        add_publication(rec)
        record_featured(MANUAL, [pid], when)
        st.success(f"Published to {len(chosen)} channel(s). The creator page and fan feed now carry this story; the impact dashboard will measure it.")

    st.subheader("Published so far")
    pubs = publications()
    if pubs:
        st.dataframe([{k: v for k, v in p.items() if k != "player_id"} for p in pubs], width="stretch", hide_index=True)
    else:
        st.info("Nothing published yet.")
