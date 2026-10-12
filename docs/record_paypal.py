"""Record the Sponsor Desk walkthrough against the hosted app for the PayPal AI Hackathon video.

The recording happens in ONE browser tab (one continuous file): the desk raises a real sandbox order, the tab goes to
PayPal's sandbox checkout, pays as the sandbox buyer, PayPal sends it back to the app; then a $2 tip the same way;
then the ledger. The buyer's sandbox login is remembered in a private browser profile, so log in once:

    python docs\record_paypal.py --login          # opens sandbox.paypal.com: log in as the BUYER (sb-ybvvq...), close the window
    python docs\record_paypal.py --login-fund     # optional: second profile, log in as the ATHLETE FUND (sb-agkha...) for the
                                                   # "money arrived" shot, close the window
    python docs\record_paypal.py                  # records headless → docs/rec_paypal/screen.webm (+ fund.webm, nav_log.json)
    python docs\record_paypal.py --headed         # same, in a window you can watch (a short laptop screen crops the film)

If the checkout still asks for a login, PP_BUYER_EMAIL / PP_BUYER_PASSWORD from the environment are typed in (never
printed or stored). Target another app with: python docs\record_paypal.py http://localhost:8501
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = (ARGS[0] if ARGS else "https://seen-unseen-xi.streamlit.app").rstrip("/")
APP = BASE + ("/~/+" if "streamlit.app" in BASE and "/~/+" not in BASE else "")   # Community Cloud serves the app inside this path
OUT = Path(__file__).resolve().parent / "rec_paypal"
PROFILE, PROFILE_FUND = OUT / "profile", OUT / "profile_fund"
OUT.mkdir(parents=True, exist_ok=True)
BRIEF = "A Bridgetown rum brand wants Caribbean fans to meet Hayley Matthews in English and Urdu for one week."
SPONSOR = "Bridgetown Rum Co"
W, H = 1600, 900
HEADLESS = "--headed" not in sys.argv      # headless gives an exact 1600x900 film; --headed lets you watch (a laptop screen may be too short)
T0 = time.time()
LOG: list[tuple[str, float]] = []
BUYER = (os.environ.get("PP_BUYER_EMAIL", "").strip(), os.environ.get("PP_BUYER_PASSWORD", ""))
PAY_BTN = re.compile(r"Review Order|Pay Now|Complete Purchase|Continue to Review|^Continue$|Agree & Pay|Agree and Pay", re.I)


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


def grid_scroll(grid, x0: int, x1: int, steps: int = 30, dt: float = 0.05):
    """Slide an AG Grid's columns from scrollLeft x0 to x1 (the grid is wider than the window)."""
    for i in range(1, steps + 1):
        x = x0 + (x1 - x0) * i / steps
        grid.evaluate(
            "(x) => { const vp = document.querySelector('.ag-body-horizontal-scroll-viewport') || document.querySelector('.ag-center-cols-viewport');"
            " if (vp) vp.scrollLeft = x; }", x)
        time.sleep(dt)


def find_grid(page, wait_s: float = 10.0):
    """The AG Grid lives in the ledger component's srcdoc iframe; it can take a few seconds to mount."""
    for _ in range(int(wait_s * 2)):
        for f in page.frames:
            try:
                if f.locator("#q").count() and f.locator(".ag-row").count():
                    return f
            except Exception:
                pass
        time.sleep(0.5)
    return None


def page_scroll(page, top: int):
    """Scroll the app page itself (Streamlit's main section) — wheel events over the grid iframe scroll the grid instead."""
    fr(page).evaluate(
        "(top) => { let el = document.querySelector('iframe');"
        " while (el && el !== document.body) { const cs = getComputedStyle(el);"
        "   if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10) break; el = el.parentElement; }"
        " (el && el !== document.body ? el : document.scrollingElement).scrollTo({top: top, behavior: 'smooth'}); }", top)
    time.sleep(1.5)


def fr(page):
    """The frame the app lives in: the page itself when it was opened at /~/+, or Community Cloud's iframe after
    PayPal sends the tab back to the public URL."""
    for f in page.frames:
        if "/~/+" in f.url and f is not page.main_frame:
            return f
    return page.main_frame


def settle(page, s: float = 1.5):
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    time.sleep(s)


def goto(page, path: str, s: float = 1.5):
    page.goto(APP + path, wait_until="domcontentloaded", timeout=90000)
    settle(page, s)
    mark("page " + path)


def nav(page, label: str):
    fr(page).get_by_role("link", name=label, exact=True).first.click(timeout=15000)
    settle(page, 1.2)
    mark("nav " + label)


