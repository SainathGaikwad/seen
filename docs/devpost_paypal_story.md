## Inspiration

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get (Cricsheet ball-by-ball data, Wikimedia pageviews, a two-line attention model) and publishes story kits about them — a 60-second script, social posts, an article — in English, Hindi and Urdu, every number checked against a sourced fact before it can be published. Federations, small newsrooms and creators in women's sport have stories and no money loop; sponsors want measurable, safe content; athletes outside the big markets get neither. The Sponsor Desk adds the money.

## What it does

**Sponsor Desk.** A sponsor writes what they want to support and a budget. A tool-calling agent (NVIDIA Nemotron on Nebius Token Factory) reads the catalogue — who is on sale, her ranks, her visibility gap, which languages her verified kit exists in, the week price — prices a package inside the policy (1–4 athletes, verified languages only, the budget as a hard cap, a price that rises with the visibility gap), and raises a PayPal checkout order, or a PayPal invoice for larger amounts, with PayPal's Agent Toolkit tools. Every tool call and result is shown on the page. The sponsor approves in PayPal; the agent cannot capture, pay or move money.

**Settlement.** When PayPal sends the sponsor back, SEEN captures the order, tags the athlete's stories "Presented by …" in the fan feed, and sends the shares out in one PayPal Payouts batch — 60 % to the athlete fund, 30 % to the creator who made the content, 10 % to SEEN. Invoices settle the same way once PayPal reports them paid.

**Fan tips.** Every card in the fan feed has a *Tip $2* button: PayPal checkout, capture on return, 70 / 20 / 10 split, paid out.

**Money ledger.** Every order, invoice and payout in an AG Grid (Community): column filters and floating filters, a quick filter, totals pinned to the bottom that follow the filter, status badges, column groups for the split, CSV export, and a second grid per athlete showing what her story raised, who presented it and what went to her fund and her creator.

## How we built it

- **PayPal** — Orders v2 (create with return/cancel URLs, get, capture), Invoicing v2 (create, send, get), Payouts v1 (batch create, batch status), all on the sandbox. Orders and invoices go through the PayPal Agent Toolkit's tool handlers (`create_order`, `pay_order`, `get_order_details`, `create_invoice`, `send_invoice`, `get_invoice`); payouts through its HTTP client. The toolkit is vendored under its Apache-2.0 licence (`vendor/paypal_agent_toolkit`, NOTICE kept).
- **The agent** — a tool-calling loop with JSON actions over deterministic tools (`seen/money/desk.py`): `catalogue`, `price_package`, `create_order`, `create_invoice`. The model plans and explains; the price, the split and the payout are computed by code, and the model has no tool that could capture or pay. If the model is slow or unavailable the desk falls back to a rules planner so the sponsor always gets a priced package.
- **The app** — Streamlit (hosted on Community Cloud), DuckDB, pandas; AG Grid Community 36 for the ledger; the same deterministic claim checker that gates every story also gates what can be sold (verified kits only).

## Challenges

Keeping the agent honest about money: the policy is code, the model only narrates it. Settlement had to be idempotent — PayPal can send the sponsor back more than once, and the hosted demo redeploys from the repository, so the ledger is committed as evidence and a returning visit never pays out twice. And the demo had to run on real sandbox calls, not mocks: the ledger rows in the repository are real sandbox orders, tips and payout batches.

## What's next

Live PayPal credentials behind the same code, per-athlete payout accounts instead of one fund, and sponsor invoices with net terms for federations.

## Where to look

- Live app (PayPal sandbox): https://seen-unseen-xi.streamlit.app — Sponsor Desk, Fan feed, Money ledger
- Code: https://github.com/SainathGaikwad/seen — `seen/money/` (desk, PayPal gateway, ledger, packages), `app/pages/9_Sponsor_Desk.py`, `app/pages/7_Fan_Feed.py`, `app/pages/10_Money_Ledger.py`, write-up in `docs/paypal_sponsor_desk.md`
- Everything in the demo is PayPal sandbox test money, with real API calls. The video's narration is an open-source voice (Kokoro); no music.
