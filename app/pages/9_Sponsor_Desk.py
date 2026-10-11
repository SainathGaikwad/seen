"""S10 — Sponsor Desk: a brief in, a priced package of verified athlete stories and a PayPal payment request out.
The agent plans within policy, the sponsor pays in PayPal, and only then are the athlete fund and the creator paid."""
import pandas as pd
import streamlit as st

from common import CFG, DERIVED, data_banner, inject_css, load_csv, require_run
from money_ui import gateway, gateway_caption, handle_return, page_url, settle, settle_order, show_receipt, usd

from seen import llm
from seen.money import ledger
from seen.money.desk import run_desk
from seen.money.packages import catalogue, policy

st.set_page_config(page_title="SEEN — Sponsor Desk", page_icon="🏏", layout="wide")
inject_css()
st.title("Sponsor Desk")
data_banner()
st.caption(gateway_caption())

handle_return()

PAY_LABELS = {"checkout": "PayPal checkout (approve now)", "invoice": "PayPal invoice (sent to the sponsor's email)", "auto": "Let the desk decide"}

if require_run():
    xi = load_csv("unseen_xi.csv")
    cat = catalogue(xi, DERIVED, CFG)
    pol = policy(CFG)
    if not cat:
        st.warning("No claim-checked story kits to sell yet — run the pipeline and the claim checker first.")
        st.stop()

    left, right = st.columns([5, 4])
    with left:
        st.subheader("1 · The brief")
        c1, c2 = st.columns(2)
        sponsor = c1.text_input("Sponsor / brand", st.session_state.get("desk_sponsor", "Mumbai Sports Nutrition"))
        email = c2.text_input("Sponsor email (PayPal sandbox account — needed for invoices)", st.session_state.get("desk_email", ""))
        c3, c4 = st.columns(2)
        budget = c3.number_input("Budget (USD)", min_value=20.0, max_value=5000.0, value=float(st.session_state.get("desk_budget", 300.0)), step=10.0)
        pay_method = c4.radio("Payment", list(PAY_LABELS), index=0, horizontal=True, format_func=PAY_LABELS.get)
        brief = st.text_area("What do you want to support?", st.session_state.get("desk_brief",
                             "We want Hindi-speaking fans to meet bowlers from outside India, England and Australia. Two athletes, one week each, English and Hindi."),
                             height=110)
        st.caption(f"The desk is **{llm.model_label()}**; without a model key it runs a rules planner over the same tools. "
                   f"Policy: 1–{pol['max_athletes']} athletes, verified languages only, the budget is a hard cap, split "
                   f"{round(pol['split']['athlete_fund']*100)}/{round(pol['split']['creator']*100)}/{round(pol['split']['seen']*100)} "
                   f"(athlete fund / creator / SEEN), invoices at ≥ {usd(pol['invoice_threshold'])}.")
        go = st.button("Ask the Sponsor Desk", type="primary", disabled=gateway() is None)
        if go:
            st.session_state.update({"desk_sponsor": sponsor, "desk_email": email, "desk_budget": budget, "desk_brief": brief})
            with st.spinner("The desk is reading the catalogue, pricing and raising the payment…"):
                res = run_desk(brief, budget, {"name": sponsor.strip() or "Sponsor", "email": email.strip()}, pay_method, CFG, DERIVED, xi, gateway(),
                               page_url("desk", paid="sponsor"), page_url("desk", cancelled="sponsor"))
            st.session_state["desk_result"] = res

    with right:
        st.subheader("On sale this week")
        tbl = pd.DataFrame([{"Athlete": c["name"], "Team": c["team"], "Role": c["role"], "Impact #": c["impact_rank"], "Attention #": c["attention_rank"],
                             "Gap z": c["gap_z"], "Languages": "+".join(l.upper() for l in c["languages"]), "Week $": c["week_price_usd"]} for c in cat])
        st.dataframe(tbl, hide_index=True, use_container_width=True, height=min(420, 38 + 35 * len(tbl)))
        st.caption("Price = base × (1 + 0.35 × gap z) per language-week + $25 per extra language: the more under-seen she is, the more her story is worth. "
                   "Only kits that passed the claim checker in every format are listed.")

    res = st.session_state.get("desk_result")
    if res:
        st.subheader("2 · What the desk did")
        st.caption(f"Planner: **{res.mode}** · {len(res.steps)} tool calls")
        for s in res.steps:
            label = f"{s['n']}. `{s['tool']}`" + (f" — {s['thought']}" if s.get("thought") else "")
            with st.expander(label, expanded=s["tool"] in ("create_order", "create_invoice")):
                a, b = st.columns([1, 2])
                a.markdown("**args**")
                a.json(s["args"], expanded=2)
                b.markdown("**result**")
                b.json(s["result"], expanded=1)
        if res.error:
            st.error(res.error)
        if res.package:
            st.subheader("3 · The package")
            lines = pd.DataFrame([{"Athlete": l["name"], "Team": l["team"], "Languages": "+".join(x.upper() for x in l["languages"]), "Weeks": l["weeks"], "USD": l["amount_usd"]} for l in res.package["lines"]])
            st.dataframe(lines, hide_index=True, use_container_width=True)
            sp = res.package["split"]
            st.markdown(f"**Total {usd(res.package['total_usd'])}** → athlete fund {usd(sp['athlete_fund'])} · creator {usd(sp['creator'])} · SEEN {usd(sp['seen'])} (paid out after PayPal confirms the payment)")
        if res.summary:
            st.markdown("> " + res.summary.replace("$", "\\$"))
        if res.payment:
            st.subheader("4 · The sponsor pays — in PayPal, not here")
            if res.payment["kind"] == "order":
                st.link_button("Approve and pay in PayPal (sandbox) →", res.payment["url"] or "#", type="primary", disabled=not res.payment["url"])
                st.caption(f"Order `{res.payment['ref']}` · status {res.payment['status']} · PayPal sends you back here and the capture, the 'presented by' tags and the payouts happen on return.")
            else:
                if res.payment["url"]:
                    st.link_button("View the invoice PayPal sent →", res.payment["url"])
                st.caption(f"Invoice `{res.payment['ref']}` · status {res.payment['status']} · sent to {st.session_state.get('desk_email', '')}.")
                if st.button("I've paid the invoice — check with PayPal"):
                    gw = gateway()
                    inv = gw.get_invoice(res.payment["ref"])
                    if inv.get("status") == "PAID":
                        r = settle(res.payment["ref"], "invoice", {"payer_email": st.session_state.get("desk_email", ""), "payer_name": st.session_state.get("desk_sponsor", "")})
                        r.update({"ref": res.payment["ref"], "kind": "invoice"})
                        show_receipt(r)
                    else:
                        st.info(f"PayPal says the invoice is **{inv.get('status') or 'unknown'}**. Pay it from the sandbox buyer account, then check again.")

    with st.expander("Returned from PayPal but nothing happened?"):
        st.caption("The return URL must point at this app (SEEN_APP_URL). Paste the `token=` value from the PayPal return address to complete the capture by hand.")
        tok = st.text_input("Order id (token)", key="manual_token")
        kind = st.radio("It was a", ["sponsorship", "tip"], horizontal=True, key="manual_kind")
        if st.button("Complete capture") and tok.strip():
            r = settle_order(tok.strip(), kind)
            if r:
                show_receipt(r)

    df = ledger.load(DERIVED)
    if len(df):
        t = ledger.totals(df)
        st.divider()
        c = st.columns(5)
        c[0].metric("Raised", f"${t['raised']:,.2f}")
        c[1].metric("Sponsorships · tips", f"{t['sponsorships']} · {t['tips']}")
        c[2].metric("To athlete fund", f"${t['to_athletes']:,.2f}")
        c[3].metric("To creators", f"${t['to_creators']:,.2f}")
        c[4].metric("Paid out", f"${t['paid_out']:,.2f}")
        st.caption(("All figures are PayPal **sandbox** test money" if not t["simulated"] else "Figures include **simulated** rows (no PayPal credentials)")
                   + " · full ledger with filters and export on the **Money ledger** page.")
