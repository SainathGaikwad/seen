"""Record the GitLab "Life After Code" walkthrough: the Editor-in-chief flow on MR !1, the pipeline, the monitor.

GitLab pages are public, but the Merge click needs your login, so this uses a persistent browser profile kept under
docs/rec_gitlab/profile:

    python docs\record_gitlab.py --login        # opens a browser: log in to gitlab.com, wait for your dashboard, close it
    python docs\record_gitlab.py                # records the walkthrough (headless: exact 1600x900) → docs/rec_gitlab/screen.webm
    python docs\record_gitlab.py --merge        # same, and clicks "Merge" on !1 on camera (the human approval shot)
    python docs\record_gitlab.py --headed       # watch it (the window may be too short for 1600x900 on a laptop screen)

Output: docs/rec_gitlab/screen.webm + nav_log.json (timestamps of every step; docs/film/film_gitlab.py cuts the film to
the narration in docs/gitlab_demo_script.md). Nothing is typed into GitLab except the Merge click when asked for.
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
HEADED = "--headed" in sys.argv
T0 = time.time()
LOG: list[tuple[str, float]] = []
BAD_COMMIT = "5d4fe46b"          # the made-up number
FIX_COMMIT = "f027cb15"          # the sourced fact
FAILED_PIPELINE = "2935308898"   # the MR pipeline that went red on the made-up number
MAIN_PIPELINE = "2935681300"     # a full main pipeline: verify → package → secure → test → deploy → monitor
SCHEDULED_PIPELINE = "2935778946"  # a scheduled run (monitor-production)
for a in sys.argv[1:]:
    if a.startswith("--pipeline="):
        MAIN_PIPELINE = a.split("=", 1)[1]


def mark(label: str) -> None:
    LOG.append((label, round(time.time() - T0, 1)))
    print(f"{time.time() - T0:6.1f}s  {label}", flush=True)


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


def show(page, target, settle: float = 3.0, label: str | None = None, wait: float = 45.0):
    """Scroll the first element matching `target` (text or a locator) into view; waits for it to exist first,
    because GitLab fills the MR activity several seconds after the page is up."""
    name = label or (target if isinstance(target, str) else "element")
    try:
        if isinstance(target, str):
            loc = page.get_by_text(target, exact=False).first
        elif isinstance(target, re.Pattern):
            loc = page.get_by_text(target).first
        else:
            loc = target.first
        loc.wait_for(state="attached", timeout=wait * 1000)
        loc.scroll_into_view_if_needed(timeout=8000)
        page.mouse.wheel(0, -120)
        time.sleep(settle)
        mark("show " + name[:40])
    except Exception as exc:
        mark(f"show {name[:30]}: {str(exc)[:60]}")


def click_job(page, name: str, settle: float = 4.0):
    """From a pipeline page, open the job with this name and scroll to the end of its log."""
    try:
        page.locator(f'a:has-text("{name}")').first.click(timeout=15000)
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


def fresh_page(ctx):
    """A page we open ourselves, emulated at W×H from the start (the profile's own first tab is sized by the window)."""
    page = ctx.new_page()
    for other in list(ctx.pages):
        if other is not page:
            try:
                other.close()
            except Exception:
                pass
    page.set_viewport_size({"width": W, "height": H})
    return page


def logged_in(page) -> bool:
    """On gitlab.com a visitor sees "Sign in" in the top bar; a logged-in user sees their avatar instead."""
    try:
        if "users/sign_in" in page.url or page.get_by_role("link", name=re.compile(r"^Sign in$")).count():
            return False
        return page.locator('[data-testid="user-avatar-content"], .header-user-avatar, [data-testid="user-menu-toggle"], '
                            '[data-testid="user-dropdown"], .gl-avatar').count() > 0
    except Exception:
        return False


with sync_playwright() as p:
    if LOGIN:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, viewport={"width": W, "height": H})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://gitlab.com/users/sign_in")
        print("Log in to GitLab in the window. This closes it by itself once your dashboard (your avatar) is there.")
        ok = False
        for _ in range(900):
            time.sleep(1)
            try:
                if "gitlab.com/dashboard" in page.url or logged_in(page):
                    ok = True
                    break
            except Exception:
                break
        if ok:
            time.sleep(4)                                   # let the session cookie land in the profile
            try:
                page.goto(GL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)
                print("logged in:", logged_in(page))
            except Exception:
                pass
        try:
            ctx.close()
        except Exception:
            pass
        print("profile saved:", PROFILE)
        sys.exit(0)

    for stray in OUT.glob("*.webm"):          # clips left by earlier runs
        if re.fullmatch(r"[0-9a-f]{32}\.webm", stray.name):
            stray.unlink()
    rec_start = time.time()
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=not HEADED, viewport={"width": W, "height": H},
                                               record_video_dir=str(OUT), record_video_size={"width": W, "height": H})
    page = fresh_page(ctx)
    # warm the heavy pages once (the composer trims this away)
    for warm in (f"{GL}/-/merge_requests/1", f"{GL}/-/pipelines", APP + "/"):
        page.goto(warm, wait_until="domcontentloaded", timeout=90000)
        time.sleep(1.5)
    page.goto(GL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if not any(a.startswith("--pipeline=") for a in sys.argv):
        try:      # the newest finished push pipeline on main (public API): after a merge this is the one the merge started
            r = page.request.get("https://gitlab.com/api/v4/projects/seen-hackathons%2Fseen/pipelines?ref=main&source=push&status=success&per_page=1")
            latest = r.json()[0]["id"] if r.ok and r.json() else None
            if latest:
                MAIN_PIPELINE = str(latest)
        except Exception as exc:
            print("pipeline lookup:", str(exc)[:80])
    print("main pipeline:", MAIN_PIPELINE)
    signed_in = logged_in(page)
    hint = "yes" if signed_in else "NO - run  python docs\\record_gitlab.py --login  first; the Merge click needs it"
    print("gitlab login:", hint)
    vw, vh = page.evaluate("[window.innerWidth, window.innerHeight]")
    print(f"viewport {vw}x{vh}")
    T0 = time.time()
    json.dump({"offset": T0 - rec_start, "viewport": [vw, vh], "headless": not HEADED, "logged_in": signed_in},
              open(OUT / "offset.json", "w"))

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
    show(page, re.compile(r"Claim gate\s*\S\s*BLOCKED"), 6.0, "Claim gate — BLOCKED", wait=60)
    smooth_scroll(page, 500, steps=14, dt=0.08)
    pause(3.0)
    show(page, page.locator(".gl-label-text-scoped", has_text="blocked"), 2.5, "editor::blocked")
    show(page, "Tracking issue for the blocked claim", 3.0)
    go(page, f"{GL}/-/work_items/2", 2.5, "issue #2")
    smooth_scroll(page, 300, steps=10, dt=0.08)
    pause(4.0)

    # ---- VERIFIED: the fix, the PASS note, the green pipeline, the human's merge
    go(page, f"{GL}/-/commit/{FIX_COMMIT}", 2.0, "commit with the sourced fact")
    show(page, "She also took 10 [F4] wickets", 4.0)
    go(page, f"{GL}/-/merge_requests/1", 3.0, "MR !1 overview again")
    show(page, re.compile(r"Claim gate\s*\S\s*PASS"), 5.0, "Claim gate — PASS", wait=60)
    show(page, page.locator(".gl-label-text-scoped", has_text="verified"), 3.0, "editor::verified")
    page.keyboard.press("Home")
    pause(3.0)
    mark("MR top: green pipeline, ready to merge")
    if MERGE:
        try:
            btn = page.get_by_role("button", name=re.compile(r"^Merge$")).first
            btn.wait_for(timeout=15000)
            btn.click(timeout=10000)
            mark("MERGE clicked")
            pause(8.0)
        except Exception as exc:
            mark(f"merge button: {str(exc)[:60]}")
    else:
        pause(3.0)

    # ---- LIFECYCLE: the main pipeline, policies, security, environments, schedule, monitor
    go(page, f"{GL}/-/pipelines", 3.0, "pipelines list")
    go(page, f"{GL}/-/pipelines/{MAIN_PIPELINE}", 4.0, "main pipeline graph")
    click_job(page, "govern-policies", 5.0)
    go(page, f"{GL}/-/pipelines/{MAIN_PIPELINE}/security", 4.0, "pipeline security tab")
    go(page, f"{GL}/-/environments", 4.0, "environments")
    go(page, f"{GL}/-/pipeline_schedules", 4.0, "pipeline schedules")
    go(page, f"{GL}/-/pipelines?source=schedule", 3.0, "scheduled runs")
    go(page, f"{GL}/-/pipelines/{SCHEDULED_PIPELINE}", 2.0, "scheduled pipeline")
    click_job(page, "monitor-production", 5.0)

    # ---- CLOSE: the flow in the catalog, the write-up, the live app
    go(page, "https://gitlab.com/explore/ai-catalog/flows/1016614", 3.0, "flow in the AI Catalog")
    smooth_scroll(page, 900, steps=24, dt=0.08)
    pause(4.0)
    go(page, f"{GL}/-/blob/main/docs/gitlab_life_after_code.md", 2.5, "write-up")
    show(page, "What was added during the submission period", 5.0)
    go(page, APP + "/", 4.0, "app home (end)")
    pause(5.0)
    mark("end")

    json.dump(LOG, open(OUT / "nav_log.json", "w"), indent=1)
    video_path = page.video.path()
    ctx.close()
    final = OUT / "screen.webm"
    if final.exists():
        final.unlink()
    shutil.move(video_path, final)
    for stray in OUT.glob("*.webm"):          # the first tab the profile opens by itself leaves an empty clip behind
        if re.fullmatch(r"[0-9a-f]{32}\.webm", stray.name):
            stray.unlink()
print("recorded:", OUT / "screen.webm")