def open_expander(page, text: str):
    try:
        s = fr(page).locator("summary", has_text=text).first
        s.scroll_into_view_if_needed(timeout=5000)
        s.click(timeout=5000)
        time.sleep(0.8)
        mark("expand " + text)
    except Exception as exc:
        mark(f"expander {text}: {str(exc)[:60]}")


def frames_with(page, make):
    """Yield (frame, locator) for every frame where the locator built by make(frame) matches something visible."""
    for f in page.frames:
        try:
            loc = make(f)
            if loc.count() and loc.first.is_visible():
                yield f, loc.first
        except Exception:
            continue


def pay_button(page):
    for _, loc in frames_with(page, lambda f: f.get_by_role("button", name=PAY_BTN)):
        return loc
    return None


def paypal_login(page, creds: tuple[str, str]) -> None:
    """The checkout either shows the review page straight away (remembered session) or asks the buyer to log in."""
    for _ in range(8):
        if pay_button(page) is not None:
            mark("checkout ready (session remembered)")
            return
        time.sleep(1.0)
    email, pw = creds
    if not (email and pw):
        mark("login needed and no PP_BUYER_* in the environment: waiting up to 90 s for a manual login")
        for _ in range(90):
            if pay_button(page) is not None:
                return
            time.sleep(1.0)
        return
    try:
        box = next(iter(frames_with(page, lambda f: f.get_by_role("textbox", name=re.compile("email|mobile", re.I)))), (None, None))[1]
        if box is None:
            box = next(iter(frames_with(page, lambda f: f.locator("input[type='email'], #email"))), (None, None))[1]
        if box is not None:
            box.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(email, delay=20)
            page.keyboard.press("Enter")
            time.sleep(2.5)
        pwd = None
        for _ in range(10):
            pwd = next(iter(frames_with(page, lambda f: f.locator("input[type='password']"))), (None, None))[1]
            if pwd is not None:
                break
            time.sleep(1.0)
        if pwd is None:
            mark("no password field appeared")
            return
        pwd.click()
        page.keyboard.type(pw, delay=20)
        page.keyboard.press("Enter")
        mark("paypal login submitted")
        for _ in range(30):
            if pay_button(page) is not None:
                return
            time.sleep(1.0)
        mark("login did not reach the checkout review")
    except Exception as exc:
        mark(f"paypal login: {str(exc)[:80]}")


def paypal_pay(page) -> bool:
    """Review Order / Pay Now on the sandbox checkout, then wait for PayPal to send the tab back to the app."""
    for _ in range(4):
        btn = pay_button(page)
        if btn is None:
            break
        try:
            name = btn.inner_text().strip()
        except Exception:
            name = "pay"
        time.sleep(1.2)
        try:
            btn.click(timeout=10000)
            mark("paypal click " + name)
        except Exception as exc:
            mark(f"paypal click failed: {str(exc)[:60]}")
            break
        time.sleep(3.5)
        if "paypal" not in page.url:
            break
    for _ in range(3):
        try:
            back = page.get_by_role("button", name=re.compile("Return to Merchant", re.I)).first
            if back.is_visible(timeout=5000):
                back.click()
                mark("return to merchant")
                break
        except Exception:
            break
    try:
        page.wait_for_url(lambda u: "paypal" not in u, timeout=60000)
    except PWTimeout:
        mark("still on PayPal after 60 s")
        return False
    settle(page, 1.0)
    mark("back in the app: " + page.url.split("?")[0])
    return True


def wait_receipt(page, what: str = "") -> None:
    """The receipt renders inside whichever frame the app is in after PayPal's return; poll for it."""
    for _ in range(60):
        try:
            if fr(page).get_by_text(re.compile(r"^Paid")).first.is_visible():
                mark(what + "receipt on screen")
                return
        except Exception:
            pass
        time.sleep(1.0)
    mark("no " + what + "receipt banner within 60 s")


def approve_in_same_tab(page, href: str, fallback_path: str) -> bool:
    page.goto(href, wait_until="domcontentloaded", timeout=60000)
    mark("paypal checkout opened")
    time.sleep(2.5)
    if "paypal" not in page.url:      # the simulated gateway returns straight to the app
        mark("simulated approval (no PayPal)")
        return True
    paypal_login(page, BUYER)
    ok = paypal_pay(page)
    if not ok:
        mark("payment not completed; returning to the app")
        goto(page, fallback_path, 2.0)
    return ok


