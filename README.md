# SEEN — visibility intelligence for women's cricket

**The Unseen XI:** every week, the eleven women cricketers whose performance most exceeds the attention they receive — found in public data, turned into fact-locked story kits in the fan's language, routed through channels ICC already owns, and measured.

Built for the ICC × Ignyte Global Hackathon 2026 (Prototype track); also entered in the Google Cloud **AI Builder Cup 2026** (theme: Media, Content & Digital Experiences — hosted on Cloud Run, Gemini for prose and translation) and the **Nebius × NVIDIA Global AI Hackathon** (NVIDIA Nemotron 3 on Nebius Token Factory as the writing model). Everything runs from public, keyless data: Cricsheet ball-by-ball files, Wikidata, Wikimedia pageviews and GDELT. An LLM key is optional.

**Live demo:** https://seen-unseen-xi.streamlit.app · **Code:** https://github.com/SainathGaikwad/seen · Decks and submission notes in `docs/`.

## What it does (one loop)

```
Cricsheet JSON ──► Women's Cricket Graph (DuckDB) ──► narrative patterns ──► significance
Wikidata + Wikipedia pageviews + GDELT ──► attention index ──► visibility gap (OLS residual)
        ──► Unseen XI (constrained selection) ──► fact-locked story kits (8 formats) ──► claim checker
        ──► localisation (glossary-locked, re-checked) ──► Creator Club / app cards / commentary / fan feed
        ──► impact: attention lift vs matched controls, funnel, breadth ──► back into selection weights
```

Design rules: **no number is written by a model** (every figure is inserted from the graph with a fact ID and re-verified); eleven athletes a week, not a firehose; selection is explainable and editor-overridable; athletes can opt out; clips are linked, never embedded, until ICC's own rights pipeline attaches them.

## Quick start

**Windows:** double-click `run_windows.bat`. It creates a virtual environment, installs the requirements, loads Cricsheet, runs the live pipeline and opens the app. Modes: `run_windows.bat load` / `run` / `app` / `fixture`. Close the app before re-running the pipeline (DuckDB allows one writer at a time).

**macOS / Linux (~15 minutes):**

```bash
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # optional: add an LLM key for prose + translation

# 1) Load public data: downloads Cricsheet zips (women's T20Is, ODIs, WPL, WBBL, Hundred) + the people register
python -m seen.pipeline load --source cricsheet -v

# 2) Run the intelligence pipeline with LIVE attention data (Wikidata → pageviews → GDELT), build kits + translations
python -m seen.pipeline run --attention live -v

# 3) Open the app (9 screens)
streamlit run app/Home.py
```

No open network? `--attention fixture` produces a **clearly labelled synthetic** attention set so the UI can be developed; never present it as real. Some corporate networks block cricsheet.org / wikimedia.org / wikidata.org / gdeltproject.org — use a home network, a Codespace or a small VPS.

