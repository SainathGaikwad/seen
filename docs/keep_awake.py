"""Visit the hosted demo like a real viewer so Streamlit Community Cloud does not put it to sleep.

Community Cloud hibernates an app after 12 hours without viewers; a sleeping app greets the next visitor with a
"get this app back up" button and a one-to-two-minute boot. The GitHub Actions workflow in .github/workflows/keep-awake.yml
runs this script every six hours: it opens the app in a headless browser (a real websocket session, which is what counts
as traffic), wakes it if it has dozed off, and fails loudly if the app does not come up — a failed run e-mails the repo owner.

    python docs/keep_awake.py https://seen-unseen-xi.streamlit.app
"""
import sys
import time

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else "https://seen-unseen-xi.streamlit.app").rstrip("/")
READY_TEXT = "This week's XI"          # rendered by app/Home.py once the pipeline output is loaded
WAKE_BUTTON = "get this app back up"   # Community Cloud's sleeping page


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        started = time.time()
        woke = False
        while time.time() - started < 300:           # a cold boot (dependency install) can take a few minutes
            if page.get_by_text(READY_TEXT).count():
                break
            btn = page.get_by_role("button", name=WAKE_BUTTON)
            if not woke and btn.count():
                print("app was asleep: waking it")
                btn.first.click()
                woke = True
            time.sleep(5)
        else:
            print(f"FAIL: '{READY_TEXT}' not visible after 5 minutes (woke={woke})")
            print(page.content()[:2000])
            browser.close()
            return 1
        # keep the session open for a moment and open one more page, like a visitor would
        time.sleep(15)
        try:
            page.get_by_role("link", name="Story Kit", exact=True).first.click(timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=30_000)
        except PWTimeout:
            pass
        time.sleep(10)
        print(f"ok: {URL} is awake (woke it: {woke}); visit took {time.time() - started:.0f}s")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
