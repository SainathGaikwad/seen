# SEEN × GitLab "Life After Code" — demo video script (under 3:00)

Narration ≈ 410 words ≈ 2:50 at a calm pace (145 words a minute) — do not add anything. Read one block per take, pause a second between blocks, do not rush the
numbers. Screen recording follows the shot list below; the film is cut to the narration afterwards.

Rules from the hackathon page: under three minutes, public on YouTube, shows the automation running end to end,
explains the problem, the audience and why it matters, **no third-party trademarks or copyrighted music**. So: no
music, no logos other than GitLab's own UI and our app, and keep the Streamlit footer out of the frame where you can.

---

**HOOK (0:00)**
This is SEEN. It finds the eleven women cricketers whose performance most exceeds the attention they get, and writes
their stories in three languages from sourced facts. A model drafts in seconds. Everything after the draft is the
product — because one plausible wrong number costs a newsroom its trust.

**PROBLEM AND AUDIENCE (0:18)**
Our audience: small newsrooms, creators and federations publishing athlete statistics weekly with no fact-checking
desk. Their failure mode is not bad prose; it is a number no fact supports. So that discipline now runs
on GitLab: a deterministic claim gate checks every number in every draft against the athlete's fact bundle — in the
pipeline on every merge, and through a Duo agent on every merge request.

**BLOCKED (0:40)**
This merge request adds one sentence to Hayley Matthews' video script: she scored two hundred runs in the final.
False: her tournament total is one hundred and forty-five. The pipeline runs the claim gate and goes red. The
Editor-in-chief flow starts on its own: it reads the merge request, runs the gate on the branch, posts the full
table — sixteen formats, three languages, one blocked: two hundred is not in any fact — and labels the request
*editor blocked*. The planner agent files a work item with the blocked row and the two allowed fixes. The agent cannot
approve or merge. The human editor sees a red pipeline, a red label and a linked issue.

**VERIFIED AND MERGED (1:28)**
The author swaps the number for a sourced fact — ten wickets, fact F4 — and pushes. The editor runs again: sixteen
of sixteen verified, the label flips to *editor verified*, the pipeline is green. Now, and only now, a person clicks
merge. Main runs the rest of the lifecycle: tests, the claim gate, six governance policies, a container image,
GitLab's security scans, a tagged release, and a deploy that pushes the verified commit to the hosting repository and
checks the live app. Every six hours a scheduled monitor visits the demo, wakes it if it sleeps, and opens an
incident if it is down.

**CLOSE (2:12)**
Path B: SEEN existed before October; the pipeline, the claim-gate command, the policies, the monitor and the
Editor-in-chief flow were built for this hackathon — nine stages touched, plan to govern. Supervised autonomy: the
agents run the review on their own, a person approves the outcome, and a deterministic checker — not the model —
decides what is publishable. Women's cricket does not need more content. It needs to be seen. Correctly.

---

## Shot list (record each in one pass, 1920×1080, browser zoom 110–125 %, no music)

| Block | Screen (URL) | What to show |
| --- | --- | --- |
| Hook | https://seen-unseen-xi.streamlit.app | Unseen XI cards; open Matthews' story kit; scroll the fact bundle (F1…F21) |
| Problem | https://gitlab.com/seen-hackathons/seen | README section "Life after code"; then `scripts/check_kits.py` top of file |
| Blocked | https://gitlab.com/seen-hackathons/seen/-/merge_requests/1 | **Changes** tab: the `+ She also scored 200 runs in the final.` line; **Pipelines** tab: the first (failed) pipeline, open the failed `claim-gate` job log, then "View exposed artifact"; back to **Overview**: the Editor-in-chief note with the table and the ⛔ row; the system line "added editor::blocked label"; the planner note → open issue #2 |
| Verified | same MR | the second commit `Story kit: use a sourced fact for the closing line` (Commits tab, open the diff); Overview: the PASS note, "added editor::verified label", green pipeline; click **Merge** (this is the human approval — do it on camera) |
| Lifecycle | https://gitlab.com/seen-hackathons/seen/-/pipelines | open the main pipeline that the merge started: the stage graph verify → package → secure → release → deploy → monitor; open `govern-policies` log (six policies, 0 failed); Security → Vulnerability report or the pipeline **Security** tab; Deployments → Environments → production; CI/CD → Schedules (every 6 hours); one `monitor-production` job log ending with `ok:` |
| Close | https://gitlab.com/explore/ai-catalog/flows/1016614 | the flow page (v1.3.0), scroll the YAML to the `toolset` of the editor (no approve/merge tool) and the router BLOCKED → planner; then `docs/gitlab_life_after_code.md` "What was added during the submission period"; end on the live app |

Timing targets: Hook 0:00–0:18 · Problem 0:18–0:40 · Blocked 0:40–1:28 · Verified 1:28–2:12 · Close 2:12–2:45.

## Recording tips

- Record the GitLab pages at the end, after the merge, so the main pipeline and the release exist. If you tag
  `v0.2.0` after the merge (`git tag -a v0.2.0 -m "Unseen XI, claim-gated" && git push gitlab v0.2.0`) the
  **Releases** page has a real release to show for the release stage.
- Hover slowly; the cut uses 2–4 s per screen. A 4–6 minute raw recording is plenty.
- Narration: phone or laptop mic, quiet room, one take per block; send the audio and the raw screen recording to
  Sainath (`docs/rec_gitlab/`, git-ignored) and the film is cut from them.
