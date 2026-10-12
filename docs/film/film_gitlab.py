"""SEEN x GitLab "Life After Code" film:  python docs/film/film_gitlab.py docs/rec_gitlab docs/rec_gitlab/narration docs/rec_gitlab/SEEN_gitlab_demo.mp4
rec_dir comes from docs/record_gitlab.py (GitLab's own UI and our app only: nothing to crop)."""
import sys
from pathlib import Path

from filmcut import BAND, compose

BLOCKS = ["hook", "problem", "blocked", "verified", "close"]
GAP_AFTER = {"hook": 0.8, "problem": 0.9, "blocked": 1.0, "verified": 1.0, "close": 3.0}


def shots_for(r, block):
    L = r.L
    if block == "hook":
        h0, h1 = r.content_span(L("app home") - 2.5, L("app story kit") - 2.0)      # the hosted app renders a beat after the mark
        k0, k1 = r.content_span(L("app story kit") - 2.5, L("repo home") - 2.5)
        return [(h0, h1, "app", "hold"), (k0, k1, "app", "hold")]
    if block == "problem":
        return [(L("repo home") - 2.0, L("show Life after code") + 0.3, "gitlab", "hold"),
                (L("check_kits.py") - 1.5, L("commit with the made-up number") - 2.5, "gitlab", "hold")]
    if block == "blocked":
        tracking = L("show Tracking issue", default=L("show I opened", default=L("issue #2") - 3.0))
        return [(L("commit with the made-up number") - 1.5, L("show She also scored") + 0.2, "gitlab"),
                (L("failed MR pipeline") - 2.5, L("failed MR pipeline") + 1.5, "gitlab"),
                (L("job claim-gate") - 5.0, L("job claim-gate") + 0.2, "gitlab"),
                (L("show Claim gate") - 6.0, tracking + 0.3, "gitlab", "hold"),
                (L("issue #2") - 1.0, L("issue #2") + 5.5, "gitlab")]
    if block == "verified":
        s = [(L("show She also took") - 3.5, L("show She also took") + 0.2, "gitlab"),
             (L("show Claim gate", 1) - 5.0, L("show editor::verified") + 0.3, "gitlab"),
             (L("MR top: green pipeline") - 3.0, L("MR top: green pipeline") + 0.5, "gitlab")]
        if r.has("MERGE clicked"):
            s.append((L("MERGE clicked") - 1.0, L("MERGE clicked") + 7.0, "gitlab"))
        pipe = L("main pipeline graph", default=L("latest pipeline graph", default=L("pipelines list") + 6.0))
        s += [(pipe - 3.5, pipe + 0.5, "gitlab"),
              (L("job govern-policies") - 5.0, L("job govern-policies") + 0.2, "gitlab"),
              (L("pipeline security tab") - 3.5, L("pipeline security tab") + 0.3, "gitlab"),
              (L("environments") - 3.5, L("environments") + 0.3, "gitlab"),
              (L("pipeline schedules") - 3.5, L("pipeline schedules") + 0.3, "gitlab")]
        if r.has("job monitor-production"):
            s.append((L("job monitor-production") - 5.0, L("job monitor-production") + 0.2, "gitlab", "hold"))
        return s
    if block == "close":
        h0, _ = r.content_span(L("app home") - 2.5, L("app story kit") - 2.0)
        end_shot = (h0, h0 + 0.4, "app", "hold")                                   # the home page, fully drawn, from the opening
        return [(L("flow in the AI Catalog") - 2.5, L("write-up") - 3.0, "gitlab"),
                (L("write-up") + 0.5, L("show What was added") + 0.3, "gitlab"),
                end_shot]
    raise KeyError(block)


def vf_for(r, kind, t_in):
    h = r.content_height(t_in)
    if h < 900:
        return f"crop=1600:{h}:0:0,scale=1920:{round(1920 * h / 1600)}:flags=lanczos,pad=1920:1080:0:0:color={BAND}"
    return "scale=1920:1080:flags=lanczos"


def captions_for(S, END):
    return [
        (S["hook"] + 0.3, S["hook"] + 7.5, "SEEN  ·  The Unseen XI  ·  stories in English, Hindi and Urdu from sourced facts"),
        (S["hook"] + 8.0, S["problem"] - 0.2, "Every number in every draft must match a fact in her bundle — or it is blocked"),
        (S["problem"] + 0.3, S["problem"] + 11.0, "gitlab.com/seen-hackathons/seen  ·  the claim gate runs in CI on every merge and as a Duo agent on every MR"),
        (S["problem"] + 11.5, S["blocked"] - 0.2, "scripts/check_kits.py — deterministic: every number in every format, checked against the facts"),
        (S["blocked"] + 0.3, S["blocked"] + 7.5, "MR !1 adds “She also scored 200 runs in the final”  —  her tournament total is 145"),
        (S["blocked"] + 8.0, S["blocked"] + 15.0, "Pipeline: the claim-gate job fails  →  red"),
        (S["blocked"] + 15.5, S["blocked"] + 27.0, "Editor-in-chief flow (Duo Agent Platform): runs the gate on the branch, posts the table, labels editor::blocked"),
        (S["blocked"] + 27.5, S["verified"] - 0.2, "Planner agent: issue #2 with the blocked row and the two allowed fixes  —  it cannot approve or merge"),
        (S["verified"] + 0.3, S["verified"] + 5.0, "The fix: “She also took 10 [F4] wickets”  —  a sourced fact"),
        (S["verified"] + 5.5, S["verified"] + 15.0, "16 / 16 verified  →  editor::verified  →  green pipeline  →  a person clicks Merge"),
        (S["verified"] + 15.5, S["verified"] + 24.0, "main: verify → package → secure → test → deploy → monitor"),
        (S["verified"] + 24.5, S["close"] - 0.2, "govern-policies: six policies, 0 failed  ·  SAST + secret detection  ·  environments  ·  monitor every 6 h"),
        (S["close"] + 0.3, S["close"] + 10.0, "Path B  ·  built for the hackathon: pipeline, claim-gate command, policies, monitor, Editor-in-chief flow v1.3.0"),
        (S["close"] + 10.5, S["close"] + 18.0, "Supervised autonomy: agents review, a person approves, a deterministic checker decides"),
        (S["close"] + 18.5, END - 0.3, "Women’s sport does not need more content. It needs to be seen. Correctly."),
    ]


if __name__ == "__main__":
    compose(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), BLOCKS, GAP_AFTER, 0.6, shots_for, vf_for, captions_for,
            prepare=lambda r: r.fit_drift("app home (end)", 4.0))
