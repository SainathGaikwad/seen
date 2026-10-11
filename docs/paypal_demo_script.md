# SEEN Sponsor Desk — PayPal AI Hackathon demo video (under 3:00)

Narration ≈ 390 words ≈ 2:40 at 145 words a minute. One block per take, a second's pause between blocks. Screen
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
A sponsor types a brief: Hindi-speaking fans, bowlers from outside the big three, three hundred dollars. The desk
agent — Nemotron on Nebius — reads the catalogue, prices a package inside policy: one to four athletes, verified
languages only, the budget as a hard cap, and a price that rises with the athlete's visibility gap. Then it raises a
PayPal checkout order with PayPal's Agent Toolkit. Every tool call is on screen. The agent cannot capture, pay or
move money; the sponsor does that in PayPal.

**THE PAYMENT (1:12)**
The sponsor approves in PayPal checkout. On return, SEEN captures the order, tags the athletes' stories "presented
by", and sends one Payouts batch: sixty per cent to the athlete fund, thirty to the creator who made the content, ten
to SEEN. Sandbox money, real API calls — here is the batch arriving in the athlete fund's account.

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
| The ledger | Money ledger | quick-filter "Bryce", clear; sort by USD; open the *Split by policy* group; **Refresh payouts** → SUCCESS badges; **Export CSV**; the per-athlete grid with the share bars |
| Close | repo on GitHub | `seen/money/` folder, `vendor/paypal_agent_toolkit` NOTICE, `docs/paypal_sponsor_desk.md` |

Timing targets: Hook 0:00–0:14 · Problem 0:14–0:32 · Desk 0:32–1:12 · Payment 1:12–1:45 · Tip 1:45–1:58 · Ledger
1:58–2:22 · Close 2:22–2:45.

## Recording tips

- Log the sandbox **buyer** in at sandbox.paypal.com before recording so checkout needs no password on camera; log the
  **athlete-fund** account in a second browser profile/window for the "money arriving" shot.
- Use a fresh brief for the recording (e.g. "A Bridgetown rum brand wants Caribbean fans to meet Hayley Matthews in
  English and Urdu for one week") so the order is new; the desk takes ~30 s with Nemotron — the cut keeps ~8 s of it.
- Record the raw screen in one pass (5–7 minutes), narration block by block; drop both in `docs/rec_paypal/`
  (git-ignored) and the film is cut from them, captions added like the previous two.