The analysis window is set in `config.yaml` (`window:`): an event (default: ICC Women's T20 World Cup 2026) or rolling days (`kind: days`, e.g. the last 28 days across all loaded competitions — the between-events mode).

## LLM modes

| `LLM_PROVIDER` | Behaviour |
| --- | --- |
| `none` (default) | TEMPLATE mode: deterministic, fact-locked text for all eight formats; no translation (English kit shown with a clear status) |
| `gemini` / `nebius` / `anthropic` / `openai` | The model rewrites three formats as natural prose and translates kits with a locked cricket glossary; **every output is re-run through the claim checker** and falls back to the template if any number cannot be matched |
| `nebius` | NVIDIA **Nemotron 3** open models (Super 120B by default; Nano 30B and 3.5 Lightning as fallbacks) served by **Nebius Token Factory** through its OpenAI-compatible API (`NEBIUS_API_KEY`, optional `NEBIUS_MODEL`). Reasoning is switched off for JSON answers; any `<think>` block is stripped |

Set `localisation.tts: true` and `pip install gTTS` for demo audio.

In the app, the **Story kit** page has *Rewrite with the model*: a live call to the configured model for one format, with an optional editorial angle ("for a first-time fan in Lahore"). The draft replaces the text only if the claim checker passes; a blocked draft is shown with the numbers it could not match. The banner on every page names the pipeline's model and the live model.

## Run it on Google Cloud Run

`deploy\deploy_cloudrun.bat YOUR_PROJECT_ID` (Windows) or `bash deploy/deploy_cloudrun.sh YOUR_PROJECT_ID` builds the `Dockerfile` with Cloud Build, stores the API key from `.env` in Secret Manager and deploys the app with the analysed data baked in. Details, costs and clean-up: [deploy/cloudrun.md](deploy/cloudrun.md). The same image with `LLM_PROVIDER=nebius` is the Nemotron-powered deployment.

## How NVIDIA Nemotron and Nebius Token Factory are used

- `seen/llm.py` → provider `nebius`: every story-kit prose rewrite, every live *Rewrite with the model* call and every translation goes to `https://api.tokenfactory.nebius.com/v1/chat/completions` with `nvidia/nemotron-3-super-120b-a12b` (falls back to `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, then `nvidia/Nemotron-3_5-Lightning`).
- The model writes from a **fact bundle only** and must cite every number (`[F3]`); `seen/stories/claim_check.py` re-verifies each figure against the bundle, so a hallucinated statistic is blocked before it reaches a creator, commentator or fan. That is the point of pairing an open model with a deterministic checker.
- Translations (`seen/stories/localize.py`) are glossary-locked and re-checked the same way; the fan feed serves them in the fan's language.
- Prompts and answers are cached by content hash (`data/cache/llm/`), so re-runs cost nothing and a pipeline run needs ~3 calls per athlete.

## The nine screens (app/)

| # | Page | What it shows |
| --- | --- | --- |
| S1 | Home — Unseen XI | This week's eleven with impact rank, attention rank, gap and "why now"; selection notes; gap explorer for every athlete |
| S2 | Athlete profile | Daily article views by language vs the expected band; match markers; significance breakdown |
| S3 | Story opportunity | Detected patterns, evidence table with fact IDs and sources, score breakdown, audience fit, athlete-safety gate (consent) |
| S4 | Story kit | Eight formats, inline citations, claim-check panel, edit → re-check → approve; a live "paste a made-up number" demo |
| S5 | Localisation | Languages ranked by opportunity, side-by-side translation, re-check status, optional audio |
| S6 | Route & publish | Channel checklist (Creator Club, app card, commentary, social, Women's Cricket Week, Gemini export, fan feed), publish log |
| S7 | Creator brief | Creator-facing brief, assets, clip slot ("ICC rights required"), post-link attribution |
| S8 | Fan feed | Athlete-first cards with exploration slots, read / quiz / follow / share, language toggle; every action logged |
| S9 | Impact dashboard | Attention lift vs matched controls (difference-in-differences), funnel (real or **labelled simulated**), breadth, XI reach, stories being missed, weights in use |

## Data and licences

- **Cricsheet** (cricsheet.org): ball-by-ball JSON, ODC-BY 1.0 — attribute "Cricsheet (cricsheet.org)".
- **Wikidata** (CC0) for identity (ESPNcricinfo ID → article titles per language); **Wikimedia Pageviews API** (public, no key); **GDELT DOC 2.0** (public, no key). Set a descriptive `SEEN_USER_AGENT`.
- Not used, by design: ESPNcricinfo/Cricbuzz scraping (terms prohibit it), any athlete health data, any private social data.
- `data/manual/consent.csv` (`player_id,consent`), `featured_log.csv`, `names.csv` (`player_id,display_name`) are editor inputs.

## Method notes (short)

- **Impact** = runs + 20 × bowler-credited wickets (z-score variant ranks the same players; Spearman 0.99).
- **Significance** = 0.35·rarity + 0.20·stakes + 0.30·magnitude + 0.15·arc; rarity = 1/(1 + prior occurrences of the pattern in the graph's history); weights in `config.yaml`.
- **Attention** = log(1 + article views across tracked editions in the window); baseline = 60 days before.
- **Gap** = expected − actual on the log scale, where expected comes from a performance-only line (OLS of attention on significance): "how much attention did athletes who played like her receive?" A second, structural line adds log(market tier) and log(1 + baseline daily views) and splits every gap into a *structural* part (small market, low prior fame) and an *anomaly* (unexplained). The XI is selected on the primary gap; athletes without an article are the maximum gap and are capped in the XI (`max_no_article`).
- **Unseen XI** = greedy selection by gap with constraints: ≤3 per country, ≥3 from outside IND/ENG/AUS, ≥4 batters and ≥4 bowlers (all-rounders count for both), consent, 14-day cooldown, top-60 by impact.
- **Lift** = (featured after − before) − mean(control after − before) on daily views, controls = 5 athletes of similar significance in the same market tier not featured.

## Project layout

```
seen/ingest        cricsheet.py (real loader) · mirror.py (dev only) · wikidata.py · pageviews.py · gdelt.py
seen/intelligence  windows.py · patterns.py (10 narrative patterns) · significance.py · attention.py · gap.py · unseen_xi.py
seen/stories       compiler.py (8 formats, template + LLM) · claim_check.py · localize.py
seen/fans          feed.py (ranking with exploration slots, event log)
seen/impact        measure.py (difference-in-differences, funnel, breadth, simulated funnel generator)
seen/pipeline.py   CLI · app/ Streamlit pages · tests/ unit tests (pytest -q)
```

## Honesty notes

- Performance figures are real (Cricsheet). Re-derive any number before publishing it; the mirror loader exists only for offline development.
- Attention numbers are real only when produced with `--attention live`; the app banner says which mode produced the data you are looking at.
- The fan funnel is simulated unless real events were logged in the app; the dashboard labels the source.
- Nothing here has been piloted with ICC; "pilot opportunities" are the hackathon's own words.
