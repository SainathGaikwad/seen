"""The Sponsor Desk agent: a brief in, a priced package of verified athlete stories and a PayPal payment request out.

The model (NVIDIA Nemotron on Nebius, Gemini, … — whatever seen.llm is configured with) plans by calling tools one at
a time; the tools are deterministic and enforce the policy (catalogue only, verified languages only, at most four
athletes, the budget is a hard cap, exactly one payment request per run). The payment itself is PayPal's: an order the
sponsor approves in PayPal checkout, or an invoice PayPal sends — both created with PayPal's Agent Toolkit tools.
Nothing is captured and no payout is made until the sponsor has paid; see app/money_ui.py for that half.

Without a model key the desk runs a rules planner over the same tools, labelled as such.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from seen import llm
from seen.money import ledger
from seen.money.packages import PackageError, catalogue, policy, price_package

log = logging.getLogger(__name__)

MAX_STEPS = 8
DEADLINE_S = 90.0   # the model gets this long in total; after that the rules planner finishes the job

TOOL_DOCS = {
    "catalogue": "catalogue {} → the Unseen XI athletes on sale this week: player_id, name, team, role, impact_rank, attention_rank, gap_z (visibility gap, higher = more under-seen), verified languages, week_price_usd (one language, one week) and language_addon_usd per extra language.",
    "price_package": 'price_package {"items": [{"player_id": "…", "languages": ["en", "hi"], "weeks": 1}]} → priced lines, total_usd and the split (60% athlete fund, 30% creator, 10% SEEN). An error message means the package breaks policy; fix it and price again.',
    "create_order": 'create_order {"items": [as priced], "note": "one line for the receipt"} → a PayPal checkout order (PayPal Agent Toolkit create_order): the sponsor approves it in PayPal; returns order_id and approve_url. Use for totals below the invoice threshold unless the sponsor asked for an invoice.',
    "create_invoice": 'create_invoice {"items": [as priced], "note": "one line for the invoice"} → a PayPal invoice (PayPal Agent Toolkit create_invoice + send_invoice) emailed to the sponsor; returns invoice_id and view_url. Use when the sponsor asked for an invoice or the total is at or above the threshold.',
}

SYSTEM = """You are the Sponsor Desk of SEEN, a newsroom that publishes claim-checked stories about women cricketers the market overlooks (the Unseen XI). A sponsor gives you a brief and a budget; you assemble a package of athlete stories to be "presented by" the sponsor, price it with the tools, and raise the payment on PayPal. You never move money yourself: the sponsor pays in PayPal, and only after that are the athlete fund and the creator paid their share.

You work by calling ONE tool per turn. Answer with a single JSON object and nothing else:
  {"thought": "<one short sentence>", "tool": "<tool name>", "args": {...}}
or, when the payment request exists:
  {"thought": "<one short sentence>", "final": {"summary": "<2-4 sentences for the sponsor: who, why they fit the brief, languages, total and what happens next>"}}

Tools:
- %(catalogue)s
- %(price_package)s
- %(create_order)s
- %(create_invoice)s

Rules you cannot break (the tools enforce them too):
1. Only athletes from the catalogue; only languages in an athlete's verified list; 1 to %(max_athletes)d athletes; 1 to %(max_weeks)d weeks each.
2. The budget is a hard cap on total_usd. If the first package is over budget, drop a language or an athlete and price again.
3. Follow the brief: named teams, countries, roles, languages or athletes come first. When the brief leaves room, prefer the largest gap_z and teams outside India, England and Australia — that is what SEEN is for.
4. Order of work: catalogue → price_package (repeat until it is within policy and budget) → exactly one of create_order / create_invoice → final. Never call a payment tool twice.
5. Every number in your summary must come from a tool result. Do not invent athletes, prices, statistics or promises.
   Describe each athlete by her catalogue role and team (an all-rounder is not a bowler); when the brief asked for
   something the catalogue cannot give (a role, a language), say so in one clause instead of pretending it did.
