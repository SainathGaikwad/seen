# SEEN on GitLab — life after code

*Entry for the GitLab "Life After Code" hackathon (Path B: bring your own project · level of autonomy: Supervised).*

SEEN finds the eleven women cricketers whose performance most exceeds the attention they get and turns each into a
fact-locked story kit in the fan's language. Writing the stories is the easy part — a model does it in seconds.
What makes the product publishable is everything that happens **after** the code and the prose exist: every number
in every draft has to match a sourced fact, in English, Hindi and Urdu, on every merge, on every deploy, and the
live demo has to stay up. That post-code discipline is what we moved onto GitLab.

## What runs on GitLab

**The Editor-in-chief flow** (`.gitlab/duo/flows/editor_in_chief.yml`, registered in the AI Catalog) reviews every
merge request on its own:

1. reads the MR, runs the deterministic claim gate (`scripts/check_kits.py --changed origin/main --translations`)
   inside its sandbox, and posts one review note with the full table — every athlete, language and format, PASS or
   BLOCKED, with the number that failed and why;
2. labels the MR `editor::verified` or `editor::blocked` through a quick action;
3. when something is blocked, a second agent files a work item that links the MR, lists the blocked numbers and the
   two allowed fixes (use a number that is in the bundle, or add a sourced fact), and links it back from the MR.

The agent never approves and never merges. A human editor approves the outcome — that is the "supervised" level —
and the deterministic checker, not the model, decides what is publishable.

**The pipeline** (`.gitlab-ci.yml`) covers the post-code stages the hackathon scores:

| Stage | What runs | Lifecycle |
|---|---|---|
| verify | pytest; the claim gate over all kits and translations (artifact: `claim_gate.md`); six governance policies (`scripts/policy_check.py`): MIT licence present, no tracked secrets, stored check results agree with a fresh run, every fact names its source, Unseen XI selection constraints hold, simulated numbers stay labelled | verify · govern |
| package | Docker image → GitLab container registry (`:sha`, `:latest`, `:tag`) | package |
| secure | SAST, secret detection, dependency scanning, container scanning (GitLab templates) | secure |
| release | tagged releases with the live-demo and image links (`release-cli`) | release |
| deploy | production is configured by pushing the verified commit to GitHub, from which Streamlit Community Cloud redeploys; a headless visit then verifies the Unseen XI renders; a manual Cloud Run job deploys the same image on Google Cloud | configure · release |
| monitor | scheduled every six hours: a real browser visit that wakes the demo if it sleeps and opens an *incident* issue when it does not come up | monitor |
| MRs | the Editor-in-chief flow; merge requires a green pipeline (claim gate + policies) and a human approval | plan · create · govern |

Nine stages touched: plan, create, verify, package, secure, release, configure, monitor, govern.

## Why this is the right job for an agent

The claim gate is deterministic; the reasoning an editor needs around it is not. "Which of these 116 rows changed in
this MR, what exactly is wrong with `24 overs`, what should the author do, and is this worth a work item?" is the
kind of judgement a language model does well — as long as it cannot overrule the gate. So the flow is built that
way: the model runs the checker, reads its output and explains it; the YAML gives it no tool that could approve or
merge; and the pipeline re-runs the same gate on every merge regardless of what any agent said.

## What was added during the submission period (Path B)

SEEN existed before October 2026 (GitHub: SainathGaikwad/seen, MIT). Built for this hackathon, on or after 5 October:
the GitLab project and pipeline (`.gitlab-ci.yml`), the claim-gate CLI (`scripts/check_kits.py`), the governance
policies (`scripts/policy_check.py`), the monitor and incident scripts (`docs/keep_awake.py`,
`scripts/raise_incident.py`), the Editor-in-chief flow and its registration, and the GitHub → Streamlit deploy step.

Original project: https://github.com/SainathGaikwad/seen · Live demo: https://seen-unseen-xi.streamlit.app

## Runbook (maintainers)

- Push to **GitLab** (`gitlab.com/seen-hackathons/seen`); the `deploy-production` job pushes `main` to GitHub.
  Do not push to GitHub directly any more, or the histories diverge.
- CI/CD variables: `GITHUB_TOKEN` (fine-grained, contents read/write on the GitHub repo; masked) for the deploy
  step; `SEEN_BOT_TOKEN` (project access token, `api` scope; masked) so the monitor can open incident issues;
  `GCP_PROJECT` + `GCP_SA_KEY` only for the optional Cloud Run job.
- Pipeline schedule: `monitor-production` every six hours (CI/CD → Schedules).
- Merge request settings: pipelines must succeed; at least one approval; the Editor-in-chief flow enabled with the
  "merge request created" and "merge request ready" triggers.
- Local: `python scripts/check_kits.py` and `python scripts/policy_check.py` run in seconds and need no API key.
