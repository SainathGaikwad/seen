# SEEN demo video — narration script, October 2026 (two variants)

Same film, two voice-overs: **(G)** for the Google Cloud AI Builder Cup (Gemini, Cloud Run) and **(N)** for the
Nebius × NVIDIA hackathon (Nemotron on Nebius Token Factory). Only the bracketed lines differ. ~430 words ≈ 2:55 at
a calm pace; the screen recording is timed to the six blocks afterwards, so pause about a second between blocks
and do not rush the numbers.

Recording, as last time: phone or laptop camera, quiet room, read from this page, one take per block is fine
(we cut the gaps). Record **both variants in one session** — the (N) lines are only four sentences. Send the
MP4(s) and Sainath drops them in `docs/`.

---

**HOOK (0:00)**
This is SEEN. Every week it finds the eleven women cricketers whose performance most exceeds the attention they get. Take Hayley Matthews. In the 2026 Women's T20 World Cup she finished first by impact — and fifty-second by attention. Six thousand article views, against fifty-eight thousand for Ellyse Perry.

**PROBLEM (0:22)**
Women's cricket does not have a content problem — the 2025 World Cup drew five billion video views. It has an attention problem. How an athlete played explains twenty per cent of the attention she receives. Who she already was — her market, her prior fame — explains eighty-one. That gap is measurable, athlete by athlete. So we measure it.

**PRODUCT (0:48)**
SEEN turns ball-by-ball data into a graph, finds ten kinds of story, scores how rare and how big each one is, and reads attention from Wikipedia in eight languages. The residual is her gap, and the Unseen XI is picked under editorial rules: at most three per country, at least three from outside India, England and Australia, consent-gated. For each athlete, **(G)** Gemini **(N)** NVIDIA Nemotron, served by Nebius Token Factory, writes the story kit — a sixty-second script, social posts, an article — from a bundle of sourced facts. The editor sees every fact behind every number.

**TRUST (1:30)**
Here is the part that makes a model safe to publish. I ask **(G)** Gemini **(N)** Nemotron for a fresh draft with an angle — for a first-time fan in Lahore. It answers in seconds, and every number is checked against the fact bundle before the draft replaces the text. Now I type a number that is not a fact — two hundred runs in the final — and the claim checker blocks it. Nothing unverifiable leaves this screen. The same checker runs on the Hindi and Urdu translations.

**FANS (2:06)**
A fan in Mumbai sees Matthews in Hindi, with the reason she is here, on a card she can read, follow and share. Every action is logged, and the impact dashboard measures attention lift against five matched athletes who were not featured — so the loop learns what converts.

**CLOSE (2:38)**
**(G)** SEEN runs on Google Cloud: one container on Cloud Run, Gemini behind it, every API response cached.
**(N)** SEEN runs as one container, with NVIDIA Nemotron on Nebius Token Factory behind it, every API response cached.
Eleven athletes a week, verified fact by fact, in the fan's language. Women's cricket does not need more content. It needs to be seen.

---

## Shot list (what the screen shows under each block)

| Block | Screen |
| --- | --- |
| Hook | Home: the Unseen XI cards, scroll to Matthews, then the scatter (performance vs attention) |
| Problem | Scatter: the expected line, Perry above it, Matthews below; drift to the gap explorer |
| Product | Athlete profile (views vs expected band) → Story opportunity (patterns, facts with IDs) → Story kit tabs |
| Trust | Story kit: *Rewrite with the model* → angle "for a first-time fan in Lahore" → Generate and verify → PASS; then type "She also scored 200 runs in the final." → Re-check → BLOCKED; Localisation (Hindi, checks) |
| Fans | Fan feed in Hindi (Matthews card: read, follow, share) → Impact dashboard (lift vs controls, funnel) |
| Close | Home again, slow drift to the scatter; closing caption |

The screen is recorded against the deployed Cloud Run URL (Gemini service for (G), the Nemotron service for (N)), so the
model call in the Trust block is real in both films.
