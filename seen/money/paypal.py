"""PayPal gateway: checkout orders, invoices and payouts on the PayPal sandbox.

Orders and invoices are executed by PayPal's Agent Toolkit tool handlers (`create_order`, `get_order_details`,
`pay_order`, `create_invoice`, `send_invoice`, `get_invoice` — vendor/paypal_agent_toolkit), so the Sponsor Desk agent
uses exactly the tools PayPal publishes for agents. Payouts use the Payouts REST API directly, through the toolkit's
HTTP client, because the toolkit has no payouts tool.

Credentials: PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in the environment (on Streamlit Community Cloud they come
from st.secrets; app/common.py copies them into os.environ). PAYPAL_ENV defaults to "sandbox"; nothing in SEEN has
been run against the live endpoint. Without credentials `gateway()` returns None, or a FakeGateway when
SEEN_PAYPAL_FAKE=1 (development and tests: every "payment" is simulated and labelled so).
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import uuid
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SANDBOX_CHECKOUT = "https://www.sandbox.paypal.com/checkoutnow?token="


@dataclass
class OrderResult:
    order_id: str
    status: str
    approve_url: str
    raw: dict = field(default_factory=dict)


@dataclass
class CaptureResult:
    order_id: str
    status: str
    amount: float
    currency: str
    capture_id: str
    payer_email: str
    payer_name: str
    raw: dict = field(default_factory=dict)


@dataclass
class InvoiceResult:
    invoice_id: str
    status: str
    view_url: str
    raw: dict = field(default_factory=dict)


@dataclass
class PayoutResult:
    batch_id: str
    status: str
    items: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _order_links(raw: dict) -> str:
    for link in raw.get("links", []) or []:
        if link.get("rel") in ("payer-action", "approve"):
            return link.get("href", "")
    return ""


class PayPalGateway:
    """Real calls to the PayPal REST API (sandbox unless PAYPAL_ENV=live)."""

    name = "PayPal sandbox"
    simulated = False

    def __init__(self, client_id: str, secret: str, sandbox: bool = True):
        from paypal_agent_toolkit.shared.api import PayPalAPI
        from paypal_agent_toolkit.shared.configuration import Context

        self.sandbox = sandbox
        self.name = "PayPal sandbox" if sandbox else "PayPal live"
        self.api = PayPalAPI(client_id=client_id, secret=secret, context=Context(sandbox=sandbox, source="SEEN"))
        self.client = self.api._paypal_client

    # -- toolkit tools -------------------------------------------------------------------------------------------
    def tool(self, method: str, params: dict) -> dict:
        """Run one PayPal Agent Toolkit tool by its published method name; returns the parsed JSON result."""
        out = self.api.run(method, params)
        return json.loads(out) if isinstance(out, str) else out

    def create_order(self, items: list[dict], return_url: str, cancel_url: str, notes: str | None = None) -> OrderResult:
        """items: [{name, description, item_cost, quantity}] in USD (the toolkit's order tool is USD-only)."""
        raw = self.tool("create_order", {
            "currency_code": "USD",
            "items": [{"name": it["name"][:127], "description": (it.get("description") or "")[:127],
                       "item_cost": round(float(it["item_cost"]), 2), "item_total": round(float(it["item_cost"]) * int(it.get("quantity", 1)), 2),
                       "quantity": int(it.get("quantity", 1)), "tax_percent": 0} for it in items],
            "notes": notes, "return_url": return_url, "cancel_url": cancel_url,
        })
        return OrderResult(order_id=raw.get("id", ""), status=raw.get("status", ""), approve_url=_order_links(raw), raw=raw)

    def get_order(self, order_id: str) -> dict:
        return self.tool("get_order_details", {"order_id": order_id}).get("raw", {})

    def capture_order(self, order_id: str) -> CaptureResult:
        res = self.tool("pay_order", {"order_id": order_id})
        raw = res.get("raw", {}) or {}
        cap = ((raw.get("purchase_units") or [{}])[0].get("payments", {}).get("captures") or [{}])[0]
        if not cap.get("amount"):   # a minimal capture response carries only id/status/links: read the full order
            full = self.get_order(order_id)
            if full:
                raw = full
                cap = ((raw.get("purchase_units") or [{}])[0].get("payments", {}).get("captures") or [{}])[0]
        payer = raw.get("payer", {}) or {}
        name = payer.get("name", {}) or {}
        return CaptureResult(order_id=order_id, status=raw.get("status", res.get("status", "")),
                             amount=float(cap.get("amount", {}).get("value", 0) or 0), currency=cap.get("amount", {}).get("currency_code", "USD"),
                             capture_id=cap.get("id", ""), payer_email=payer.get("email_address", ""),
                             payer_name=" ".join(x for x in (name.get("given_name"), name.get("surname")) if x), raw=raw)

    def create_invoice(self, recipient_email: str, business_name: str, items: list[dict], note: str, reference: str) -> InvoiceResult:
        raw = self.tool("create_invoice", {
            "currency_code": "USD", "reference": reference[:120], "note": note[:4000],
            "invoicer_business_name": "SEEN — The Unseen XI",
            "primary_recipients": [{"billing_info": {"business_name": business_name[:300], "email_address": recipient_email}}],
            "items": [{"name": it["name"][:200], "description": (it.get("description") or "")[:1000], "quantity": str(int(it.get("quantity", 1))),
                       "unit_amount": {"currency_code": "USD", "value": f"{float(it['item_cost']):.2f}"}, "unit_of_measure": "QUANTITY"} for it in items],
        })
        inv_id = raw.get("id") or (raw.get("href", "").rsplit("/", 1)[-1] if raw.get("href") else "")
        sent = self.tool("send_invoice", {"invoice_id": inv_id, "send_to_recipient": True}) if inv_id else {}
        detail = self.get_invoice(inv_id) if inv_id else {}
        return InvoiceResult(invoice_id=inv_id, status=detail.get("status", raw.get("status", "DRAFT")),
                             view_url=detail.get("view_url", ""), raw={"create": raw, "send": sent, "detail": detail.get("raw", {})})

    def get_invoice(self, invoice_id: str) -> dict:
        raw = self.tool("get_invoice", {"invoice_id": invoice_id})
        meta = (raw.get("detail") or {}).get("metadata") or {}
        total = ((raw.get("amount") or {}).get("value"))
        return {"id": raw.get("id", invoice_id), "status": raw.get("status", ""), "view_url": meta.get("recipient_view_url") or meta.get("invoicer_view_url", ""),
                "total": float(total) if total else None, "raw": raw}

    # -- payouts (REST) ---------------------------------------------------------------------------------------------
    def create_payout(self, items: list[dict], subject: str, batch_id: str | None = None) -> PayoutResult:
        """items: [{receiver (email), amount, note, sender_item_id}] in USD."""
        batch_id = batch_id or f"seen-{uuid.uuid4().hex[:12]}"
        payload = {
            "sender_batch_header": {"sender_batch_id": batch_id, "email_subject": subject[:255], "email_message": "SEEN — share of a verified story's sponsorship"},
            "items": [{"recipient_type": "EMAIL", "receiver": it["receiver"], "note": (it.get("note") or "")[:4000],
                       "sender_item_id": it.get("sender_item_id", f"{batch_id}-{i}"),
                       "amount": {"value": f"{float(it['amount']):.2f}", "currency": "USD"}} for i, it in enumerate(items)],
        }
        raw = self.client.post("/v1/payments/payouts", payload)
        head = raw.get("batch_header", {}) or {}
        return PayoutResult(batch_id=head.get("payout_batch_id", ""), status=head.get("batch_status", ""), items=[], raw=raw)

    def get_payout(self, batch_id: str) -> PayoutResult:
        raw = self.client.get(f"/v1/payments/payouts/{batch_id}")
        head = raw.get("batch_header", {}) or {}
        items = [{"receiver": (it.get("payout_item") or {}).get("receiver"), "status": it.get("transaction_status"),
                  "amount": (it.get("payout_item") or {}).get("amount", {}).get("value"), "transaction_id": it.get("transaction_id", "")}
                 for it in raw.get("items", []) or []]
        return PayoutResult(batch_id=batch_id, status=head.get("batch_status", ""), items=items, raw=raw)


class FakeGateway:
    """In-memory stand-in with the same surface: deterministic ids, instant captures. Used by tests and by
    SEEN_PAYPAL_FAKE=1; every record it produces is labelled simulated."""

    name = "simulated PayPal (no credentials)"
    simulated = True

    def __init__(self):
        self._n = itertools.count(1)
        self.orders: dict[str, dict] = {}
        self.invoices: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def tool(self, method: str, params: dict) -> dict:   # kept for symmetry with the real gateway
        self.calls.append((method, params))
        return {"method": method, "simulated": True}

    def create_order(self, items, return_url, cancel_url, notes=None) -> OrderResult:
        oid = f"SIM-ORDER-{next(self._n):04d}"
        total = round(sum(float(i["item_cost"]) * int(i.get("quantity", 1)) for i in items), 2)
        self.orders[oid] = {"items": items, "total": total, "status": "PAYER_ACTION_REQUIRED", "return_url": return_url}
        self.calls.append(("create_order", {"items": items, "return_url": return_url}))
        sep = "&" if "?" in return_url else "?"
        return OrderResult(order_id=oid, status="PAYER_ACTION_REQUIRED", approve_url=f"{return_url}{sep}token={oid}&PayerID=SIMULATED", raw={"simulated": True})

    def get_order(self, order_id: str) -> dict:
        return dict(self.orders.get(order_id, {}), id=order_id)

    def capture_order(self, order_id: str) -> CaptureResult:
        o = self.orders.get(order_id)
        if not o:
            raise ValueError(f"unknown order {order_id}")
        o["status"] = "COMPLETED"
        self.calls.append(("pay_order", {"order_id": order_id}))
        return CaptureResult(order_id=order_id, status="COMPLETED", amount=o["total"], currency="USD", capture_id=f"SIM-CAP-{order_id[-4:]}",
                             payer_email="buyer@simulated.example", payer_name="Simulated Buyer", raw={"simulated": True})

    def create_invoice(self, recipient_email, business_name, items, note, reference) -> InvoiceResult:
        iid = f"SIM-INV-{next(self._n):04d}"
        total = round(sum(float(i["item_cost"]) * int(i.get("quantity", 1)) for i in items), 2)
        self.invoices[iid] = {"status": "SENT", "total": total, "recipient": recipient_email}
        self.calls.append(("create_invoice", {"recipient_email": recipient_email, "items": items}))
        return InvoiceResult(invoice_id=iid, status="SENT", view_url=f"https://www.sandbox.paypal.com/invoice/p/#{iid}", raw={"simulated": True})

    def get_invoice(self, invoice_id: str) -> dict:
        inv = self.invoices.get(invoice_id, {})
        return {"id": invoice_id, "status": inv.get("status", "UNKNOWN"), "view_url": f"https://www.sandbox.paypal.com/invoice/p/#{invoice_id}", "total": inv.get("total"), "raw": {}}

    def mark_invoice_paid(self, invoice_id: str) -> None:
        self.invoices[invoice_id]["status"] = "PAID"

    def create_payout(self, items, subject, batch_id=None) -> PayoutResult:
        bid = batch_id or f"SIM-BATCH-{next(self._n):04d}"
        self.payouts[bid] = {"items": [dict(it, status="SUCCESS") for it in items]}
        self.calls.append(("create_payout", {"items": items}))
        return PayoutResult(batch_id=bid, status="SUCCESS", items=self.payouts[bid]["items"], raw={"simulated": True})

    def get_payout(self, batch_id: str) -> PayoutResult:
        return PayoutResult(batch_id=batch_id, status="SUCCESS", items=self.payouts.get(batch_id, {}).get("items", []))


def gateway():
    """The configured gateway: real sandbox/live credentials → PayPalGateway; SEEN_PAYPAL_FAKE=1 → FakeGateway; else None."""
    cid, sec = os.environ.get("PAYPAL_CLIENT_ID", "").strip(), os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
    if cid and sec:
        return PayPalGateway(cid, sec, sandbox=os.environ.get("PAYPAL_ENV", "sandbox").strip().lower() != "live")
    if os.environ.get("SEEN_PAYPAL_FAKE", "").strip() in ("1", "true", "yes"):
        return FakeGateway()
    return None