6. Payment method: %(pay_method)s. Invoice threshold: $%(threshold).2f.
"""

LANG_WORDS = {"hindi": "hi", "urdu": "ur", "english": "en", "tamil": "ta", "bengali": "bn", "marathi": "mr", "telugu": "te", "sinhala": "si"}
ROLE_WORDS = {"bowler": "bowler", "bowlers": "bowler", "batter": "batter", "batters": "batter", "batsman": "batter", "all-rounder": "all-rounder", "allrounder": "all-rounder", "all-rounders": "all-rounder", "all rounder": "all-rounder"}


@dataclass
class DeskResult:
    mode: str = ""                       # "model: <label>" or "rules"
    steps: list = field(default_factory=list)
    package: dict | None = None
    payment: dict | None = None          # {"kind": "order"|"invoice", "ref", "url", "status"}
    summary: str = ""
    error: str = ""


class DeskTools:
    """The deterministic half of the desk: catalogue, pricing, and the two PayPal tools, with the guardrails."""

    def __init__(self, cfg: dict, derived: Path, xi: pd.DataFrame, gateway, sponsor: dict, budget: float, pay_method: str, return_url: str, cancel_url: str):
        self.cfg, self.derived, self.gateway = cfg, Path(derived), gateway
        self.sponsor, self.budget, self.pay_method = sponsor, float(budget), pay_method
        self.return_url, self.cancel_url = return_url, cancel_url
        self.pol = policy(cfg)
        self.cat = catalogue(xi, derived, cfg)
        self.package: dict | None = None
        self.payment: dict | None = None

    def names(self) -> list[str]:
        return list(TOOL_DOCS)

    def run(self, name: str, args: dict) -> dict:
        args = args or {}
        if name == "catalogue":
            return {"athletes": [{k: v for k, v in c.items() if k not in ("language_names",)} for c in self.cat], "budget_usd": self.budget,
                    "invoice_threshold_usd": self.pol["invoice_threshold"], "payment_method": self.pay_method}
        if name == "price_package":
            try:
                self.package = price_package(args.get("items") or [], self.cat, self.cfg, budget=self.budget)
            except PackageError as exc:
                return {"error": str(exc)}
            return {"lines": [{k: l[k] for k in ("player_id", "name", "team", "languages", "weeks", "amount_usd")} for l in self.package["lines"]],
                    "total_usd": self.package["total_usd"], "split_usd": self.package["split"], "within_budget": True}
        if name in ("create_order", "create_invoice"):
            if self.payment:
                return {"error": "a payment request already exists for this brief; answer with final"}
            if self.gateway is None:
                return {"error": "PayPal is not configured (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET)"}
            try:
                pkg = price_package(args.get("items") or (self.package or {}).get("lines") or [], self.cat, self.cfg, budget=self.budget)
            except PackageError as exc:
                return {"error": str(exc)}
            self.package = pkg
            items = [{"name": l["item_name"], "description": l["description"], "item_cost": l["amount_usd"], "quantity": 1} for l in pkg["lines"]]
            note = (args.get("note") or f"SEEN sponsorship for {self.sponsor.get('name', 'sponsor')}")[:120]
            kind = "order" if name == "create_order" else "invoice"
            if kind == "invoice" and not self.sponsor.get("email"):
                return {"error": "an invoice needs the sponsor's email; use create_order instead"}
            try:
                if kind == "order":
                    res = self.gateway.create_order(items, self.return_url, self.cancel_url, notes=note)
                    self.payment = {"kind": "order", "ref": res.order_id, "url": res.approve_url, "status": res.status}
                else:
                    res = self.gateway.create_invoice(self.sponsor["email"], self.sponsor.get("name", "Sponsor"), items, note=note, reference=f"SEEN-{self.sponsor.get('name', 'sponsor')[:20]}")
                    self.payment = {"kind": "invoice", "ref": res.invoice_id, "url": res.view_url, "status": res.status}
            except Exception as exc:   # PayPal errors come back as the tool result, so the model can explain them
                log.warning("PayPal %s failed: %s", name, exc)
                return {"error": f"PayPal rejected the {kind}: {str(exc)[:300]}"}
            self._record(pkg, note)
            return {k: v for k, v in self.payment.items()} | {"total_usd": pkg["total_usd"], "simulated": bool(getattr(self.gateway, "simulated", False))}
        return {"error": f"unknown tool {name}"}

    def _record(self, pkg: dict, note: str) -> None:
        sim = bool(getattr(self.gateway, "simulated", False))
        kind = "sponsorship" if self.payment["kind"] == "order" else "invoice"
        for l in pkg["lines"]:
            sp = l["split"]
            ledger.record(self.derived, kind=kind, ref=self.payment["ref"], status=self.payment["status"] or ("CREATED" if kind == "sponsorship" else "SENT"),
                          payer=self.sponsor.get("name", ""), payer_email=self.sponsor.get("email", ""), player_id=l["player_id"], athlete=l["name"], team=l["team"],
                          languages=l["languages"], weeks=l["weeks"], item=l["item_name"], amount=l["amount_usd"], currency="USD",
                          split_athlete=sp["athlete_fund"], split_creator=sp["creator"], split_seen=sp["seen"], simulated=sim, note=note)


def _compact(obj, limit: int = 6000):
    """Tool results go back to the model verbatim unless they are huge (then as a truncated string)."""
    s = json.dumps(obj, ensure_ascii=False)
    return obj if len(s) <= limit else s[:limit] + " …[truncated]"


def run_desk(brief: str, budget: float, sponsor: dict, pay_method: str, cfg: dict, derived: Path, xi: pd.DataFrame, gateway,
             return_url: str, cancel_url: str, complete=None, use_model: bool | None = None, max_steps: int = MAX_STEPS,
             deadline_s: float = DEADLINE_S) -> DeskResult:
    tools = DeskTools(cfg, derived, xi, gateway, sponsor, budget, pay_method, return_url, cancel_url)
    res = DeskResult()
    if not tools.cat:
        res.error = "no verified story kits to sell (run the pipeline first)"
        return res
    scripted = complete is not None
    complete = complete or llm.quick   # one attempt per step, short timeout: a slow or rate-limited model falls back to rules
    if use_model is None:
        use_model = llm.available()
    if use_model:
        try:
            _model_loop(brief, budget, sponsor, pay_method, tools, complete, res, max_steps, deadline_s)
            res.mode = "model: scripted" if scripted else f"model: {llm.model_label()}"
        except Exception as exc:
            log.warning("desk model loop failed (%s); falling back to rules", exc)
            if tools.payment:   # the model got as far as the payment request: keep it, only the summary is missing
                res.mode = f"model: {llm.model_label()} (summary by rules)"
                res.error = ""
                res.summary = res.summary or _summary(tools, sponsor, budget)
            else:
                res = DeskResult()
                tools = DeskTools(cfg, derived, xi, gateway, sponsor, budget, pay_method, return_url, cancel_url)
                _rules_loop(brief, budget, sponsor, pay_method, tools, res)
                res.mode = f"rules (model unavailable: {str(exc)[:80]})"
    else:
        _rules_loop(brief, budget, sponsor, pay_method, tools, res)
        res.mode = "rules (no model key)"
    res.package, res.payment = tools.package, tools.payment
    if not res.payment and not res.error:
        res.error = "the desk finished without a payment request"
    return res


def _step(res: DeskResult, tools: DeskTools, name: str, args: dict, thought: str = "") -> dict:
    out = tools.run(name, args)
    res.steps.append({"n": len(res.steps) + 1, "thought": thought, "tool": name, "args": args, "result": out})
    return out


def _model_loop(brief, budget, sponsor, pay_method, tools: DeskTools, complete, res: DeskResult, max_steps: int, deadline_s: float = DEADLINE_S) -> None:
    pol = tools.pol
    t0 = time.monotonic()
    system = SYSTEM % {**TOOL_DOCS, "max_athletes": pol["max_athletes"], "max_weeks": pol["max_weeks"], "pay_method": pay_method, "threshold": pol["invoice_threshold"]}
    base = {"sponsor": sponsor.get("name", ""), "sponsor_email_given": bool(sponsor.get("email")), "budget_usd": float(budget), "payment_method": pay_method, "brief": brief}
    for _ in range(max_steps):
        if time.monotonic() - t0 > deadline_s:
            raise TimeoutError(f"the model took longer than {deadline_s:.0f}s")
        user = json.dumps({"request": base, "history": [{"step": s["n"], "tool": s["tool"], "args": s["args"], "result": _compact(s["result"])} for s in res.steps],
                           "instruction": "Reply with the next JSON object only."}, ensure_ascii=False)
        raw = complete(system, user, max_tokens=1500)
        obj = llm.parse_json(raw) or {}
        thought = str(obj.get("thought", ""))[:300]
        if "final" in obj:
            fin = obj["final"] if isinstance(obj["final"], dict) else {"summary": str(obj["final"])}
            res.summary = str(fin.get("summary", ""))[:1500]
            if not tools.payment:
                res.error = "the model finished before raising a payment request"
            return
        name = str(obj.get("tool", "")).strip()
        if name not in TOOL_DOCS:
            res.steps.append({"n": len(res.steps) + 1, "thought": thought, "tool": name or "?", "args": obj.get("args") or {}, "result": {"error": f"unknown tool '{name}'; use one of {list(TOOL_DOCS)}"}})
            continue
        _step(res, tools, name, obj.get("args") or {}, thought)
    res.error = f"stopped after {max_steps} steps"


def _rules_loop(brief: str, budget: float, sponsor: dict, pay_method: str, tools: DeskTools, res: DeskResult) -> None:
    """A transparent planner for runs without a model: keyword match on the brief, then the biggest gaps first."""
    text = brief.lower()
    cat = _step(res, tools, "catalogue", {}, "Read what is on sale this week.")["athletes"]
    teams = {c["team"] for c in cat}
    want_teams = {t for t in teams if t.lower() in text or t.lower().split()[-1] in text}
    want_roles = {v for k, v in ROLE_WORDS.items() if re.search(rf"\b{re.escape(k)}\b", text)}
    want_langs = [v for k, v in LANG_WORDS.items() if k in text]
    want_names = [c for c in cat if c["name"].lower() in text or c["name"].split()[-1].lower() in text.split()]

    def score(c):
        s = 0.0
        if c in want_names:
            s += 10
        if c["team"] in want_teams:
            s += 3
        if c["role"] in want_roles:
            s += 1.5
        if want_langs and all(l in c["languages"] for l in want_langs):
            s += 2.0   # a brief that names a language needs a verified kit in it: that outranks role and team
        if c["team"] not in (tools.cfg.get("big_three") or ["India", "England", "Australia"]):
            s += 0.5
        return s + 0.3 * c["gap_z"]

    ranked = sorted(cat, key=score, reverse=True)
    n = min(tools.pol["max_athletes"], max(1, len(want_names)) if want_names else 2)
    items = []
    for c in ranked[:n]:
        langs = ["en"] + [l for l in want_langs if l in c["languages"] and l != "en"]
        items.append({"player_id": c["player_id"], "languages": list(dict.fromkeys(langs)), "weeks": 1})
    priced = _step(res, tools, "price_package", {"items": items}, "Price the athletes that match the brief, biggest gaps first.")
    while "error" in priced and items:
        # over budget or outside policy: fewer athletes first (the brief's languages matter more than a second name),
        # then shed extra languages
        if len(items) > 1:
            items = items[:-1]
        else:
            it = items[0]
            if len(it["languages"]) > 1:
                it["languages"] = it["languages"][:-1]
            else:
                break
        priced = _step(res, tools, "price_package", {"items": items}, "Trim the package to fit the budget.")
    if "error" in priced:
        res.error = priced["error"]
        return
    total = priced["total_usd"]
    use_invoice = pay_method == "invoice" or (pay_method == "auto" and total >= tools.pol["invoice_threshold"] and sponsor.get("email"))
    pay = _step(res, tools, "create_invoice" if use_invoice else "create_order", {"items": items, "note": f"SEEN sponsorship: {len(items)} athlete stories for {sponsor.get('name', 'sponsor')}"},
                "Raise the payment request on PayPal.")
    if "error" in pay:
        res.error = pay["error"]
        return
    res.summary = _summary(tools, sponsor, budget)


def _summary(tools: DeskTools, sponsor: dict, budget: float) -> str:
    pkg, pay = tools.package or {"lines": [], "total_usd": 0.0, "split": {}}, tools.payment or {}
    who = "; ".join(f"{l['name']} ({l['team']}, {'+'.join(x.upper() for x in l['languages'])})" for l in pkg["lines"])
    sp = pkg.get("split") or {}
    return (f"Package for {sponsor.get('name', 'the sponsor')}: {who}. Total ${pkg['total_usd']:,.2f}, within the ${float(budget):,.2f} budget; "
            f"${sp.get('athlete_fund', 0):,.2f} goes to the athlete fund and ${sp.get('creator', 0):,.2f} to the creators once paid. "
            + ("The invoice has been sent by PayPal." if pay.get("kind") == "invoice" else "Approve the order in PayPal to confirm."))
