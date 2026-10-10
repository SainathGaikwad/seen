"""S3 — Story opportunity: why it matters, with evidence a journalist could check; safety gate."""
import json

import pandas as pd
import streamlit as st

from common import CFG, consent_map, data_banner, inject_css, load_csv, load_json, load_kit, require_run, set_consent

from seen.stories.localize import rank_languages

st.set_page_config(page_title="SEEN — Story opportunity", page_icon="🏏", layout="wide")
inject_css()
st.title("Story opportunity")
data_banner()

if require_run():
    gap = load_csv("gap.csv")
    cands = load_json("candidates.json", [])
    xi = load_csv("unseen_xi.csv")
    names = gap.sort_values("gap_rank")["name"].tolist()
    pre = st.session_state.get("selected_player")
    default = gap[gap.player_id == pre]["name"].iloc[0] if pre in set(gap.player_id) else (xi.iloc[0]["name"] if not xi.empty else names[0])
    pick = st.selectbox("Athlete", names, index=names.index(default) if default in names else 0)
    r = gap[gap.name == pick].iloc[0]
    st.session_state["selected_player"] = r.player_id

    mine = [c for c in cands if c["player_id"] == r.player_id]
    mine.sort(key=lambda c: -(1.0 / (1 + c["rarity_count"])))
    if not mine:
        st.info("No narrative pattern fired for this athlete. The kit (if she is in the XI) uses her tournament aggregates.")
    else:
        labels = [f"{c['pattern']} — {c['headline']}" for c in mine]
        ci = st.radio("Detected stories", range(len(labels)), format_func=lambda i: labels[i])
        c = mine[ci]
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Evidence")
            ev = pd.DataFrame([{"fact": f["id"], "statement": f["text"], "value": str(f["value"]), "source": f["source"]} for f in c["facts"]])
            st.dataframe(ev, width="stretch", hide_index=True)
            st.caption("Every statement traces to a Cricsheet match file (cricsheet:<match id>) or to a query over the graph's history.")
        with right:
            st.subheader("Why it scores")
            wts = CFG["significance"]
            rarity = 1 / (1 + c["rarity_count"])
            arc = min(1.0, 0.5 * len(set(c["arc_flags"])))
            st.dataframe(pd.DataFrame({
                "component": ["rarity", "stakes", "magnitude", "arc"],
                "input": [f"{c['rarity_count']} prior occurrences → {rarity:.2f}", f"{c['stakes']:.2f}", f"{c['magnitude']:.2f}", f"{', '.join(c['arc_flags']) or 'none'} → {arc:.2f}"],
                "weight": [wts["rarity"], wts["stakes"], wts["magnitude"], wts["arc"]],
                "contribution": [round(wts["rarity"] * rarity, 3), round(wts["stakes"] * c["stakes"], 3), round(wts["magnitude"] * c["magnitude"], 3), round(wts["arc"] * arc, 3)],
            }), width="stretch", hide_index=True)
            st.subheader("Audience fit")
            langs = rank_languages(r.to_dict(), CFG)[:5]
            st.dataframe(pd.DataFrame(langs), width="stretch", hide_index=True)

    st.subheader("Athlete-safety gate")
    cm = consent_map()
    current = cm.get(str(r.player_id), True)
    col1, col2 = st.columns([1, 2])
    with col1:
        val = st.toggle("Consent to be featured", value=current, key=f"consent_{r.player_id}")
        if val != current:
            set_consent(r.player_id, val)
            st.success("Consent updated (data/manual/consent.csv). Re-run the pipeline to apply to the XI.")
    with col2:
        risk = "standard" if r.team in CFG["big_three"] else "review market-specific abuse risk before publishing"
        st.write(f"Abuse-risk review: **{risk}**. Minors: not applicable to senior internationals; U19 events require board consent.")
        st.write("Banned topics in every kit: health or injury speculation, private life, betting, religion, appearance.")

    kit = load_kit(r.player_id)
    if kit:
        st.success(f"A kit exists for {r['name']} (pattern {kit['pattern']}, mode {kit['mode']}).")
        try:
            st.page_link("pages/3_Story_Kit.py", label="→ Open the story kit", icon="📝")
        except Exception:
            st.caption("Next: open the Story kit page.")
    else:
        st.info("Kits are generated for the Unseen XI. Run the pipeline with `--top-kits` or add her to the XI to build one.")
