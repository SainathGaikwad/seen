"""The money layer: pricing policy, the Sponsor Desk agent loop (scripted model and rules planner), settlement
bookkeeping and the PayPal tool payloads — all against the fake gateway, no network."""
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from seen.config import load_config
from seen.money import ledger
from seen.money.desk import run_desk
from seen.money.packages import PackageError, catalogue, price_package, split_amount, tip_lines
from seen.money.paypal import FakeGateway

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()


@pytest.fixture
def derived(tmp_path):
    """A copy of the real derived data (kits + localized) so the catalogue is the shipped one."""
    src = ROOT / "data" / "derived"
    dst = tmp_path / "derived"
    dst.mkdir()
    shutil.copytree(src / "kits", dst / "kits")
    shutil.copytree(src / "localized", dst / "localized")
    shutil.copy(src / "unseen_xi.csv", dst / "unseen_xi.csv")
    return dst


@pytest.fixture
def xi(derived):
    return pd.read_csv(derived / "unseen_xi.csv")


def test_catalogue_lists_only_verified_kits_with_their_languages(xi, derived):
    cat = catalogue(xi, derived, CFG)
    assert len(cat) >= 8
    hm = next(c for c in cat if c["name"] == "Hayley Matthews")
    assert set(hm["languages"]) >= {"en", "hi", "ur"}
    assert hm["week_price_usd"] > 60.0            # her gap raises the price above the base
    assert all(c["week_price_usd"] >= 60.0 for c in cat)


def test_pricing_policy_and_errors(xi, derived):
    cat = catalogue(xi, derived, CFG)
    hm = next(c for c in cat if c["name"] == "Hayley Matthews")
    pkg = price_package([{"player_id": hm["player_id"], "languages": ["en", "hi"], "weeks": 2}], cat, CFG)
    assert pkg["total_usd"] == round((hm["week_price_usd"] + 25.0) * 2, 2)
    s = pkg["split"]
    assert round(s["athlete_fund"] + s["creator"] + s["seen"], 2) == pkg["total_usd"]
    with pytest.raises(PackageError):
        price_package([{"player_id": "nobody"}], cat, CFG)
    with pytest.raises(PackageError):
        price_package([{"player_id": hm["player_id"], "languages": ["fr"]}], cat, CFG)
    with pytest.raises(PackageError):
        price_package([{"player_id": hm["player_id"], "languages": ["en"]}], cat, CFG, budget=10.0)
    with pytest.raises(PackageError):
        price_package([{"player_id": c["player_id"]} for c in cat[:5]], cat, CFG)
    assert split_amount(10.0, {"athlete_fund": 0.6, "creator": 0.3, "seen": 0.1}) == {"athlete_fund": 6.0, "creator": 3.0, "seen": 1.0}
    tip = tip_lines({"player_id": "x", "name": "X", "team": "T"}, CFG, "hi")
    assert tip["total_usd"] == 2.0 and tip["split"]["athlete_fund"] == 1.4


def test_rules_desk_raises_an_order_within_budget_and_records_it(xi, derived):
    gw = FakeGateway()
    res = run_desk("Hindi-speaking fans should meet bowlers from outside the big three; two athletes, one week.", 150.0,
                   {"name": "Test Brand", "email": ""}, "checkout", CFG, derived, xi, gw, "http://app/Sponsor_Desk?paid=sponsor", "http://app/Sponsor_Desk?cancelled=1",
                   use_model=False)
    assert res.mode.startswith("rules") and not res.error, res.error
    assert res.payment["kind"] == "order" and res.payment["ref"].startswith("SIM-ORDER")
    assert res.package["total_usd"] <= 150.0
    assert all(l["team"] not in ("India", "England", "Australia") for l in res.package["lines"])
    assert all("hi" in l["languages"] for l in res.package["lines"])
    assert [c[0] for c in gw.calls] == ["create_order"]
    df = ledger.load(derived)
    assert set(df.kind) == {"sponsorship"} and set(df.status) == {"PAYER_ACTION_REQUIRED"}
    assert round(df.amount.sum(), 2) == res.package["total_usd"]
    assert "approve_url" not in res.summary and "$" in res.summary


