# SEEN — submission text for the October 2026 hackathons

Paste-ready text for the two forms. Fields in `[brackets]` are filled on the day (URLs you create). Keep
every number as written here; each one is reproducible from the prototype's own run (`data/derived/`).

---

## A. Google Cloud AI Builder Cup 2026 (Hack2skill) — register by 11 Oct, submit by 18 Oct

**Team name:** SEEN
**Members:** Sainath Gaikwad (team lead) · Sharvari Otari
**Theme:** Media, Content & Digital Experiences
**Project title:** SEEN — The Unseen XI: fact-locked athlete stories in the fan's language

**One line (tagline):**
Every week, the eleven women cricketers whose performance most exceeds the attention they get — found in public data, written by Gemini from locked facts, verified figure by figure, and delivered in the fan's language.

**Problem (≈120 words):**
Women's cricket has an attention problem, not a content problem. In the 2026 Women's T20 World Cup, how an athlete played explained only 20% of the attention she received (R² 0.20 on Wikipedia article views); who she already was — home-market size and prior fame — explained 81%. The result is a visibility gap that falls hardest on players from outside India, England and Australia: Hayley Matthews finished the tournament ranked #1 by impact and #52 by attention. Rights-holders and publishers cannot act on this gap because nobody measures it athlete by athlete, week by week, and because turning a performance into publishable, multilingual, *correct* content at that cadence is expensive and error-prone.

**Solution (≈200 words):**
SEEN is a working content-intelligence pipeline and editor app. It turns Cricsheet ball-by-ball data into a graph, detects ten narrative patterns (first-ever wins, milestones, all-round performances), scores their significance, and measures attention from Wikimedia pageviews in eight language editions. Two regression lines give every athlete an expected level of attention; the residual is her visibility gap. A constrained selection picks the Unseen XI (≤3 per country, ≥3 from outside the big three, consent-gated, 14-day cooldown).

For each athlete, Gemini writes a story kit — a 60-second video script, social posts and an article — from a bundle of sourced facts, and translates it into Hindi and Urdu with a locked cricket glossary. A deterministic claim checker verifies every number in every draft against the fact bundle and blocks anything it cannot match: in this run, 1,123 numeric claims across 88 formats, zero unverifiable in the published kits. The editor can ask Gemini for a live rewrite with an angle ("for a first-time fan in Lahore"); the draft replaces the text only if it passes. Kits route to creator briefs, app cards, commentary packs and a fan feed, and an impact dashboard measures attention lift against matched controls.

**Google Cloud and Gen AI used:**
Gemini (gemini-3.8-flash via the google-genai SDK) for prose, translation and live rewrites · Cloud Run (asia-south1) hosts the app with the analysed data baked into the container · Secret Manager holds the API key · Cloud Build builds the image from the Dockerfile. Production path: Gemini on Vertex AI with provisioned throughput, Firestore for fan events and the publish log, BigQuery for the attention index, Cloud Scheduler and Cloud Run jobs for the weekly pipeline.