def fresh_page(ctx):
    """A page whose viewport really is W×H. The tab a headed persistent profile opens by itself is sized by the
    window (1600×768 on a laptop, with a grey band under it in the video) until the first cross-site navigation;
    a page we open ourselves is emulated at W×H from the start. The check makes the size visible in the log."""
    page = ctx.new_page()
    for other in list(ctx.pages):
        if other is not page:
            try:
                other.close()
            except Exception:
                pass
    page.set_viewport_size({"width": W, "height": H})
    return page


def check_viewport(page) -> tuple[int, int]:
    vw, vh = page.evaluate("[window.innerWidth, window.innerHeight]")
    if (vw, vh) != (W, H):
        page.set_viewport_size({"width": W, "height": H})
        time.sleep(0.5)
        vw, vh = page.evaluate("[window.innerWidth, window.innerHeight]")
    print(f"viewport {vw}x{vh}" + ("" if (vw, vh) == (W, H) else f"  <-- expected {W}x{H}; the film will need letterboxing"))
    return vw, vh


def login_window(p, profile: Path, who: str) -> None:
    ctx = p.chromium.launch_persistent_context(str(profile), headless=False, viewport={"width": W, "height": H})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.sandbox.paypal.com/signin", wait_until="domcontentloaded")
    print(f"Log in as the {who} in the window (sandbox account), wait for the account summary, then close the window.")
    try:
        for _ in range(900):
            time.sleep(1)
            if not ctx.pages:
                break
            if "myaccount" in page.url:
                time.sleep(3)
                break
    except Exception:
        pass
    try:
        ctx.close()
    except Exception:
        pass
    print("profile saved:", profile)


