"""Streamlit glue for the money layer: the PayPal return leg (capture → ledger → "presented by" → payouts), fan tips,
and the small status bits the pages share. The agent half lives in seen/money/desk.py."""
from __future__ import annotations

import os
import uuid

import streamlit as st

from common import CFG, DERIVED

from seen.money import ledger
from seen.money.packages import policy, tip_lines
from seen.money.paypal import gateway as _gateway

PAGE_PATHS = {"desk": "Sponsor_Desk", "feed": "Fan_Feed", "ledger": "Money_Ledger"}


def usd(x) -> str:
    """Money for st.markdown: the dollar sign is escaped so two amounts in one line are not read as LaTeX."""
    return f"\\${float(x):,.2f}"


@st.cache_resource(show_spinner=False)
def gateway():
    return _gateway()


def app_url() -> str:
    url = os.environ.get("SEEN_APP_URL", "").strip() or str((CFG.get("money") or {}).get("app_url") or "http://localhost:8501")
    return url.rstrip("/")


def page_url(page: str, **params) -> str:
    base = f"{app_url()}/{PAGE_PATHS[page]}"
    if params:
        base += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return base


def payees() -> dict:
    m = CFG.get("money") or {}
    p = dict(m.get("payees") or {})
    p["athlete_fund"] = os.environ.get("SEEN_PAYEE_ATHLETE_FUND", "").strip() or p.get("athlete_fund", "")
    p["creator"] = os.environ.get("SEEN_PAYEE_CREATOR", "").strip() or p.get("creator", "")
    return p


def gateway_caption() -> str:
    gw = gateway()
    if gw is None:
        return ("PayPal is **not configured**: add `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` (sandbox app) to `.streamlit/secrets.toml` "
                "or the environment — or set `SEEN_PAYPAL_FAKE=1` to run the desk with simulated payments.")
    pay = payees()
    who = ", ".join(f"{k.replace('_', ' ')} → `{v}`" for k, v in pay.items() if v) or "no payee accounts configured (payouts are skipped)"
    return f"Payments: **{gw.name}** · payouts: {who} · return URL: `{app_url()}`"


# -- settlement --------------------------------------------------------------------------------------------------------
def settle(ref: str, kind: str, capture) -> dict:
    """After PayPal confirms the money: mark the ledger rows paid, register the 'presented by' tags, pay the shares out.
    kind: 'sponsorship' | 'tip' | 'invoice'. capture: CaptureResult or a dict with amount/payer fields."""
    gw = gateway()
    sim = bool(getattr(gw, "simulated", False))
    df = ledger.load(DERIVED)
    rows = df[(df.ref == ref) & (df.kind == kind)]
    if rows.empty:
        return {"error": f"no ledger rows for {kind} {ref}"}
    payer_email = getattr(capture, "payer_email", None) or (capture.get("payer_email") if isinstance(capture, dict) else "") or ""
    payer_name = getattr(capture, "payer_name", None) or (capture.get("payer_name") if isinstance(capture, dict) else "") or ""
    status = "PAID" if kind == "invoice" else "COMPLETED"
    fields = {"status": status}
    if payer_email:
        fields["payer_email"] = payer_email
    if kind == "tip" and payer_name:
        fields["payer"] = payer_name
    ledger.update(DERIVED, ref, kind, **fields)
    sponsor = rows.iloc[0].payer or payer_name
    if kind in ("sponsorship", "invoice"):
        for _, r in rows.iterrows():
            ledger.add_sponsorship(DERIVED, r.player_id, sponsor, [l for l in str(r.languages).split("+") if l], int(r.weeks or 1), ref, simulated=sim)
    out = {"status": status, "amount": round(float(rows.amount.sum()), 2), "athletes": rows.athlete.tolist(), "sponsor": sponsor, "payout": None}
    out["payout"] = pay_shares(ref, kind, rows)
    return out


