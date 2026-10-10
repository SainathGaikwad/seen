"""S5 — Localisation: take the story to the markets where the gap is largest."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from common import CFG, DERIVED, data_banner, inject_css, load_csv, load_kit, load_localized, require_run

from seen import llm
from seen.stories.localize import localize_kit, rank_languages

st.set_page_config(page_title="SEEN — Localisation", page_icon="🏏", layout="wide")
inject_css()
st.title("Localisation")
data_banner()

if require_run():
    xi = load_csv("unseen_xi.csv")
    gap = load_csv("gap.csv")
    if xi.empty:
        st.stop()
    names = xi["name"].tolist()
    pre = st.session_state.get("selected_player")
    default = xi[xi.player_id == pre]["name"].iloc[0] if pre in set(xi.player_id) else names[0]
    pick = st.selectbox("Athlete (Unseen XI)", names, index=names.index(default))
    row = gap[gap.name == pick].iloc[0]
    pid = row.player_id
    kit = load_kit(pid)
    if not kit:
        st.stop()

    st.subheader("Languages ranked by opportunity")
    ranked = rank_languages(row.to_dict(), CFG)
    st.dataframe(pd.DataFrame(ranked), width="stretch", hide_index=True)
    st.caption("Heuristic ranking (documented in seen/stories/localize.py): home-market languages, large cricket audiences, and languages where she has no Wikipedia article yet score higher. In pilot, replace with measured per-language response.")

    langs = [l["language"] for l in ranked if l["language"] != "en"][:6]
    lang = st.selectbox("Language", langs, format_func=lambda c: CFG["localisation"]["language_names"].get(c, c))
    lang_name = CFG["localisation"]["language_names"].get(lang, lang)
    loc = load_localized(pid, lang)
    translated = bool(loc and loc.get("checks"))          # a fallback file (no LLM, or the run's budget ran out) holds English and no checks
    if not translated or st.button("Translate now" if llm.available() else "Translate now (needs LLM key)"):
        if llm.available():
            with st.spinner("Translating with a locked cricket glossary, then re-running the claim checker…"):
                loc = localize_kit(kit, lang, lang_name, DERIVED / "localized", tts=bool(CFG["localisation"].get("tts")))
                (DERIVED / "localized" / f"{pid}_{lang}.json").write_text(json.dumps(loc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
                translated = bool(loc.get("checks"))
        if not translated:
            why = (loc or {}).get("status", "")
            if why.startswith("translation failed"):
                why = "the run's LLM budget was used up before this athlete — re-run the pipeline tomorrow (cached answers cost nothing)"
            elif not why or why.startswith("needs LLM key"):
                why = "needs an LLM key (LLM_PROVIDER in .env)"
            loc = {"status": f"not translated yet: {why}", "formats": {k: kit["formats"][k] for k in ("video_script", "social_posts", "article", "creator_brief")}, "checks": {}, "audio": None}
    if translated:
        st.success(f"Status: {loc['status']}")
    else:
        st.warning(f"Status: {loc['status']} — the English kit is shown on the right.")
    fmt = st.radio("Format", ["video_script", "social_posts", "article", "creator_brief"], horizontal=True)
    left, right = st.columns(2)
    with left:
        st.markdown("**English (approved kit)**")
        st.text_area("en", kit["formats"][fmt], height=320, key=f"en_{pid}_{fmt}", disabled=True)
    with right:
        st.markdown(f"**{lang_name}**" if translated else f"**{lang_name}** — not translated yet (English shown)")
        st.text_area(lang, loc["formats"].get(fmt, ""), height=320, key=f"loc_{pid}_{fmt}_{lang}", disabled=True)
        ch = (loc.get("checks") or {}).get(fmt)
        if ch:
            st.markdown(f"<span class='{'ok' if ch['passed'] else 'bad'}'><b>{'PASS' if ch['passed'] else 'BLOCKED'}</b> — {ch['summary']}</span>", unsafe_allow_html=True)
    if loc.get("audio") and Path(loc["audio"]).exists():
        st.audio(loc["audio"])
    else:
        st.caption("Audio: set `localisation.tts: true` in config.yaml and install gTTS for a demo voice track (production: ElevenLabs / Google / Sarvam-class TTS).")
