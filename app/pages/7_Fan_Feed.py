"""S8 — Fan discovery feed (mobile): from unknown name to follow."""
import json
import re
import uuid

import pandas as pd
import streamlit as st

from common import CFG, DERIVED, data_banner, inject_css, load_csv, load_kit, load_localized, publications, require_run, tidy_sentence

from seen.fans.feed import log_event, rank_cards
from seen.stories.claim_check import CITATION
from seen.stories.compiler import GUIDANCE_MARKER

st.set_page_config(page_title="SEEN — Fan feed", page_icon="🏏", layout="wide")
inject_css()
st.title("Fan discovery feed")
data_banner()

if require_run():
    xi = load_csv("unseen_xi.csv")
    gap = load_csv("gap.csv")
    if xi.empty:
        st.stop()
    if "fan_id" not in st.session_state:
        st.session_state["fan_id"] = f"fan-{uuid.uuid4().hex[:8]}"
    fan = st.session_state["fan_id"]
    st.session_state.setdefault("follows", set())

    side, phone = st.columns([1, 1])
    with side:
        st.subheader("Who is this fan?")
        teams = sorted(gap.team.unique().tolist())
        my_teams = st.multiselect("Teams I follow", teams, default=["India"] if "India" in teams else teams[:1])
        roles = st.multiselect("I like", ["batter", "bowler", "all-rounder"], default=["all-rounder"])
        lang_opts = ["en"] + CFG["localisation"]["languages"]
        lang = st.selectbox("Language", lang_opts, format_func=lambda c: CFG["localisation"]["language_names"].get(c, c))
        n_pub = len([p for p in publications() if "fan_feed" in p.get("channels", [])])
        only_published = st.toggle(f"Only published stories ({n_pub}) — the production rule; off shows the whole ranked XI", value=False)
        st.caption(f"Fan id {fan} · every impression, read, quiz answer and follow is logged to fan_events.csv (real events for this session).")
        st.markdown("**Following:** " + (", ".join(sorted(st.session_state["follows"])) or "nobody yet"))

    cards = rank_cards(xi, {"teams": my_teams, "roles": roles, "language": lang}, CFG)
    if only_published:
        pub_ids = {p["player_id"] for p in publications() if "fan_feed" in p.get("channels", [])}
        cards = cards[cards.player_id.isin(pub_ids)]

    with phone:
        st.markdown("**📱 Fan app preview**")
        if cards.empty:
            st.info("No published stories match. Publish one from Route & publish, or switch the toggle off.")
        for _, r in cards.head(4).iterrows():
            kit = load_kit(r.player_id)
            if not kit:
                continue
            loc = load_localized(r.player_id, lang) if lang != "en" else None
            if loc and not loc.get("checks"):
                loc = None                      # a fallback file holds English: use the kit itself
            script = (loc["formats"]["video_script"] if loc and lang != "en" else kit["formats"]["video_script"]).split(GUIDANCE_MARKER)[0]
            # the hook is the first real sentence after the opening timestamp, whatever the script's line layout
            lines = [re.sub(r"^\s*\[\d\d:\d\d-\d\d:\d\d\]\s*", "", ln).strip() for ln in script.splitlines()]
            lines = [ln for ln in lines if ln]
            hook = lines[1] if len(lines) > 1 else (lines[0] if lines else kit["headline"])
            hook = tidy_sentence(CITATION.sub("", hook))
            log_event(DERIVED, fan, r.player_id, "impression", "fan_feed", lang)
            kicker = "New to you" if r.card_reason == "new to you" else r.card_reason
            box = st.container(border=True)
            box.markdown(f'<div class="kicker">{kicker} · {r.team}</div><h3 style="margin:.1rem 0 .3rem 0">Meet {r["name"]}</h3><p>{hook}</p>', unsafe_allow_html=True)
            c1, c2, c3 = box.columns(3)
            if c1.button("Read", key=f"read_{r.player_id}"):
                log_event(DERIVED, fan, r.player_id, "read", "fan_feed", lang)
                st.session_state[f"open_{r.player_id}"] = True
            if c2.button("Follow" if r["name"] not in st.session_state["follows"] else "Following ✓", key=f"follow_{r.player_id}"):
                st.session_state["follows"].add(r["name"])
                log_event(DERIVED, fan, r.player_id, "follow", "fan_feed", lang)
                st.rerun()
            if c3.button("Share", key=f"share_{r.player_id}"):
                log_event(DERIVED, fan, r.player_id, "share", "fan_feed", lang)
                st.toast("Share link copied (demo)")
            if st.session_state.get(f"open_{r.player_id}"):
                article = (loc["formats"]["article"] if loc and lang != "en" else kit["formats"]["article"]).split(GUIDANCE_MARKER)[0]
                box.markdown(tidy_sentence(CITATION.sub("", article)))
                try:
                    quiz = json.loads(kit["formats"]["quiz"])
                except json.JSONDecodeError:
                    quiz = []
                if quiz:
                    q = quiz[0]
                    ans = box.radio(q["question"], q["options"], key=f"quiz_{r.player_id}", index=None, horizontal=True)
                    if ans is not None:
                        log_event(DERIVED, fan, r.player_id, "quiz", "fan_feed", lang)
                        box.write("✅ Correct" if ans == q["answer"] else f"❌ It was {q['answer']} [{q['fact']}]")
                box.caption("Where to watch next: fixtures and broadcaster from the rights map (pilot data).")