def pay_shares(ref: str, kind: str, rows) -> dict | None:
    """One Payouts batch per settled payment: the athlete fund's share and the creator's share. SEEN's share stays in
    the merchant account. Skipped (and said so in the ledger) when no payee accounts are configured."""
    gw = gateway()
    pay = payees()
    a, c = round(float(rows.split_athlete.sum()), 2), round(float(rows.split_creator.sum()), 2)
    items = []
    if pay.get("athlete_fund") and a >= 0.01:
        items.append({"receiver": pay["athlete_fund"], "amount": a, "note": f"Athlete fund share of SEEN {kind} {ref}", "sender_item_id": f"{ref}-athlete"})
    if pay.get("creator") and c >= 0.01:
        items.append({"receiver": pay["creator"], "amount": c, "note": f"Creator share of SEEN {kind} {ref}", "sender_item_id": f"{ref}-creator"})
    sim = bool(getattr(gw, "simulated", False))
    if not items or gw is None:
        ledger.update(DERIVED, ref, kind, payout_status="SKIPPED (no payee accounts)")
        return {"status": "SKIPPED", "items": [], "batch_id": ""}
    try:
        res = gw.create_payout(items, subject=f"SEEN — your share of a verified story ({ref})")
    except Exception as exc:
        ledger.update(DERIVED, ref, kind, payout_status=f"FAILED: {str(exc)[:80]}")
        return {"status": "FAILED", "error": str(exc)[:300], "items": items, "batch_id": ""}
    ledger.update(DERIVED, ref, kind, payout_batch=res.batch_id, payout_status=res.status or "PENDING")
    athletes = ", ".join(dict.fromkeys(rows.athlete.tolist()))
    for it in items:
        who = "athlete_fund" if it["sender_item_id"].endswith("-athlete") else "creator"
        ledger.record(DERIVED, kind="payout", ref=res.batch_id, status=res.status or "PENDING", payer="SEEN (merchant account)", payer_email=it["receiver"],
                      player_id=rows.iloc[0].player_id if len(rows) == 1 else "", athlete=athletes, team=rows.iloc[0].team if len(rows) == 1 else "",
                      item=f"{who.replace('_', ' ')} share of {kind} {ref}", amount=it["amount"], currency="USD", payout_batch=res.batch_id,
                      payout_status=res.status or "PENDING", simulated=sim, note=it["note"])
    return {"status": res.status, "batch_id": res.batch_id, "items": items}


FINAL_PAYOUT = {"SUCCESS", "DENIED", "FAILED", "RETURNED", "CANCELED", "BLOCKED", "REFUNDED", "REVERSED"}


def refresh_payouts() -> int:
    """Ask PayPal for the status of every payout batch that is not final yet. Returns the number of rows updated."""
    gw = gateway()
    if gw is None:
        return 0
    df = ledger.load(DERIVED)
    open_batches = sorted(set(df[(df.kind == "payout") & ~df.status.isin(FINAL_PAYOUT)].ref))
    n = 0
    for batch in open_batches:
        try:
            res = gw.get_payout(batch)
        except Exception:
            continue

        def apply(d, batch=batch, res=res):
            nonlocal n
            for it in res.items or []:
                mask = (d.ref == batch) & (d.kind == "payout") & (d.payer_email == (it.get("receiver") or ""))
                if it.get("status") and mask.any():
                    d.loc[mask, "status"] = it["status"]
                    n += int(mask.sum())
            if res.status:
                d.loc[(d.ref == batch) & (d.kind == "payout"), "payout_status"] = res.status
                d.loc[d.payout_batch == batch, "payout_status"] = res.status

        ledger.edit(DERIVED, apply)
    return n


# -- the return leg ----------------------------------------------------------------------------------------------------
def settle_order(token: str, kind: str) -> dict | None:
    """Capture an approved PayPal order (idempotent per session) and settle it. kind: 'sponsorship' | 'tip'."""
    gw = gateway()
    if gw is None:
        st.error("PayPal returned a payment, but PayPal is not configured on this server.")
        return None
    key = f"settled_{token}"
    if key in st.session_state:
        return st.session_state[key]
    with st.spinner("Confirming the payment with PayPal…"):
        try:
            cap = gw.capture_order(token)
        except Exception as exc:
            msg = str(exc)
            if "ORDER_ALREADY_CAPTURED" in msg or "422" in msg:
                st.info("This order was already captured; showing its ledger state.")
                cap = {"payer_email": "", "payer_name": ""}
            else:
                st.error(f"PayPal did not confirm the payment: {msg[:300]}")
                return None
        receipt = settle(token, kind, cap)
        receipt["ref"] = token
        receipt["kind"] = kind
        st.session_state[key] = receipt
    return receipt


