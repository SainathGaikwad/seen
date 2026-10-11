"""Smoke-test the PayPal credentials without the UI: get a token, create a $1 sandbox order (never captured), and
probe whether the app may call Payouts. Reads .streamlit/secrets.toml when the variables are not in the environment.

    python scripts/paypal_check.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_secrets() -> None:
    p = ROOT / ".streamlit" / "secrets.toml"
    if not p.exists():
        return
    for m in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"', p.read_text(encoding="utf-8-sig"), re.M):
        os.environ.setdefault(m.group(1), m.group(2))


def main() -> int:
    load_secrets()
    from seen.money.paypal import gateway

    gw = gateway()
    if gw is None:
        print("no credentials: put PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .streamlit/secrets.toml (see docs/paypal_sponsor_desk.md)")
        return 2
    print(f"gateway: {gw.name}")
    app_url = os.environ.get("SEEN_APP_URL", "http://localhost:8501").rstrip("/")
    try:
        order = gw.create_order([{"name": "SEEN connectivity test", "description": "not captured", "item_cost": 1.0, "quantity": 1}],
                                f"{app_url}/Sponsor_Desk?paid=sponsor", f"{app_url}/Sponsor_Desk?cancelled=1", notes="paypal_check")
    except Exception as exc:
        print(f"FAIL: token or order creation: {str(exc)[:300]}")
        print("  → wrong client id / secret, or PAYPAL_ENV does not match the app (sandbox vs live)")
        return 1
    print(f"OK   order {order.order_id} {order.status}; approve link starts with {order.approve_url[:48]}…")
    if getattr(gw, "simulated", False):
        print("     (simulated gateway: nothing was sent to PayPal)")
        return 0
    try:
        gw.client.get("/v1/payments/payouts/BATCH-DOES-NOT-EXIST")
        print("OK   payouts endpoint reachable")
    except Exception as exc:
        msg = str(exc)
        if "404" in msg:
            print("OK   payouts endpoint reachable (404 for a made-up batch id is the expected answer)")
        elif "401" in msg or "403" in msg:
            print("WARN payouts not permitted for this app: enable 'Payouts' under the app's Features in the developer dashboard")
        else:
            print(f"WARN payouts probe: {msg[:200]}")
    pay = {k: os.environ.get(k, "") for k in ("SEEN_PAYEE_ATHLETE_FUND", "SEEN_PAYEE_CREATOR")}
    print("payees from env:", pay if any(pay.values()) else "none (config.yaml money.payees will be used)")
    print("next: streamlit run app/Home.py → Sponsor Desk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
