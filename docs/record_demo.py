"""Record the SEEN walkthrough against the hosted app, timed to the 3-minute narration.

Run on a machine that can reach the app (your laptop):
    .venv\\Scripts\\pip install playwright
    .venv\\Scripts\\playwright install chromium
    .venv\\Scripts\\python docs\\record_demo.py https://seen-unseen-xi.streamlit.app/~/+

It opens a 1600x900 browser, walks the nine screens on the narration's clock (hook 0:00, problem 0:22,
product 0:48, trust 1:30, fans 2:06, close 2:38), triggers one live "Rewrite with the model" call, shows the
claim checker blocking a made-up number, and writes docs/rec_nebius/screen.webm + offset.json + nav_log.json.
Send that folder back; the narration, captions and picture-in-picture are composed afterwards.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://seen-unseen-xi.streamlit.app/~/+").rstrip("/")
OUT = Path(__file__).resolve().parent / "rec_nebius"
OUT.mkdir(parents=True, exist_ok=True)
B = {"hook": 0.0, "problem": 22.3, "product": 48.4, "trust": 89.8, "fans": 125.6, "close": 157.8}
ATHLETE = "Hayley Matthews"
ANGLE = "for a first-time fan in Lahore, warm and simple"
T0 = None
LOG = []


def at(t):
    delay = T0 + t - time.time()
    if delay > 0:
        time.sleep(delay)


def mark(label):
    LOG.append((label, round(time.time() - T0, 1)))


def nav(page, label):
    page.get_by_role("link", name=label, exact=True).first.click()
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    mark("nav " + label)
    time.sleep(0.3)


def select_first(page, text, idx=0):
    box = page.locator('div[data-testid="stSelectbox"]').nth(idx)
    box.wait_for(timeout=20000)
    try:
        if box.locator("input").first.input_value().strip() == text:
            time.sleep(0.5)
            return
    except Exception:
        pass
    for _ in range(2):
        box.locator("input").first.click()
        page.keyboard.type(text, delay=30)
        time.sleep(0.9)
        page.keyboard.press("Enter")
        for _ in range(12):
            time.sleep(0.4)
            try:
                if box.locator("input").first.input_value().strip() == text:
                    time.sleep(0.8)
                    return
            except Exception:
                pass
    time.sleep(0.5)


def smooth_scroll(page, dy, steps=12, dt=0.05):
    page.mouse.move(800, 500)
    for _ in range(steps):
        page.mouse.wheel(0, dy / steps)
        time.sleep(dt)


def live_rewrite(page):
    """Open the popover, type the angle, generate; return when the result banner is on screen (max 45 s)."""
    page.get_by_role("button", name="Rewrite with the model").first.click()
    time.sleep(0.8)
    field = page.get_by_label("Angle (optional)").first
    field.click()
    page.keyboard.type(ANGLE, delay=25)
    page.keyboard.press("Enter")
    time.sleep(0.6)
    page.get_by_role("button", name="Generate and verify").first.click()
    mark("rewrite requested")
    try:
        page.get_by_text("passed the claim checker").first.wait_for(timeout=35000)
        mark("rewrite accepted")
    except Exception:
        mark("rewrite: no result banner in 35 s (continuing)")
    page.keyboard.press("Escape")
    time.sleep(0.5)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
    rec_start = time.time()
    ctx = browser.new_context(viewport={"width": 1600, "height": 900}, record_video_dir=str(OUT), record_video_size={"width": 1600, "height": 900})
    page = ctx.new_page()
    # warm every page once before the clock starts (first loads compile each page script; the composer trims this away)
    for warm in ("/Athlete_Profile", "/Story_Opportunity", "/Story_Kit", "/Localisation", "/Fan_Feed", "/Impact_Dashboard"):
        page.goto(BASE + warm, wait_until="networkidle", timeout=90000)
        time.sleep(1.0)
    page.goto(BASE + "/", wait_until="networkidle", timeout=90000)
    page.get_by_text("This week's XI").first.wait_for(timeout=90000)
    time.sleep(1.5)
    T0 = time.time()
    json.dump({"offset": T0 - rec_start}, open(OUT / "offset.json", "w"))
    # ---- hook: the XI, Matthews' card, then the scatter
    at(4.0); smooth_scroll(page, 900)
    at(12.0); smooth_scroll(page, 260)
    # ---- problem: stay on the scatter, drift to the gap explorer and back
    at(B["problem"] + 12); smooth_scroll(page, 700, steps=20, dt=0.08)
    at(B["problem"] + 20); smooth_scroll(page, -700, steps=20, dt=0.08)
    # ---- product: XI cards -> profile -> story opportunity -> story kit -> live Nemotron rewrite
    at(B["product"]); page.goto(BASE + "/", wait_until="networkidle", timeout=60000); page.get_by_text("This week's XI").first.wait_for(timeout=30000); time.sleep(0.8); smooth_scroll(page, 700)
    at(B["product"] + 6); nav(page, "Athlete Profile"); select_first(page, ATHLETE)
    at(B["product"] + 16); smooth_scroll(page, 300)
    at(B["product"] + 20); nav(page, "Story Opportunity"); select_first(page, ATHLETE)
    at(B["product"] + 27); nav(page, "Story Kit"); select_first(page, ATHLETE)
    at(B["product"] + 28); live_rewrite(page)            # result banner lands around 1:32-1:40 on the hosted app
    # ---- trust: the made-up number is blocked, then the gap split and the Hindi kit
    at(B["trust"] + 5); smooth_scroll(page, 120, steps=4)
    ta = page.locator('div[data-testid="stTextArea"] textarea').first
    at(B["trust"] + 6.5); ta.click(); page.keyboard.press("Control+End")
    page.keyboard.type(" She also scored 200 runs in the final.", delay=30)
    time.sleep(0.4); page.keyboard.press("Control+Enter"); time.sleep(1.2)
    at(B["trust"] + 10.5); page.get_by_role("button", name="Re-check").first.click(); mark("re-check")
    at(B["trust"] + 14); nav(page, "Athlete Profile"); select_first(page, ATHLETE)
    at(B["trust"] + 19); smooth_scroll(page, 520)
    at(B["trust"] + 22.5); nav(page, "Localisation"); select_first(page, ATHLETE)
    at(B["trust"] + 30); smooth_scroll(page, 900)
    # ---- fans: feed in Hindi, then impact
    at(B["fans"] - 4.0); nav(page, "Fan Feed"); select_first(page, "Hindi")
    at(B["fans"] + 7); smooth_scroll(page, 500, steps=16, dt=0.08)
    at(B["fans"] + 9.5); nav(page, "Impact Dashboard")
    at(B["fans"] + 24); smooth_scroll(page, 600, steps=16, dt=0.08)
    # ---- close: back on the Unseen XI, drift to the scatter
    at(B["close"] - 6); nav(page, "Home"); page.get_by_text("This week's XI").first.wait_for(timeout=30000)
    at(B["close"] + 5); smooth_scroll(page, 900, steps=24, dt=0.15)
    at(B["close"] + 13); smooth_scroll(page, 260, steps=30, dt=0.15)
    at(183.0)
    # ---- leave the hosted kit clean: put the verified text back after the blocked-edit demo
    try:
        nav(page, "Story Kit"); select_first(page, ATHLETE)
        page.get_by_role("button", name="Revert edits").first.click(timeout=5000); mark("reverted")
        time.sleep(2)
    except Exception:
        mark("no revert button (nothing to revert)")
    json.dump(LOG, open(OUT / "nav_log.json", "w"), indent=1)
    video_path = page.video.path()
    ctx.close()
    browser.close()
    final = OUT / "screen.webm"
    if final.exists():
        final.unlink()
    shutil.move(video_path, final)
print("recorded:", OUT / "screen.webm")
print("log:", LOG)