def handle_return() -> dict | None:
    """Called at the top of a page PayPal may redirect back to. Reads ?paid=<kind>&token=<order id>, captures the
    order, settles it, and shows the receipt. Returns the receipt (or None when this load is not a return)."""
    qp = st.query_params
    token, paid = qp.get("token"), qp.get("paid")
    if qp.get("cancelled"):
        qp.clear()
        st.info("Payment cancelled in PayPal — nothing was charged and nothing was published.")
        return None
    if not token or paid not in ("sponsor", "tip"):
        return None
    receipt = settle_order(token, "sponsorship" if paid == "sponsor" else "tip")
    qp.clear()
    if receipt:
        show_receipt(receipt)
    return receipt


def show_receipt(r: dict) -> None:
    if r.get("error"):
        st.warning(r["error"])
        return
    sim = bool(getattr(gateway(), "simulated", False))
    tag = " (simulated — no PayPal credentials)" if sim else " (PayPal sandbox — test money)"
    st.success(f"**Paid{tag}:** {usd(r['amount'])} · {r['kind']} `{r['ref']}` · {', '.join(dict.fromkeys(r['athletes']))}")
    p = r.get("payout") or {}
    if p.get("status") in ("SUCCESS", "PENDING", "PROCESSING"):
        shares = " · ".join(f"{usd(it['amount'])} → `{it['receiver']}`" for it in p.get("items", []))
        st.info(f"**Payout batch** `{p.get('batch_id')}` {p['status']}: {shares}")
    elif p.get("status") == "SKIPPED":
        st.caption("Shares were not paid out: no payee accounts configured (money.payees in config.yaml, or SEEN_PAYEE_* env).")
    elif p.get("status") == "FAILED":
        st.warning(f"Payout failed: {p.get('error', '')}")


# -- fan tips ------------------------------------------------------------------------------------------------------------
def tip_control(athlete: dict, language: str, fan_id: str, key: str) -> None:
    """A 'Tip her story' button on a fan-feed card: creates the PayPal order when clicked and shows the approval link."""
    gw = gateway()
    pol = policy(CFG)
    label = f"Tip ${pol['tip_amount']:.0f}"
    if gw is None:
        st.button(label, key=key, disabled=True, help="PayPal is not configured")
        return
    state = f"tip_{athlete['player_id']}"
    if st.button(label, key=key, help=f"${pol['tip_amount']:.2f} via PayPal (sandbox); 70% to the athlete fund, 20% to the creator"):
        pkg = tip_lines(athlete, CFG, language)
        line = pkg["lines"][0]
        try:
            res = gw.create_order([{"name": line["item_name"], "description": line["description"], "item_cost": line["amount_usd"], "quantity": 1}],
                                  page_url("feed", paid="tip"), page_url("feed", cancelled="tip"), notes=f"Fan tip {fan_id}")
        except Exception as exc:
            st.error(f"PayPal could not create the tip: {str(exc)[:200]}")
            return
        sp = pkg["split"]
        ledger.record(DERIVED, kind="tip", ref=res.order_id, status=res.status or "CREATED", payer=fan_id, player_id=athlete["player_id"], athlete=athlete["name"],
                      team=athlete.get("team", ""), languages=[language], weeks=0, item=line["item_name"], amount=line["amount_usd"], currency="USD",
                      split_athlete=sp["athlete_fund"], split_creator=sp["creator"], split_seen=sp["seen"], simulated=bool(getattr(gw, "simulated", False)), note="fan tip")
        st.session_state[state] = res.approve_url
    if st.session_state.get(state):
        st.link_button("Pay the tip in PayPal →", st.session_state[state], type="primary")


def new_fan_id() -> str:
    return f"fan-{uuid.uuid4().hex[:8]}"
