"""Visit the hosted demo like a real viewer so Streamlit Community Cloud does not put it to sleep.

Community Cloud hibernates an app after 12 hours without viewers; a sleeping app greets the next visitor with a
"get this app back up" button and a one-to-two-minute boot. The GitHub Actions workflow in .github/workflows/keep-awake.yml
runs this script every six hours: it opens the app in a headless browser (a real websocket session, which is what counts
as traffic), wakes it if it has dozed off, and fails loudly if the app does not come up — a failed run e-mails the repo owner.

Community Cloud serves the app inside an iframe of a host page, so every check looks through all frames.

    python docs/keep_awake.py https://seen-unseen-xi.streamlit.app
"""
import sys
import time

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else "https://seen-unseen-xi.streamlit.app").rstrip("/")
READY_TEXT = "This week's XI"          # rendered by app/Home.py once the pipeline output is loaded
WAKE_BUTTON = "get this app back up"   # Community Cloud's sleeping page


def frame_with_text(page, text):
    for frame in page.frames:
        try:
            if frame.get_by_text(text).count():
                return frame
        except Exception:      # a frame can detach while the app boots
            pass
    return None


def frame_with_button(page, name):
    for frame in page.frames:
        try:
            if frame.get_by_role("button", name=name).count():
                return frame
        except Exception:
            pass
    return None


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        started = time.time()
        woke = False
        app = None
        while time.time() - started < 300:           # a cold boot (dependency install) can take a few minutes
            app = frame_with_text(page, READY_TEXT)
            if app is not None:
                break
            if not woke:
                f = frame_with_button(page, WAKE_BUTTON)
                if f is not None:
                    print("app was asleep: waking it")
                    f.get_by_role("button", name=WAKE_BUTTON).first.click()
                    woke = True
            time.sleep(5)
        else:
            print(f"FAIL: '{READY_TEXT}' not visible after 5 minutes (woke={woke}); frames: {[f.url for f in page.frames]}")
            print(page.content()[:1500])
            browser.close()
            return 1
        # keep the session open for a moment and open one more page, like a visitor would
        time.sleep(15)
        try:
            app.get_by_role("link", name="Story Kit", exact=True).first.click(timeout=15_000)
            time.sleep(10)
        except Exception:
            pass
        print(f"ok: {URL} is awake (woke it: {woke}); visit took {time.time() - started:.0f}s; app frame: {app.url}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
