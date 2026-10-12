"""SEEN Sponsor Desk film:  python docs/film/film_paypal.py docs/rec_paypal docs/rec_paypal/narration docs/rec_paypal/SEEN_paypal_demo.mp4
Streamlit Cloud's wrapper (Fork/GitHub icon, "Hosted with Streamlit") and GitHub's header are cropped away, never shown."""
import sys
from pathlib import Path

from filmcut import BAND, compose

BLOCKS = ["hook", "problem", "desk", "payment", "tip", "ledger", "close"]
GAP_AFTER = {"hook": 0.7, "problem": 0.7, "desk": 0.9, "payment": 0.9, "tip": 1.8, "ledger": 2.2, "close": 3.0}


def shots_for(r, block):
    L = r.L
    if block == "hook":
        return [(L("page /") - 1.5, L("nav Story Kit") - 0.3, "app"),
                (L("nav Story Kit") + 0.3, L("nav Sponsor Desk") - 0.3, "app")]
    if block == "problem":
        return [(L("nav Sponsor Desk"), L("desk asked") + 0.4, "app")]
    if block == "desk":
        think_end = L("order raised")
        think_start = max(L("desk asked") + 0.4, think_end - 8.0)
        s = [(think_start, think_end, "app"),
             (think_end, L("approve url captured") + 1.2, "app", "hold")]
        clicks, readies = r.times("paypal click"), r.times("checkout ready")
        if clicks:
            ready0 = next((t for t in readies if t < clicks[0]), None)
            if ready0:                                        # remembered session: the checkout appears straight away
                s.append((L("paypal checkout opened", 0) + 0.5, ready0, "paypal"))
        return s
    if block == "payment":
        back = L("back in the app", 0, default=L("receipt on screen") - 0.5)
        clicks, readies = r.times("paypal click"), r.times("checkout ready")
        s = []
        if clicks:
            ready0 = next((t for t in readies if t < clicks[0]), None)
            s.append((ready0 if ready0 else clicks[0] - 2.5, clicks[0] + 3.0, "paypal"))
            s.append((back - 3.5, back - 1.8, "app"))
        s += [(back - 1.6, L("nav Fan Feed") - 0.2, "app", "hold"),
              (L("nav Fan Feed") + 4.5, L("tip clicked") - 1.0, "app")]
        return s
    if block == "tip":
        clicks, readies = r.times("paypal click"), r.times("checkout ready")
        s = [(L("tip clicked") - 1.0, L("tip clicked") + 2.0, "app")]
        if len(clicks) > 1:
            ready1 = next((t for t in readies if clicks[0] < t < clicks[1]), None)
            s.append((ready1 if ready1 else clicks[1] - 2.5, clicks[1] + 2.0, "paypal"))
        s.append((L("tip receipt on screen") + 2.0, L("tip receipt on screen") + 6.0, "app"))
        return s
    if block == "ledger":
        if not r.has("quick filter Bryce"):                      # no grid in this recording: hold the page
            return [(L("nav Money Ledger") + 5.5, L("per-athlete table", default=L("nav Money Ledger") + 12.0) + 4.0, "app")]
        s = [(L("nav Money Ledger") + 5.5, L("quick filter Bryce") - 1.2, "app"),
             (L("quick filter Bryce") - 1.2, L("filters reset") + 1.0, "app")]
        if r.has("grid slid right"):
            s.append((L("grid slid right") - 2.0, L("split group opened") + 2.0, "app"))
            s.append((L("per-athlete table") - 0.5, L("per-athlete table") + 5.0, "app"))
        else:
            s.append((L("filters reset") + 1.0, L("filters reset") + 8.0, "app"))
        return s
    if block == "close":
        return [(L("github seen/money") + 2.0, L("github seen/money") + 4.0, "github"),
                (L("github write-up") + 0.8, L("github write-up") + 4.0, "github"),
                (L("page /", 0) - 2.5, L("page /", 0) + 0.2, "app", "hold")]      # the home page, fully drawn, from the opening
    raise KeyError(block)


def vf_for(r, kind, t_in):
    h = r.content_height(t_in)
    if kind == "github":                          # GitHub's header (its logo, sign-in) is not ours: crop it off
        return "crop=1233:694:0:74,scale=1920:1080:flags=lanczos" if h < 900 else "crop=1465:824:0:76,scale=1920:1080:flags=lanczos"
    if h < 900:                                   # a 1600x768 recording: letterbox under a band
        return f"crop=1600:{h}:0:0,scale=1920:{round(1920 * h / 1600)}:flags=lanczos,pad=1920:1080:0:0:color={BAND}"
    return "crop=1511:850:0:0,scale=1920:1080:flags=lanczos"   # app + PayPal pages: the Cloud wrapper sits outside this window


def captions_for(S, END):
    return [
        (S["hook"] + 0.3, S["hook"] + 6.5, "SEEN  ·  The Unseen XI  ·  women’s cricket, from public data  ·  seen-unseen-xi.streamlit.app"),
        (S["hook"] + 7.0, S["problem"] - 0.2, "Every number in every story is checked against a fact bundle before it is published"),
        (S["problem"] + 0.3, S["problem"] + 8.0, "Sponsor Desk  ·  verified story kits on sale this week  ·  price rises with the athlete’s visibility gap"),
        (S["problem"] + 8.5, S["desk"] - 0.2, "The brief: a Bridgetown rum brand, Caribbean fans, Hayley Matthews, English + Urdu, one week"),
        (S["desk"] + 0.3, S["desk"] + 9.0, "Planner: NVIDIA Nemotron on Nebius  ·  tools from PayPal’s Agent Toolkit: catalogue → price_package → create_order"),
        (S["desk"] + 9.5, S["desk"] + 19.5, "Policy: 1–4 athletes  ·  verified languages only  ·  the budget is a hard cap  ·  60 / 30 / 10 split"),
        (S["desk"] + 20.0, S["payment"] - 0.2, "The agent only raises the order (PayPal Orders v2)  —  approval and payment happen in PayPal, by the sponsor"),
        (S["payment"] + 0.3, S["payment"] + 6.5, "PayPal sandbox checkout  ·  test money, real API calls"),
        (S["payment"] + 7.0, S["payment"] + 14.0, "On return: capture the order  →  tag her stories “Presented by”  →  one Payouts batch (60 / 30 / 10)"),
        (S["payment"] + 14.5, S["tip"] - 0.2, "Fan feed: Hayley Matthews’ story now carries the sponsor’s tag"),
        (S["tip"] + 0.3, S["ledger"] - 0.2, "Fan tip $2  →  PayPal checkout  →  split 70 / 20 / 10  →  Payouts"),
        (S["ledger"] + 0.3, S["ledger"] + 7.5, "Money ledger  ·  AG Grid Community: quick filter, column filters, totals that follow the filter, CSV export"),
        (S["ledger"] + 8.0, S["close"] - 0.2, "Per athlete: what her story raised, and where it went"),
        (S["close"] + 0.3, S["close"] + 8.5, "PayPal Orders v2 · Invoicing v2 · Payouts v1  ·  Agent Toolkit vendored (Apache-2.0)  ·  Nemotron on Nebius"),
        (S["close"] + 9.0, END - 0.3, "SEEN  —  women’s cricket, correctly, paid.   github.com/SainathGaikwad/seen"),
    ]


if __name__ == "__main__":
    compose(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), BLOCKS, GAP_AFTER, 0.6, shots_for, vf_for, captions_for,
            prepare=lambda r: r.fit_drift("page /", 4.0, k=1))
