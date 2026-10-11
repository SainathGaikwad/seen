"""Record the GitLab "Life After Code" walkthrough: the Editor-in-chief flow on MR !1, the pipeline, the monitor.

GitLab pages need your login, so this uses a persistent browser profile kept under docs/rec_gitlab/profile:

    python docs\record_gitlab.py --login        # opens a browser: log in to gitlab.com once, then close the window
    python docs\record_gitlab.py                # records the walkthrough (headed, so you can watch) → docs/rec_gitlab/screen.webm
    python docs\record_gitlab.py --merge        # same, and clicks "Merge" on !1 on camera (the human approval shot)

Output: docs/rec_gitlab/screen.webm + nav_log.json (timestamps of every step, used to cut the film to the
narration in docs/gitlab_demo_script.md). Nothing is typed into GitLab except the merge click when asked for.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

GL = "https://gitlab.com/seen-hackathons/seen"
APP = "https://seen-unseen-xi.streamlit.app/~/+"
OUT = Path(__file__).resolve().parent / "rec_gitlab"
PROFILE = OUT / "profile"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1600, 900
LOGIN = "--login" in sys.argv
MERGE = "--merge" in sys.argv
T0 = time.time()
LOG: list[tuple[str, float]] = []
BAD_COMMIT = "5d4fe46b"     # the made-up number
FIX_COMMIT = "f027cb15"     # the sourced fact
FAILED_PIPELINE = "2935308898"


def mark(label: str) -> None:
    LOG.append((label, round(time.time() - T0, 1)))
    print(f"{time.time() - T0:6.1f}s  {label}")


def pause(s: float) -> None:
    time.sleep(s)


def smooth_scroll(page, dy, steps=14, dt=0.05):
    page.mouse.move(W // 2, H // 2)
    for _ in range(steps):
        page.mouse.wheel(0, dy / steps)
        time.sleep(dt)


def go(page, url: str, settle: float = 2.0, label: str | None = None):
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    time.sleep(settle)
    mark(label or url.replace(GL, ""))


def show(page, text: str, settle: float = 3.0):
    """Scroll the first element containing `text` into view (the notes on the MR are long)."""
    try:
        el = page.get_by_text(text, exact=False).first
        el.scroll_into_view_if_needed(timeout=8000)
        page.mouse.wheel(0, -120)
        time.sleep(settle)
        mark("show " + text[:40])
    except Exception as exc:
        mark(f"show {text[:30]}: {str(exc)[:60]}")


def click_job(page, name: str, settle: float = 4.0):
    """From a pipeline page, open the job with this name and scroll to the end of its log."""
    try:
        page.locator(f'a:has-text("{name}")').first.click(timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass
        time.sleep(1.5)
        page.keyboard.press("End")
        time.sleep(settle)
        mark("job " + name)
    except Exception as exc:
        mark(f"job {name}: {str(exc)[:60]}")


with sync_playwright() as p:
    if LOGIN:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, viewport={"width": W, "height": H})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://gitlab.com/users/sign_in")
        print("Log in to GitLab in the window, then close it (or wait: this exits once /dashboard loads).")
        for _ in range(600):
            time.sleep(1)
            try:
                if "gitlab.com/dashboard" in page.url or page.locator('[data-testid="user-avatar-content"], .header-user-avatar').count():
                    break
            except Exception:
                break
        time.sleep(2)
        try:
            ctx.close()
        except Exception:
            pass
        print("profile saved:", PROFILE)
        sys.exit(0)

    rec_start = time.time()
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, viewport={"width": W, "height": H},
                                               record_video_dir=str(OUT), record_video_size={"width": W, "height": H})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    # warm the heavy pages once (the composer trims this away)
    for warm in (f"{GL}/-/merge_requests/1", f"{GL}/-/pipelines", APP + "/"):
        page.goto(warm, wait_until="domcontentloaded", timeout=90000)
        time.sleep(1.5)
    T0 = time.time()
    json.dump({"offset": T0 - rec_start}, open(OUT / "offset.json", "w"))

    # ---- HOOK: the live app, a kit with its fact bundle
    go(page, APP + "/", 2.5, "app home")
    smooth_scroll(page, 600, steps=18, dt=0.08)
    pause(2.0)
    go(page, APP + "/Story_Kit", 2.5, "app story kit")
    smooth_scroll(page, 700, steps=18, dt=0.08)
    pause(3.0)

    # ---- PROBLEM: the repo, the README section, the gate's code
    go(page, GL, 2.5, "repo home")
    show(page, "Life after code: the GitLab pipeline", 4.0)
    go(page, f"{GL}/-/blob/main/scripts/check_kits.py", 2.0, "check_kits.py")
    smooth_scroll(page, 500, steps=14, dt=0.08)
    pause(3.0)

    # ---- BLOCKED: the bad commit, the red pipeline, the editor's note, the label, the planner's issue
    go(page, f"{GL}/-/commit/{BAD_COMMIT}", 2.0, "commit with the made-up number")
    show(page, "She also scored 200 runs in the final", 4.0)
    go(page, f"{GL}/-/pipelines/{FAILED_PIPELINE}", 3.0, "failed MR pipeline")
    pause(2.0)
    click_job(page, "claim-gate", 5.0)
    go(page, f"{GL}/-/merge_requests/1", 3.0, "MR !1 overview")
    show(page, "Claim gate — BLOCKED", 6.0)
    smooth_scroll(page, 500, steps=14, dt=0.08)
    pause(3.0)
    show(page, "editor::blocked", 2.5)
    show(page, "I opened a tracking issue", 3.0)
    go(page, f"{GL}/-/work_items/2", 2.5, "issue #2")
    smooth_scroll(page, 300, steps=10, dt=0.08)
    pause(4.0)

    # ---- VERIFIED: the fix, the PASS note, the green pipeline, the human's merge
    go(page, f"{GL}/-/commit/{FIX_COMMIT}", 2.0, "commit with the sourced fact")
    show(page, "She also took 10 [F4] wickets", 4.0)
    go(page, f"{GL}/-/merge_requests/1", 3.0, "MR !1 overview again")
    show(page, "Claim gate — PASS", 5.0)
    show(page, "editor::verified", 3.0)
    page.keyboard.press("Home")
    pause(3.0)
    mark("MR top: green pipeline, ready to merge")
    if MERGE:
        try:
            page.get_by_role("button", name=re.compile(r"^Merge", re.I)).first.click(timeout=10000)
            mark("MERGE clicked")
            pause(6.0)
        except Exception as exc:
            mark(f"merge button: {str(exc)[:60]}")
    else:
        pause(3.0)

    # ---- LIFECYCLE: the main pipeline, policies, security, environments, schedule, monitor
    go(page, f"{GL}/-/pipelines", 3.0, "pipelines list")
    try:
        page.locator('a[href*="/-/pipelines/"]:has-text("#")').first.click(timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass
        pause(4.0)
        mark("latest pipeline graph")
        pipeline_url = page.url
    except Exception as exc:
        mark(f"pipeline open: {str(exc)[:60]}")
        pipeline_url = f"{GL}/-/pipelines"
    click_job(page, "govern-policies", 5.0)
    go(page, pipeline_url.split("?")[0].rstrip("/") + "/security", 4.0, "pipeline security tab")
    go(page, f"{GL}/-/environments", 4.0, "environments")
    go(page, f"{GL}/-/pipeline_schedules", 4.0, "pipeline schedules")
    go(page, f"{GL}/-/pipelines?source=schedule", 3.0, "scheduled runs")
    try:
        page.locator('a[href*="/-/pipelines/"]:has-text("#")').first.click(timeout=10000)
        time.sleep(2.0)
        click_job(page, "monitor-production", 5.0)
    except Exception as exc:
        mark(f"monitor job: {str(exc)[:60]}")

    # ---- CLOSE: the flow in the catalog, the write-up, the live app
    go(page, "https://gitlab.com/explore/ai-catalog/flows/1016614", 3.0, "flow in the AI Catalog")
    smooth_scroll(page, 900, steps=24, dt=0.08)
    pause(4.0)
    go(page, f"{GL}/-/blob/main/docs/gitlab_life_after_code.md", 2.5, "write-up")
    show(page, "What was added during the submission period", 5.0)
    go(page, APP + "/", 5.0, "app home (end)")
    mark("end")

    json.dump(LOG, open(OUT / "nav_log.json", "w"), indent=1)
    video_path = page.video.path()
    ctx.close()
    final = OUT / "screen.webm"
    if final.exists():
        final.unlink()
    shutil.move(video_path, final)
print("recorded:", OUT / "screen.webm")
