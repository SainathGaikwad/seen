## What it does, and the problem it solves

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get and turns each into a story kit — a 60-second script, social posts, an article — in English, Hindi and Urdu, written by a model from a bundle of sourced facts.

The audience is small newsrooms, creators and federations that publish athlete statistics every week without a fact-checking desk. Their failure mode is not bad prose; it is a plausible number that no fact supports, and one of those costs a publication its trust. Writing the draft takes a model seconds. Everything after the draft — checking every number against a sourced fact, in every language, on every merge and every deploy, and keeping the live demo up — is the product, and that is what we moved onto GitLab.

## How we used GitLab to automate the post-code lifecycle

- **Plan / create / govern — the Editor-in-chief flow** (`.gitlab/duo/flows/editor_in_chief.yml`, registered in the AI Catalog, triggered on merge request created / marked ready / mention / reviewer assignment). The first agent reads the MR, runs the deterministic claim gate on the branch (`scripts/check_kits.py --changed origin/main --translations`), posts one review note with the full table (every athlete, language and format — PASS or BLOCKED with the failing number), and applies `editor::verified` or `editor::blocked` through a quick action. When anything is blocked, a router hands over to a planner agent that reads the note, files a work item listing the blocked rows and the two allowed fixes, and links it from the MR. The toolsets contain no approve or merge tool; the human editor approves the outcome.
- **Verify** — `unit-tests`, `claim-gate` (the same gate over all kits and translations; `claim_gate.md` exposed on the MR) and `govern-policies` (six policies: MIT licence present, no tracked secrets, stored check results agree with a fresh run, every fact names its source, the Unseen XI selection constraints hold, simulated numbers stay labelled).
- **Package** — container image to the GitLab registry (`:sha`, `:latest`, `:tag`). **Secure** — SAST, secret detection, dependency scanning, container scanning from GitLab's templates. **Release** — tagged releases with the live-demo and image links via release-cli.
- **Configure / deploy** — production is configured by pushing the verified commit to the hosting repository, from which Streamlit Community Cloud redeploys; a headless browser then verifies the Unseen XI renders (`verify-production`). A manual job deploys the same image to Google Cloud Run.
- **Monitor** — a pipeline schedule every six hours visits the demo like a reader, wakes it if it has gone to sleep, and opens an *incident* issue when it does not come up.

Merge requests require a green pipeline (claim gate + policies) and a human approval. Nine stages touched: plan, create, verify, package, secure, release, configure, monitor, govern.

## The verified run

Merge request !1 adds one sentence to Hayley Matthews' video script: *she scored 200 runs in the final*. Her tournament total is 145. The pipeline runs the claim gate and goes red; the Editor-in-chief flow posts the table (16 formats, 15 verified, 1 blocked — 200 is not in any fact), labels the MR `editor::blocked`, and the planner files work item #2 with the blocked row and the two allowed fixes. The author swaps the number for a sourced fact (10 wickets, fact F4); the editor runs again — 16 of 16 verified, `editor::verified`, green pipeline — and a person merges. The merge starts the main pipeline: tests, the gate, six policies, a container image, security scans, deploy and monitor. The demo video walks through exactly this run.

## Why an agent, and why supervised

The gate is deterministic; the judgement around it is not ("which rows changed in this MR, what exactly is wrong with `24 overs`, what should the author do, is this worth a work item"). A language model does that well as long as it cannot overrule the gate — so the flow runs the checker and explains it, has no tool that could approve or merge, and the pipeline re-runs the same gate on every merge regardless of what any agent said. Level of autonomy: **supervised**.

## What we added during the submission period (Path B)

SEEN predates October (MIT, https://github.com/SainathGaikwad/seen). Built for this hackathon, on or after 5 October: the GitLab project and pipeline (`.gitlab-ci.yml`), the claim-gate CLI (`scripts/check_kits.py`), the governance policies (`scripts/policy_check.py`), the monitor and incident scripts (`docs/keep_awake.py`, `scripts/raise_incident.py`), the Editor-in-chief flow and its AI Catalog registration (v1.3.0), the GitHub → Streamlit deploy step and the production verification, and the merge-request workflow (scoped labels, triggers, service account). Everything else in the repository predates October.

## Where to look

- Repository, pipelines, the merge request and the flow: https://gitlab.com/seen-hackathons/seen (merge request !1, work item #2, CI/CD → Pipelines, Schedules)
- The flow in the AI Catalog: https://gitlab.com/explore/ai-catalog/flows/1016614
- Live app (monitored every six hours): https://seen-unseen-xi.streamlit.app
- Write-up with the flow sessions and runbook: `docs/gitlab_life_after_code.md` in the repository

The demo video's narration is an open-source voice (Kokoro); no music, no third-party material.