**Why it is a Media, Content & Digital Experiences solution:**
Creation (eight formats from one verified event), discovery (the Unseen XI and the fan feed surface athletes the market overlooks), personalisation (language, editorial angle), understanding (the claim checker makes model output safe to publish), experience (athlete-first cards in the fan's language) — one loop, measured.

**Links for the form:**
- Functional prototype (Cloud Run): `[https://seen-….run.app]`
- Demo video (3 min, YouTube/Drive public): `[link]`
- Proposal deck (PDF): `docs/SEEN_AI_Builder_Cup_proposal.pdf`
- Code: `[GitHub repo]` (optional for the Cup; required for Nebius)

**Submission checklist (18 Oct):** PDF proposal ✓ · prototype deployed on Cloud Run and opening in <5 s ✓ · video ≤3:00 showing the live app and one Gemini rewrite ✓ · category stated (Media, Content & Digital Experiences) ✓ · all materials in English ✓.

---

## B. Nebius × NVIDIA Global AI Hackathon (Devpost) — submit by 30 Oct, 10:00 PT (22:30 IST)

**Track:** Best Apps and Agents
**Project name:** SEEN — The Unseen XI
**Tagline:** Fact-locked athlete stories from open data, written by NVIDIA Nemotron on Nebius Token Factory and verified before anyone reads them.

**About the project (Devpost "story" field):**

*Inspiration.* In the 2026 Women's T20 World Cup, performance explained 20% of the attention an athlete received; market size and prior fame explained 81%. Great players from Ireland, Scotland, the West Indies or Sri Lanka finish top-ten by impact and outside the top fifty by attention. Nobody measures that gap weekly, and nobody can afford to write correct, multilingual stories for the athletes the market overlooks. We built the machine that does both.

*What it does.* SEEN turns Cricsheet ball-by-ball data into a graph, detects narrative patterns, scores significance, measures attention from Wikimedia pageviews in eight languages, fits two regression lines, and picks the Unseen XI under editorial constraints. For each athlete, Nemotron writes a story kit (video script, social posts, article) from a bundle of sourced facts and translates it into Hindi and Urdu with a locked glossary. A deterministic claim checker re-verifies every number against the bundle and blocks drafts it cannot match. In the hosted app, an editor can ask Nemotron for a live rewrite with an angle; the draft is published only if it passes. Kits route to creator briefs, app cards, commentary packs and a fan feed; an impact dashboard measures lift against matched controls.

*How we built it.* Python, DuckDB, pandas and Streamlit; the pipeline runs from one command and the app runs in one container. `seen/llm.py` talks to Nebius Token Factory through its OpenAI-compatible endpoint with `nvidia/nemotron-3-super-120b-a12b` (falling back to Nemotron 3 Nano 30B and Nemotron 3.5 Lightning), reasoning switched off for JSON answers, low temperature, prompts cached by content hash. `seen/stories/claim_check.py` is the gate between the model and publication.

*Challenges.* Making an open model safe to publish: the answer was not a better prompt but a checker that treats every number as a claim with a fact ID, and a UI that shows a blocked draft instead of hiding it. Keeping the attention model honest (two lines, not one, so a small market is not mistaken for a scandal). Free-tier quotas during development.

*Accomplishments.* A real run on 3,577 women's matches and 165 athletes: 11 kits, 224 facts, 1,123 numeric claims checked, zero unverifiable in the published kits; translations re-verified after generation; a live model loop in the hosted app.

*What we learned.* Nemotron 3 Super writes vivid, well-structured JSON from a fact bundle and keeps citations in place when the instruction is explicit; turning off reasoning for structured answers cuts latency and cost without hurting quality on this task.

*What's next.* A weekly public Unseen XI through the WBBL (Nov–Dec), a read-only API for creators, a measured pilot with a rights-holder, and a consent workflow agreed with the boards.

**Built with:** python · duckdb · pandas · streamlit · plotly · nvidia-nemotron-3 · nebius-token-factory · openai-sdk · cloud-run · docker

**Try it out:** https://seen-unseen-xi.streamlit.app · https://github.com/SainathGaikwad/seen · https://youtu.be/YXaoldQgoZg

**How Nemotron / Token Factory are used (README section already written):** `README.md` → "How NVIDIA Nemotron and Nebius Token Factory are used".

**Feedback on Token Factory (required field — fill after your first real run):**
onboarding (minutes to first successful call), model catalogue clarity (ids as listed vs ids the API accepts), the `enable_thinking` behaviour, latency for 3k-token JSON answers, credits/promo flow, what you would change.

**Submission checklist (30 Oct):** public repo with `LICENSE` (MIT) visible in the About section ✓ · README with setup instructions and the Nemotron/Token Factory notes ✓ · working demo URL that stays up until 15 Dec ✓ · demo video <3:00 on YouTube, public ✓ · track chosen ✓ · feedback section ✓ · "significant updates" note: SEEN predates the submission period — list what was added during it: the Nemotron provider, the live rewrite loop, the Cloud Run deployment, the hosted demo.

---

## C. GitLab "Life After Code" (Devpost: gitlab-transcend.devpost.com) — submit by 27 Oct, 1:00 pm UTC (6:30 pm IST)

**Path:** B — Bring Your Own (MIT project imported to GitLab; automation and deployment done on/after 5 Oct)
**Level of autonomy:** Supervised — the agents run the multi-step review on their own; a human approves the outcome (the merge)
**Project name:** SEEN — The Unseen XI, with an Editor-in-chief on GitLab
**Tagline:** Fact-locked athlete stories: a Duo agent runs the claim gate on every merge request, the pipeline re-runs it on every deploy, and a human approves what is published.

**What it does / the problem it solves (text description):**

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get and turns each into a story kit — a 60-second script, social posts, an article — in English, Hindi and Urdu, written by a model from a bundle of sourced facts. The audience is small newsrooms, creators and federations that publish athlete statistics every week without a fact-checking desk. Their failure mode is not bad prose; it is a plausible number that no fact supports, and one of those costs a publication its trust. Writing the draft takes a model seconds. Everything after the draft — checking every number against a sourced fact, in every language, on every merge and every deploy, and keeping the live demo up — is the product, and that is what we moved onto GitLab.

**How we used GitLab to automate the post-code lifecycle:**

- *Plan / create / govern — the Editor-in-chief flow* (`.gitlab/duo/flows/editor_in_chief.yml`, registered in the AI Catalog, triggered on merge request created / marked ready / mention / reviewer assignment). The first agent reads the MR, runs the deterministic claim gate on the branch (`scripts/check_kits.py --changed origin/main --translations`), posts one review note with the full table (every athlete, language and format — PASS or BLOCKED with the failing number), and applies `editor::verified` or `editor::blocked` through a quick action. When anything is blocked, a router hands over to a planner agent that reads the note, files a work item listing the blocked rows and the two allowed fixes, and links it from the MR. The toolsets contain no approve or merge tool; the human editor approves the outcome.
- *Verify* — `unit-tests`, `claim-gate` (the same gate over all kits and translations; `claim_gate.md` exposed on the MR) and `govern-policies` (six policies: MIT licence present, no tracked secrets, stored check results agree with a fresh run, every fact names its source, the Unseen XI selection constraints hold, simulated numbers stay labelled).
- *Package* — container image to the GitLab registry (`:sha`, `:latest`, `:tag`). *Secure* — SAST, secret detection, dependency scanning, container scanning from GitLab's templates. *Release* — tagged releases with the live-demo and image links via release-cli.
- *Configure / deploy* — production is configured by pushing the verified commit to the hosting repository, from which Streamlit Community Cloud redeploys; a headless browser then verifies the Unseen XI renders (`verify-production`). A manual job deploys the same image to Google Cloud Run.
- *Monitor* — a pipeline schedule every six hours visits the demo like a reader, wakes it if it has gone to sleep, and opens an *incident* issue when it does not come up.

Merge requests require a green pipeline (claim gate + policies) and a human approval. Nine stages touched: plan, create, verify, package, secure, release, configure, monitor, govern.

**Why an agent, and why supervised:** the gate is deterministic; the judgement around it is not ("which rows changed in this MR, what exactly is wrong with `24 overs`, what should the author do, is this worth a work item"). A language model does that well as long as it cannot overrule the gate — so the flow runs the checker and explains it, has no tool that could approve or merge, and the pipeline re-runs the same gate on every merge regardless of what any agent said.

**What we added or changed during the submission period (Path B):** the GitLab project and pipeline (`.gitlab-ci.yml`), the claim-gate CLI (`scripts/check_kits.py`), the governance policies (`scripts/policy_check.py`), the monitor and incident scripts (`docs/keep_awake.py`, `scripts/raise_incident.py`), the Editor-in-chief flow and its AI Catalog registration, the GitHub → Streamlit deploy step and the production verification, and the merge-request workflow (scoped labels, triggers, service account). Everything else in the repository predates October.

**Links for the form:**
- Public GitLab repository: https://gitlab.com/seen-hackathons/seen (MIT licence visible in About; pipeline history under CI/CD → Pipelines)
- Deployed project: https://seen-unseen-xi.streamlit.app (stays live until winners are announced; monitored every six hours) `[+ Cloud Run URL if the bonus deploy is done]`
- Original MIT-licensed project: https://github.com/SainathGaikwad/seen
- Demo video (YouTube, < 3:00, public): `[link]`
- The verified run to point judges at: merge request !1 (blocked → work item #2 → fixed → verified → merged) and the flow sessions linked from `docs/gitlab_life_after_code.md`.

**Built with:** gitlab-ci · gitlab-duo-agent-platform · ai-catalog-flows · python · duckdb · streamlit · playwright · docker · release-cli · gitlab-security-scanners

**Optional fields:** Google Cloud bonus — only if `deploy-cloud-run` has run and the Cloud Run URL is live (the job and `deploy/cloudrun.md` are in the repo). Most Environmentally Impactful — do not opt in (we have no SCI measurement).

**Submission checklist (27 Oct):** registered on Devpost ✓ · video uploaded, public, no music, no third-party logos ✓ · repo public with LICENSE in About ✓ · pipeline history visible ✓ · Path B fields (what was added; deployed URL; original URL) ✓ · level of autonomy = Supervised ✓ · stages ticked: plan, create, verify, package, secure, release, configure, monitor, govern ✓.

---

## D. PayPal AI Hackathon (Devpost: paypalaihackathon.devpost.com) — submit by 12 Nov, 12:00 pm PST (13 Nov 01:30 IST)

**Project name:** SEEN Sponsor Desk — money for the athletes the market overlooks
**Tagline:** An agent turns a sponsor's brief into a package of claim-checked women's-cricket stories, raises the payment on PayPal, and pays the athlete fund and the creator their share — after the sponsor approves, never before.

**Features and functionality (text description):**

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get (Cricsheet ball-by-ball data, Wikimedia pageviews, a two-line attention model) and publishes story kits about them — a 60-second script, social posts, an article — in English, Hindi and Urdu, every number checked against a sourced fact before it can be published. The Sponsor Desk adds the money.

*Sponsor Desk.* A sponsor writes what they want to support and a budget. A tool-calling agent (NVIDIA Nemotron on Nebius Token Factory; the same code runs on Gemini or OpenAI) reads the catalogue — who is on sale, her ranks, her visibility gap, which languages her verified kit exists in, the week price — prices a package inside the policy (1–4 athletes, verified languages only, budget as a hard cap, price rising with the visibility gap), and raises a PayPal checkout order, or a PayPal invoice for larger amounts, with PayPal's Agent Toolkit tools. Every tool call and result is shown on the page. The sponsor approves in PayPal; the agent cannot capture, pay or move money.

*Settlement.* When PayPal sends the sponsor back, SEEN captures the order (`pay_order`), tags the athlete's stories "Presented by …" in the fan feed, and sends the shares out in one PayPal Payouts batch — 60 % to the athlete fund, 30 % to the creator who made the content, 10 % to SEEN. Invoices are settled the same way once PayPal reports them paid.

*Fan tips.* Every card in the fan feed has a *Tip $2* button: PayPal checkout, capture on return, 70 / 20 / 10 split, paid out.

*Money ledger.* Every order, invoice and payout in an AG Grid (Community): column filters and floating filters, quick filter, totals pinned to the bottom that follow the filter, status badges, column groups for the split, CSV export, and a second grid per athlete showing what her story raised, who presented it and what went to her fund and her creator.

**How PayPal is used:** Orders v2 (create with return/cancel URLs, get, capture), Invoicing v2 (create, send, get), Payouts v1 (batch create, batch status) — all on the sandbox; orders and invoices through the PayPal Agent Toolkit's tool handlers (`create_order`, `pay_order`, `get_order_details`, `create_invoice`, `send_invoice`, `get_invoice`), payouts through its HTTP client.

**How AI is used:** the Sponsor Desk agent (tool-calling loop with JSON actions over deterministic tools; model: NVIDIA Nemotron 3 Super via Nebius Token Factory) plans the package and explains it; the story kits themselves are written by the same model from fact bundles and verified by SEEN's deterministic claim checker. The model never sets a price, a split or a payout and never approves a payment.

**Why it matters / who it is for:** federations, small newsrooms and creators in women's sport have stories and no money loop; sponsors want measurable, safe content; athletes outside the big markets get neither. This makes the under-seen athlete the thing worth paying for — her price rises with her gap — and routes money to her fund and to the creator who told her story, with every number in that story already verified.

**Sponsor tools:** AG Grid (Money ledger page) · nothing else claimed.

**Links for the form:**
- Repo: https://github.com/SainathGaikwad/seen (MIT, licence visible in About) · mirror https://gitlab.com/seen-hackathons/seen
- Hosted demo: https://seen-unseen-xi.streamlit.app (Sponsor Desk, Fan feed, Money ledger) — PayPal sandbox; pay with a sandbox personal account
- Demo video (YouTube, < 3:00, public, no music, no third-party logos): `[link]`
- Write-up: `docs/paypal_sponsor_desk.md`

**Submission checklist (12 Nov):** registered on Devpost ✓ · sandbox credentials in Streamlit secrets and the hosted desk raising real sandbox orders ✓ · a committed ledger with real sandbox rows so the grid is not empty ✓ · video uploaded ✓ · AI tools and PayPal APIs named on the form ✓.

---

## E. Dates

| When | What |
| --- | --- |
| 11 Oct | Builder Cup registration + team formation closes |
| by 15 Oct | Cloud Run deployment live; new 3-min video recorded against it |
| 18 Oct | Builder Cup prototype submission deadline |
| 19 Oct – 6 Nov | Builder Cup evaluation; finalists announced 7 Nov; Demo Day Singapore 4 Dec |
| by 25 Oct | GitHub repo public, Nemotron deployment live, video uploaded to YouTube |
| 27 Oct, 18:30 IST | GitLab "Life After Code" submission deadline (winners ~16 Nov; demo must stay live until then) |
| 12 Nov, 12:00 PST (13 Nov 01:30 IST) | PayPal AI Hackathon submission deadline |
| 30 Oct, 22:30 IST | Nebius × NVIDIA submission deadline (demo must stay up to 15 Dec; winners ~11 Jan 2027) |