def test_scripted_model_desk_follows_the_tool_protocol(xi, derived):
    gw = FakeGateway()
    cat = catalogue(xi, derived, CFG)
    pid = next(c["player_id"] for c in cat if c["name"] == "Kathryn Bryce")
    script = iter([
        json.dumps({"thought": "see what is on sale", "tool": "catalogue", "args": {}}),
        json.dumps({"thought": "price Bryce in three languages", "tool": "price_package", "args": {"items": [{"player_id": pid, "languages": ["en", "hi", "ur"], "weeks": 3}]}}),
        json.dumps({"thought": "over budget: one week", "tool": "price_package", "args": {"items": [{"player_id": pid, "languages": ["en", "hi"], "weeks": 1}]}}),
        json.dumps({"thought": "raise the order", "tool": "create_order", "args": {"items": [{"player_id": pid, "languages": ["en", "hi"], "weeks": 1}], "note": "Scotland week"}}),
        json.dumps({"thought": "done", "final": {"summary": "Kathryn Bryce (Scotland) in English and Hindi for one week; approve the order in PayPal."}}),
    ])

    def fake_complete(system, user, max_tokens=0):
        assert "Sponsor Desk" in system and "history" in user
        return next(script)

    res = run_desk("Scottish all-rounders", 120.0, {"name": "Edinburgh Oats", "email": "sb-buyer@personal.example.com"}, "checkout", CFG, derived, xi, gw,
                   "http://app/Sponsor_Desk?paid=sponsor", "http://app/Sponsor_Desk?cancelled=1", complete=fake_complete, use_model=True)
    assert not res.error, res.error
    assert [s["tool"] for s in res.steps] == ["catalogue", "price_package", "price_package", "create_order"]
    assert "error" in res.steps[1]["result"]            # 3 weeks in 3 languages blew the $120 budget
    assert res.payment["kind"] == "order" and res.summary.startswith("Kathryn Bryce")
    assert res.mode == "model: scripted"


def test_invoice_path_and_settlement_bookkeeping(xi, derived):
    gw = FakeGateway()
    res = run_desk("Hayley Matthews in English and Urdu for two weeks", 2000.0, {"name": "Bridgetown Rum Co", "email": "sb-sponsor@business.example.com"}, "invoice",
                   CFG, derived, xi, gw, "http://app/x", "http://app/y", use_model=False)
    assert not res.error and res.payment["kind"] == "invoice" and res.payment["ref"].startswith("SIM-INV")
    df = ledger.load(derived)
    assert set(df.kind) == {"invoice"} and set(df.status) == {"SENT"}
    # settlement: mark paid, register the sponsor tag, pay the shares
    ledger.update(derived, res.payment["ref"], "invoice", status="PAID")
    rows = ledger.load(derived)
    for _, r in rows.iterrows():
        ledger.add_sponsorship(derived, r.player_id, r.payer, r.languages.split("+"), int(r.weeks), r.ref, simulated=True)
    hm = rows.iloc[0]
    assert ledger.presented_by(derived, hm.player_id, "ur") == "Bridgetown Rum Co"
    assert ledger.presented_by(derived, hm.player_id, "hi") is None or "hi" in hm.languages
    t = ledger.totals(rows)
    assert t["raised"] == res.package["total_usd"] and t["sponsorships"] == len(rows) and t["simulated"] is True
    by = ledger.by_athlete(rows)
    assert by.iloc[0].athlete == "Hayley Matthews" and by.iloc[0].sponsors == "Bridgetown Rum Co"


def test_fake_gateway_payout_roundtrip():
    gw = FakeGateway()
    o = gw.create_order([{"name": "Tip", "item_cost": 2.0, "quantity": 1}], "http://app/Fan_Feed?paid=tip", "http://app/Fan_Feed?cancelled=1")
    assert o.approve_url.startswith("http://app/Fan_Feed?paid=tip&token=")
    cap = gw.capture_order(o.order_id)
    assert cap.status == "COMPLETED" and cap.amount == 2.0
    p = gw.create_payout([{"receiver": "a@x", "amount": 1.4, "note": "n", "sender_item_id": "a"}, {"receiver": "c@x", "amount": 0.4, "note": "n", "sender_item_id": "c"}], "subject")
    assert p.status == "SUCCESS" and len(gw.get_payout(p.batch_id).items) == 2


def test_toolkit_order_payload_matches_paypal_shape():
    """The vendored PayPal Agent Toolkit builds the Orders v2 request we rely on (totals, items, return URL)."""
    from paypal_agent_toolkit.shared.orders.parameters import CreateOrderParameters
    from paypal_agent_toolkit.shared.orders.payload_util import parse_order_details
    params = CreateOrderParameters(currency_code="USD", items=[{"name": "Presented by: X", "item_cost": 81.0, "item_total": 81.0, "quantity": 1},
                                                              {"name": "Presented by: Y", "item_cost": 60.0, "item_total": 60.0, "quantity": 1}],
                                   return_url="https://seen-unseen-xi.streamlit.app/Sponsor_Desk?paid=sponsor", cancel_url="https://seen-unseen-xi.streamlit.app/Sponsor_Desk?cancelled=1")
    req = parse_order_details(params.model_dump())
    assert req["intent"] == "CAPTURE"
    pu = req["purchase_units"][0]
    assert pu["amount"] == {"value": "141.00", "currency_code": "USD", "breakdown": pu["amount"]["breakdown"]}
    assert pu["amount"]["breakdown"]["item_total"]["value"] == "141.00"
    assert [i["unit_amount"]["value"] for i in pu["items"]] == ["81.00", "60.00"]
    assert req["payment_source"]["paypal"]["experience_context"]["return_url"].endswith("?paid=sponsor")
