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

**Try it out:** `[hosted demo URL — the Cloud Run service deployed with LLM_PROVIDER=nebius]` · `[GitHub repo]` · `[YouTube video]`

**How Nemotron / Token Factory are used (README section already written):** `README.md` → "How NVIDIA Nemotron and Nebius Token Factory are used".

**Feedback on Token Factory (required field — fill after your first real run):**
onboarding (minutes to first successful call), model catalogue clarity (ids as listed vs ids the API accepts), the `enable_thinking` behaviour, latency for 3k-token JSON answers, credits/promo flow, what you would change.

**Submission checklist (30 Oct):** public repo with `LICENSE` (MIT) visible in the About section ✓ · README with setup instructions and the Nemotron/Token Factory notes ✓ · working demo URL that stays up until 15 Dec ✓ · demo video <3:00 on YouTube, public ✓ · track chosen ✓ · feedback section ✓ · "significant updates" note: SEEN predates the submission period — list what was added during it: the Nemotron provider, the live rewrite loop, the Cloud Run deployment, the hosted demo.

---

## C. Dates

| When | What |
| --- | --- |
| 11 Oct | Builder Cup registration + team formation closes |
| by 15 Oct | Cloud Run deployment live; new 3-min video recorded against it |
| 18 Oct | Builder Cup prototype submission deadline |
| 19 Oct – 6 Nov | Builder Cup evaluation; finalists announced 7 Nov; Demo Day Singapore 4 Dec |
| by 25 Oct | GitHub repo public, Nemotron deployment live, video uploaded to YouTube |
| 30 Oct, 22:30 IST | Nebius × NVIDIA submission deadline (demo must stay up to 15 Dec; winners ~11 Jan 2027) |
