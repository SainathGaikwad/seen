# SEEN Sponsor Desk — money for the Unseen XI, on PayPal

*Entry for the PayPal AI Hackathon (Devpost, closes 12 Nov 2026 12:00 pm PST). Everything below runs on the PayPal
**sandbox**; no live money has moved.*

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get and publishes
claim-checked story kits about them in English, Hindi and Urdu. The Sponsor Desk is the money side of that newsroom:
sponsors pay to have a verified story "presented by" them, fans tip the stories they like, and the money is split by
a fixed policy and paid out through PayPal to the athlete fund and the creator who made the content.

## What a user sees

| Who | Page | What happens |
|---|---|---|
| Sponsor | **Sponsor Desk** | types a brief ("Hindi-speaking fans should meet bowlers from outside the big three", budget $300) → the desk agent reads the catalogue, prices a package within policy and budget, raises a **PayPal checkout order** (or a **PayPal invoice** for larger amounts / on request) → the sponsor approves it in PayPal → on return SEEN captures the order, tags the stories "Presented by …", and sends the shares out with **PayPal Payouts** |
| Fan | **Fan feed** | a *Tip $2* button on every card → PayPal checkout → on return the tip is captured and split 70 / 20 / 10 |
| Everyone | **Money ledger** | every order, invoice and payout in an AG Grid: filters, totals that follow the filter, status badges, CSV export, and a per-athlete view of what her story raised and where it went |

## The agent (seen/money/desk.py)

The desk is a tool-calling agent. The model (NVIDIA Nemotron on Nebius Token Factory in the hosted demo; any provider
`seen.llm` supports) plans one tool call per turn and answers with JSON; the tools are deterministic Python and
enforce the policy whatever the model asks for:

| Tool | Does | Guardrail |
|---|---|---|
| `catalogue` | the Unseen XI with ranks, gap z-score, verified languages and week price | only kits that passed the claim checker in every format are listed |
| `price_package` | prices athletes × languages × weeks; returns the 60 / 30 / 10 split | 1–4 athletes, verified languages only, 1–4 weeks, budget is a hard cap — errors come back as tool results so the model can re-plan |
| `create_order` | PayPal Agent Toolkit `create_order` (Orders v2, CAPTURE intent, return/cancel URLs) | one payment request per brief; the sponsor approves in PayPal, never the agent |
| `create_invoice` | PayPal Agent Toolkit `create_invoice` + `send_invoice` | needs the sponsor's email; same single-request rule |

The model never touches money: it cannot capture an order, cannot pay an invoice and cannot create a payout. Those
happen in `app/money_ui.py` *after* PayPal confirms the sponsor paid (`pay_order` on the return leg, `get_invoice`
for invoices), and the payout amounts come from the policy split, not from the model. Without a model key the same
tools are driven by a transparent rules planner (keyword match on the brief, biggest gaps first), labelled as such.

Pricing is policy too (`config.yaml → money`): `base × (1 + 0.35 × gap z)` per language-week plus $25 per extra
language — the more under-seen an athlete is, the more her story is worth to a sponsor, which is the point of SEEN.

## PayPal surface used

- **Orders v2** — create (`payment_source.paypal.experience_context` with return/cancel URLs), get, capture.
- **Invoicing v2** — create, send, get (status polled when the sponsor says they have paid).
- **Payouts v1** — one batch per settled payment: the athlete fund's share and the creator's share; SEEN's share stays in the
  merchant account; batch and item status are refreshed from the ledger page.
- All orders and invoices go through PayPal's own **Agent Toolkit** tool handlers (`vendor/paypal_agent_toolkit`,
  Apache-2.0, vendored because the PyPI package pins agent frameworks SEEN does not use); payouts use the toolkit's HTTP
  client against the REST endpoint.

Credentials: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (sandbox app), optional `PAYPAL_ENV=sandbox|live` (sandbox is
the default and the only thing SEEN has run against), `SEEN_APP_URL` (where PayPal sends the payer back),
`SEEN_PAYEE_ATHLETE_FUND` / `SEEN_PAYEE_CREATOR` (sandbox account emails; also `money.payees` in config.yaml).

## What is real and what is simulated

- Money: PayPal **sandbox** — real API calls, test balances. Rows written without credentials (`SEEN_PAYPAL_FAKE=1`,
  used by the tests) carry `simulated=True` and the ledger says so.
- Stories, facts, visibility gaps: real pipeline output (Cricsheet, Wikimedia), claim-checked.
- "Athlete fund" and "creator" payees are sandbox test accounts standing in for a federation-run fund and a creator.

## Runbook

1. PayPal developer dashboard → sandbox app → copy the client id and secret into `.streamlit/secrets.toml` (local) and
   Streamlit Community Cloud → Settings → Secrets (hosted):
   ```
   PAYPAL_CLIENT_ID = "…"
   PAYPAL_CLIENT_SECRET = "…"
   PAYPAL_ENV = "sandbox"
   SEEN_APP_URL = "https://seen-unseen-xi.streamlit.app"      # http://localhost:8501 locally
   SEEN_PAYEE_ATHLETE_FUND = "sb-…@personal.example.com"
   SEEN_PAYEE_CREATOR = "sb-…@personal.example.com"
   ```
   Enable *Payouts* (and *Invoicing*) on the sandbox app's features if the dashboard offers the switches.
2. Pay as the sandbox **personal** account when PayPal's checkout opens; on return the app captures and settles.
3. `python -m pytest tests/test_money.py` — the whole loop against the fake gateway. `SEEN_PAYPAL_FAKE=1 streamlit run app/Home.py`
   runs the pages with simulated payments.
4. The ledger (`data/derived/money_ledger.csv`, `sponsorships.json`) is a plain file: commit it after a sandbox session
   so the hosted demo (whose disk resets on redeploy) shows real sandbox history.