with sync_playwright() as p:
    if "--login" in sys.argv:
        login_window(p, PROFILE, "BUYER (sb-ybvvq…)")
        sys.exit(0)
    if "--login-fund" in sys.argv:
        login_window(p, PROFILE_FUND, "ATHLETE FUND (sb-agkha…)")
        sys.exit(0)

    for stray in OUT.glob("*.webm"):          # clips left by earlier runs
        if re.fullmatch(r"[0-9a-f]{32}\.webm", stray.name):
            stray.unlink()
    headless = HEADLESS
    rec_start = time.time()
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=headless, viewport={"width": W, "height": H},
                                               record_video_dir=str(OUT), record_video_size={"width": W, "height": H},
                                               executable_path=os.environ.get("PW_CHROMIUM") or None)
    page = fresh_page(ctx)
    for warm in ("/Sponsor_Desk", "/Fan_Feed", "/Money_Ledger", "/Story_Kit"):
        page.goto(APP + warm, wait_until="domcontentloaded", timeout=90000)
        time.sleep(1.5)
    vw, vh = check_viewport(page)
    T0 = time.time()
    json.dump({"offset": T0 - rec_start, "viewport": [vw, vh], "headless": headless}, open(OUT / "offset.json", "w"))

    # ---- HOOK: the XI, then a story kit with its fact bundle
    goto(page, "/", 2.0)
    fr(page).get_by_text("This week's XI").first.wait_for(timeout=60000)
    smooth_scroll(page, 700, steps=20, dt=0.08)
    pause(2.5)
    nav(page, "Story Kit")
    pause(2.0)
    smooth_scroll(page, 600, steps=16, dt=0.08)
    pause(3.0)

    # ---- PROBLEM: the catalogue on the desk
    nav(page, "Sponsor Desk")
    pause(2.0)
    smooth_scroll(page, 250, steps=8)
    pause(4.0)

    # ---- THE DESK: brief → agent → order
    ta = fr(page).locator('div[data-testid="stTextArea"] textarea').first
    ta.click()
    page.keyboard.press("Control+A")
    page.keyboard.type(BRIEF, delay=18)
    page.keyboard.press("Control+Enter")
    time.sleep(0.8)
    sp = fr(page).locator('div[data-testid="stTextInput"] input').first
    sp.click(); page.keyboard.press("Control+A"); page.keyboard.type(SPONSOR, delay=25); page.keyboard.press("Enter")
    time.sleep(0.8)
    mark("brief typed")
    fr(page).get_by_role("button", name="Ask the Sponsor Desk").first.click()
    mark("desk asked")
    link = fr(page).get_by_role("link", name=re.compile(r"Approve and pay in PayPal"))
    link.first.wait_for(timeout=180000)
    mark("order raised")
    time.sleep(1.0)
    smooth_scroll(page, 700, steps=16, dt=0.07)
    open_expander(page, "catalogue")
    pause(2.0)
    open_expander(page, "create_order")
    pause(2.5)
    smooth_scroll(page, 600, steps=16, dt=0.07)
    pause(4.0)
    href = link.first.get_attribute("href")
    mark("approve url captured")

    # ---- THE PAYMENT: PayPal sandbox in the same tab, back to the receipt, then the "presented by" tag
    paid = approve_in_same_tab(page, href, "/Sponsor_Desk")
    if paid:
        wait_receipt(page)
    pause(6.0)
    nav(page, "Fan Feed")
    pause(3.0)
    smooth_scroll(page, 300, steps=10)
    pause(3.0)

    # ---- THE TIP
    try:
        fr(page).get_by_role("button", name=re.compile(r"^Tip \$")).first.click(timeout=15000)
        mark("tip clicked")
        tip = fr(page).get_by_role("link", name=re.compile(r"Pay the tip"))
        tip.first.wait_for(timeout=60000)
        pause(1.5)
        thref = tip.first.get_attribute("href")
        if approve_in_same_tab(page, thref, "/Fan_Feed"):
            wait_receipt(page, "tip ")
    except Exception as exc:
        mark(f"tip step: {str(exc)[:80]}")
    pause(5.0)

    # ---- THE LEDGER: grid, quick filter, totals, refresh, split group, per-athlete
    nav(page, "Money Ledger")
    pause(3.0)
    try:
        fr(page).get_by_role("button", name="Refresh payouts").first.click(timeout=10000)
        mark("refresh payouts")
        time.sleep(4)
    except Exception:
        pass
    grid = find_grid(page)
    if grid is None:                      # the component occasionally does not mount on the first render
        page.reload(wait_until="domcontentloaded")
        settle(page, 2.0)
        grid = find_grid(page)
        mark("ledger reloaded" + ("" if grid is not None else " (no grid)"))
    if grid is not None:
        try:
            grid.locator("#q").click()
            page.keyboard.type("Bryce", delay=60)
            mark("quick filter Bryce")
            pause(3.0)
            grid.locator("#reset").click()
            mark("filters reset")
            pause(1.5)
        except Exception as exc:
            mark(f"grid interaction: {str(exc)[:60]}")
        # the grid is wider than the window: slide it to the split, status, payout and PayPal-id columns and back
        try:
            grid_scroll(grid, 0, 900, steps=30, dt=0.05)
            mark("grid slid right (status, payout, PayPal id)")
            pause(2.5)
            grid.locator('.ag-header-group-cell:has-text("Split by policy") .ag-header-expand-icon-collapsed').first.click(timeout=5000)
            mark("split group opened")
            pause(2.0)
            grid_scroll(grid, 900, 0, steps=30, dt=0.05)
            pause(1.0)
        except Exception as exc:
            mark(f"grid slide: {str(exc)[:60]}")
    page_scroll(page, 760)         # the page, not the grid: the per-athlete table underneath
    mark("per-athlete table")
    pause(5.0)

    # ---- CLOSE: the code
    page.goto("https://github.com/SainathGaikwad/seen/tree/main/seen/money", wait_until="domcontentloaded", timeout=60000)
    mark("github seen/money")
    pause(4.0)
    page.goto("https://github.com/SainathGaikwad/seen/blob/main/docs/paypal_sponsor_desk.md", wait_until="domcontentloaded", timeout=60000)
    mark("github write-up")
    pause(4.0)
    goto(page, "/", 4.0)
    pause(5.0)
    mark("end")

    json.dump(LOG, open(OUT / "nav_log.json", "w"), indent=1)
    video_path = page.video.path()
    ctx.close()
    final = OUT / "screen.webm"
    if final.exists():
        final.unlink()
    shutil.move(video_path, final)
    print("recorded:", final)

    # ---- optional second clip: the athlete-fund account's activity (its own profile, its own short video)
    if PROFILE_FUND.exists():
        ctx2 = p.chromium.launch_persistent_context(str(PROFILE_FUND), headless=headless, viewport={"width": W, "height": H},
                                                    record_video_dir=str(OUT), record_video_size={"width": W, "height": H})
        pg2 = fresh_page(ctx2)
        pg2.goto("https://www.sandbox.paypal.com/myaccount/activity/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
        try:
            pg2.mouse.wheel(0, 200)
        except Exception:
            pass
        time.sleep(4)
        v2 = pg2.video.path()
        ctx2.close()
        fund = OUT / "fund.webm"
        if fund.exists():
            fund.unlink()
        shutil.move(v2, fund)
        print("recorded:", fund)

    for stray in OUT.glob("*.webm"):          # the first tab each profile opens by itself leaves an empty clip behind
        if re.fullmatch(r"[0-9a-f]{32}\.webm", stray.name):
            stray.unlink()
