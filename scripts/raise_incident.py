"""Open (or update) an incident issue when the hosted demo fails its health check — the "monitor" stage's alarm.

Runs inside GitLab CI after docs/keep_awake.py fails. Needs a project access token with `api` scope in the CI/CD
variable SEEN_BOT_TOKEN (Settings > CI/CD > Variables, masked). Without it, the job still fails — the pipeline
status is the alarm — and this script only prints what it would have done. Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

API = os.environ.get("CI_API_V4_URL", "https://gitlab.com/api/v4")
PROJECT = os.environ.get("CI_PROJECT_ID", "")
TOKEN = os.environ.get("SEEN_BOT_TOKEN", "")
APP_URL = os.environ.get("APP_URL", "https://seen-unseen-xi.streamlit.app")
PIPELINE = os.environ.get("CI_PIPELINE_URL", "")
TITLE = "Incident: hosted demo failed its health check"


def call(method: str, path: str, data: dict | None = None):
    req = urllib.request.Request(f"{API}/projects/{PROJECT}/{path}", method=method,
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"PRIVATE-TOKEN": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    body = (f"The scheduled monitor could not load **{APP_URL}** (the Unseen XI did not render within 5 minutes).\n\n"
            f"Pipeline: {PIPELINE}\n\nRunbook: open the app once (Community Cloud wakes a sleeping app on the first visit); "
            f"if it stays down, reboot it from share.streamlit.io, then re-run the monitor job.")
    if not (TOKEN and PROJECT):
        print("SEEN_BOT_TOKEN not set — would have opened an incident issue:\n" + body)
        return 0
    q = urllib.parse.urlencode({"state": "opened", "search": TITLE, "in": "title"})
    existing = call("GET", f"issues?{q}")
    if existing:
        iid = existing[0]["iid"]
        call("POST", f"issues/{iid}/notes", {"body": f"Still failing — {PIPELINE}"})
        print("updated incident", existing[0]["web_url"])
    else:
        issue = call("POST", "issues", {"title": TITLE, "description": body, "labels": "incident,monitor", "issue_type": "incident"})
        print("opened incident", issue["web_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
