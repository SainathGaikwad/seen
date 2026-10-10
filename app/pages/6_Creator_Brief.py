"""S7 — Creator brief: what a Creator Club member receives, with attribution."""
import csv
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from common import DERIVED, data_banner, inject_css, load_kit, publications, require_run

from seen.stories.compiler import GUIDANCE_MARKER

st.set_page_config(page_title="SEEN — Creator brief", page_icon="🏏", layout="wide")
inject_css()
st.title("Creator brief")
st.caption("Creator-facing view. Everything here is pre-verified; the [F#] tags point to sourced facts.")
data_banner()

if require_run():
    pubs = [p for p in publications() if "creator_club" in p.get("channels", [])]
    if not pubs:
        st.info("No briefs published to the Creator Club yet. Publish one from the Route & publish page.")
        st.stop()
    labels = [f"{p['name']} — {p['headline']}" for p in pubs]
    i = st.selectbox("Briefs", range(len(labels)), format_func=lambda k: labels[k])
    p = pubs[i]
    kit = load_kit(p["player_id"])
    body, _, guidance = kit["formats"]["creator_brief"].partition(GUIDANCE_MARKER)
    left, right = st.columns([3, 2])
    with left:
        st.code(body, language=None, wrap_lines=True)
        if guidance:
            st.markdown("**Guidance**")
            for line in guidance.splitlines():
                st.write("· " + line)
    with right:
        st.markdown("**Assets**")
        st.download_button("Infographic spec (JSON)", kit["formats"]["infographic"], f"{p['player_id']}_infographic.json", "application/json")
        st.download_button("60-second script", kit["formats"]["video_script"].split(GUIDANCE_MARKER)[0], f"{p['player_id']}_script.txt", "text/plain")
        st.download_button("Quiz (JSON)", kit["formats"]["quiz"], f"{p['player_id']}_quiz.json", "application/json")
        st.markdown("**Clip slot** — ICC-cleared highlight required (not included in the prototype).")
        st.markdown("**Attribution**")
        link = st.text_input("I posted this — paste the post URL")
        if st.button("Submit post link") and link:
            path = DERIVED / "creator_posts.csv"
            new = not path.exists()
            with open(path, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["ts", "player_id", "name", "url"])
                w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), p["player_id"], p["name"], link])
            st.success("Recorded. The impact dashboard counts creator uptake from these links.")
    path = DERIVED / "creator_posts.csv"
    if path.exists():
        st.subheader("Attributed posts")
        st.dataframe(pd.read_csv(path), width="stretch", hide_index=True)
