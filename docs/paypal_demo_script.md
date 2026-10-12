# SEEN Sponsor Desk — PayPal AI Hackathon demo video (under 3:00)

Narration ≈ 315 words ≈ 2:15 at 145 words a minute — the screen gets room to breathe; do not add to it. One block per take, a second's pause between blocks. Screen
recording follows the shot list; the film is cut to the narration. Rules from the hackathon page: under three minutes,
public on YouTube, the project working end to end, **no third-party trademarks or copyrighted music** — PayPal's own
checkout screens are the product being demonstrated and are fine; keep other logos (browser chrome, Streamlit footer)
out of frame where you can, no music.

---

**HOOK (0:00)**
SEEN finds the women cricketers whose performance most exceeds the attention they get, and publishes claim-checked
stories about them in English, Hindi and Urdu. This is the money side of that newsroom: the Sponsor Desk.

**PROBLEM (0:14)**
Federations, small newsrooms and creators in women's sport have stories and no money loop. Sponsors want measurable,
safe content. Athletes outside the big markets get neither. So we built an agent that sells verified stories — and
PayPal moves the money.

**THE DESK (0:32)**
A sponsor types a brief: Caribbean fans, Hayley Matthews, English and Urdu, one week. The desk agent — Nemotron on
Nebius — reads the catalogue, prices a package inside policy: one to four athletes, verified
languages only, the budget as a hard cap, and a price that rises with the athlete's visibility gap. Then it raises a
PayPal checkout order with PayPal's Agent Toolkit. Every tool call is on screen. The agent cannot capture, pay or
move money; the sponsor does that in PayPal.

**THE PAYMENT (1:12)**
The sponsor approves in PayPal checkout. On return, SEEN captures the order, tags the athlete's stories "presented
by", and sends one Payouts batch: sixty per cent to the athlete fund, thirty to the creator who made the content, ten
to SEEN. Sandbox money, real API calls.

**THE TIP (1:45)**
Fans do the same for two dollars: tip her story, PayPal, split seventy-twenty-ten, paid out.

**THE LEDGER (1:58)**
The money ledger is an AG Grid: every order, invoice and payout, column filters, totals that follow the filter,
status badges, CSV export — and per athlete, what her story raised and where it went.

**CLOSE (2:22)**
Orders, Invoicing and Payouts; PayPal's Agent Toolkit for the agent's tools; Nemotron for the planning; a
deterministic claim checker for every number in every story. The under-seen athlete becomes the thing worth paying
for — and the money reaches her. SEEN: women's cricket, correctly, paid.

---

## Shot list (hosted app, 1920×1080, browser zoom 110–125 %)

| Block | Screen | What to show |
| --- | --- | --- |
| Hook | https://seen-unseen-xi.streamlit.app | Unseen XI cards → Story Kit page: a kit, the fact bundle, the claim-check panel |
| Problem | Sponsor Desk page, top | the "On sale this week" table (ranks, gap z, languages, week price) |
| The desk | Sponsor Desk | type the brief, click **Ask the Sponsor Desk**; open the `catalogue`, `price_package` and `create_order` expanders (args + result); the package table and the split line; the summary |
| The payment | click **Approve and pay in PayPal (sandbox)** | PayPal sandbox checkout (buyer already logged in) → Review Order → Pay Now → back on the Sponsor Desk: the green receipt + the payout-batch line; then Fan feed: the "Presented by" tag on the card; then sandbox.paypal.com logged in as the athlete-fund account: Activity shows the payout |
| The tip | Fan feed | **Tip $2** → **Pay the tip in PayPal** → Pay Now → receipt on the Fan feed |
| The ledger | Money ledger | **Refresh payouts**; quick-filter "Bryce", reset; slide the grid right to the *Split by policy* columns, the status and payout badges and the PayPal ids; open the *Split by policy* group; scroll the page to the per-athlete grid with the share bars |
| Close | repo on GitHub | `seen/money/` folder, `vendor/paypal_agent_toolkit` NOTICE, `docs/paypal_sponsor_desk.md` |

Timing targets: Hook 0:00–0:14 · Problem 0:14–0:32 · Desk 0:32–1:12 · Payment 1:12–1:45 · Tip 1:45–1:58 · Ledger
1:58–2:22 · Close 2:22–2:45.

## Recording tips

- `python docs\record_paypal.py --login` once: log the sandbox **buyer** in at sandbox.paypal.com in the window that
  opens, so checkout needs no password on camera (`--login-fund` does the same for the athlete-fund account, for an
  optional "money arriving" clip).
- `python docs\record_paypal.py` records the whole pass by itself (one tab, ~2½ minutes) into `docs/rec_paypal/`
  (git-ignored): it prints `viewport 1600x900` after the warm-up and switches to a headless browser if the window on
  your screen cannot show that size. Narration block by block (a phone or laptop mic in a quiet room, or the generated
  voice) goes next to it; the film is cut to the narration with captions like the previous two.
- The brief in the recorder is the one in the narration above ("A Bridgetown rum brand wants Caribbean fans to meet
  Hayley Matthews in English and Urdu for one week", sponsor "Bridgetown Rum Co"); change both together.
