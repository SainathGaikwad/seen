"""S4 — Story kit: one verified event, eight formats, with the claim checker in front of publication."""
import json

import streamlit as st

from common import data_banner, inject_css, load_csv, load_kit, require_run, save_kit

from seen import llm
from seen.stories import claim_check
from seen.stories.compiler import FORMATS, GUIDANCE_MARKER, REWRITE_FORMATS, rewrite_format, run_checks

st.set_page_config(page_title="SEEN — Story kit", page_icon="🏏", layout="wide")
inject_css()
st.title("Story kit")
data_banner()

LABELS = {"video_script": "60-second video script", "social_posts": "Social posts", "article": "Article", "infographic": "Infographic (spec)",
          "creator_brief": "Creator brief", "commentator_note": "Commentator note", "quiz": "Fan quiz", "sponsor_hook": "Sponsor hook"}

if require_run():
    xi = load_csv("unseen_xi.csv")
    if xi.empty:
        st.stop()
    names = xi["name"].tolist()
    pre = st.session_state.get("selected_player")
    default = xi[xi.player_id == pre]["name"].iloc[0] if pre in set(xi.player_id) else names[0]
    pick = st.selectbox("Athlete (Unseen XI)", names, index=names.index(default))
    pid = xi[xi.name == pick].iloc[0].player_id
    st.session_state["selected_player"] = pid
    kit = load_kit(pid)
    if not kit:
        st.warning("No kit for this athlete yet.")
        st.stop()

    st.markdown(f"**{kit['headline']}**  ·  pattern `{kit['pattern']}`  ·  generated in `{kit['mode']}` mode")
    passed = sum(1 for v in kit["checks"].values() if v["passed"])
    st.progress(passed / len(kit["checks"]), text=f"Claim checker: {passed}/{len(kit['checks'])} formats verified")

    tabs = st.tabs([LABELS[f] for f in FORMATS])
    for tab, fmt in zip(tabs, FORMATS):
        with tab:
            text = kit["formats"][fmt]
            body, _, guidance = text.partition(GUIDANCE_MARKER)
            if fmt in ("infographic", "quiz"):
                st.code(body, language="json")
            else:
                # the key carries a revision counter: a model rewrite or a revert changes it, so the box shows the new text
                rev = int(kit.get("text_rev", 0))
                edited = st.text_area("Edit (every number must still match a fact)", body, height=260, key=f"ta_{pid}_{fmt}_{rev}")
                if guidance:
                    st.caption("Guidance (not checked as claims): " + guidance.replace("\n", " · "))
                cols = st.columns([1, 1, 1.4, 2.6])
                if cols[0].button("Re-check", key=f"chk_{pid}_{fmt}"):
                    kit.setdefault("generated", {}).setdefault(fmt, text)   # keep the generated version so an edit can be undone
                    kit["formats"][fmt] = edited + (GUIDANCE_MARKER + guidance if guidance else "")
                    kit["checks"] = run_checks(kit)
                    save_kit(kit)
                    st.rerun()
                if cols[1].button("Approve", key=f"appr_{pid}_{fmt}", disabled=not kit["checks"][fmt]["passed"]):
                    kit.setdefault("approved", {})[fmt] = True
                    save_kit(kit)
                    st.success("Approved")
                original = (kit.get("generated") or {}).get(fmt)
                if original and original != text and cols[2].button("Revert edits", key=f"rev_{pid}_{fmt}", help="Restore the generated, verified text"):
                    kit["formats"][fmt] = original
                    kit["text_rev"] = rev + 1
                    kit["checks"] = run_checks(kit)
                    save_kit(kit)
                    st.rerun()
                if fmt in REWRITE_FORMATS:
                    # live model call: a fresh draft from the same fact bundle, accepted only if the claim checker passes
                    label = llm.model_label()
                    with cols[3].popover("Rewrite with the model", disabled=not llm.available(),
                                         help=f"Asks {label} for a new draft; every number is re-verified before it replaces the text"):
                        st.caption(f"Model: {label}. Facts and citations are locked; only the prose changes.")
                        angle = st.text_input("Angle (optional)", key=f"angle_{pid}_{fmt}",
                                              placeholder="e.g. for a first-time fan in Lahore · playful · for a commentator")
                        if st.button("Generate and verify", key=f"rw_{pid}_{fmt}", type="primary"):
                            with st.spinner(f"Asking {label}…"):
                                out = rewrite_format(kit, fmt, angle)
                            if out["error"]:
                                st.error(f"Model call failed: {out['error']}")
                            elif out["accepted"]:
                                save_kit(kit)
                                st.session_state[f"rw_msg_{pid}_{fmt}"] = (f"New draft from {label} passed the claim checker ({out['check']['summary']}); "
                                                           f"{int(round(out['changed'] * 100))}% of the words changed.")
                                st.rerun()
                            else:
                                save_kit(kit)
                                st.session_state[f"rw_msg_{pid}_{fmt}"] = ("BLOCKED: the draft from the model failed the claim checker — "
                                                                           f"{out['check']['summary']}. The verified text is unchanged; the draft is shown below.")
                                st.rerun()
                    msg = st.session_state.pop(f"rw_msg_{pid}_{fmt}", None)
                    if msg:
                        (st.error if msg.startswith("BLOCKED") else st.success)(msg)
                    last = [r for r in kit.get("rewrites", []) if r.get("format") == fmt]
                    if last:
                        r = last[-1]
                        st.caption(f"Last model rewrite: {r.get('model', '?')} · angle: {r.get('angle') or '—'} · {int(round(float(r.get('changed', 0)) * 100))}% of words changed · {str(r.get('at', ''))[:16].replace('T', ' ')} UTC · "
                                   f"{len(last)} accepted rewrite{'s' if len(last) != 1 else ''} for this format")
            ch = kit["checks"][fmt]
            st.markdown(f"<span class='{'ok' if ch['passed'] else 'bad'}'><b>{'PASS' if ch['passed'] else 'BLOCKED'}</b> — {ch['summary']}</span>", unsafe_allow_html=True)
            bad = [c for c in ch["claims"] if c["status"] == "unmatched"]
            if bad:
                st.error("Unverifiable numbers: " + ", ".join(sorted({c['text'] for c in bad})) + " — not in any fact. Fix the text or add a sourced fact.")
            if ch["banned"]:
                st.error("Banned topics: " + ", ".join(ch["banned"]))
            if ch.get("unknown_names"):
                st.caption("Names not in the fact bundle (warning): " + ", ".join(ch["unknown_names"]))
            if kit.get("rejected", {}).get(fmt):
                with st.expander("LLM draft rejected by the claim checker (kept the template instead)"):
                    st.write(kit["rejected"][fmt]["reason"])
                    st.code(kit["rejected"][fmt]["text"])

    with st.expander(f"Fact bundle ({len(kit['facts'])} facts)"):
        for f in kit["facts"]:
            st.markdown(f"<div class='fact'>[{f['id']}] {f['text']} — <i>{f['source']}</i></div>", unsafe_allow_html=True)

    st.divider()
    st.subheader("Try the checker: paste a sentence with a made-up number")
    demo = st.text_input("Sentence", f"{kit['name']} scored 97 runs and took 9 wickets in the tournament.")
    res = claim_check.check(demo, kit["facts"], [kit["name"], kit["team"]])
    st.markdown(f"<span class='{'ok' if res.passed else 'bad'}'><b>{'PASS' if res.passed else 'BLOCKED'}</b> — {res.summary()}</span>", unsafe_allow_html=True)
    if res.claims:
        import pandas as pd
        st.dataframe(pd.DataFrame([{"number in the sentence": c["text"], "status": c["status"], "matched fact": c.get("fact") or "—"} for c in res.claims]),
                     width="stretch", hide_index=True)
