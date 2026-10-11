"""The money ledger: one append-only CSV of everything that moved (or was asked to move) through PayPal, plus the
"presented by" register that the fan feed reads. Nothing here calls PayPal; the gateway's results are written in."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COLUMNS = ["ts", "kind", "ref", "status", "payer", "payer_email", "player_id", "athlete", "team", "languages", "weeks", "item",
           "amount", "currency", "split_athlete", "split_creator", "split_seen", "payout_batch", "payout_status", "simulated", "note"]
KINDS = ("sponsorship", "tip", "invoice", "payout")


def _path(derived: Path) -> Path:
    return Path(derived) / "money_ledger.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(derived: Path, **row) -> dict:
    """Append one row; unknown keys are dropped, missing ones left empty. Returns the row as written."""
    path = _path(derived)
    path.parent.mkdir(parents=True, exist_ok=True)
    row.setdefault("ts", now_iso())
    out = {c: row.get(c, "") for c in COLUMNS}
    if isinstance(out["languages"], (list, tuple)):
        out["languages"] = "+".join(out["languages"])
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(out)
    return out


def load(derived: Path) -> pd.DataFrame:
    path = _path(derived)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in ("amount", "split_athlete", "split_creator", "split_seen"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["weeks"] = pd.to_numeric(df["weeks"], errors="coerce").fillna(0).astype(int)
    return df


def update(derived: Path, ref: str, kind: str | None = None, **fields) -> int:
    """Set fields on every row with this ref (and kind, if given). Returns the number of rows changed."""
    path = _path(derived)
    if not path.exists():
        return 0
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    mask = df["ref"] == ref
    if kind:
        mask &= df["kind"] == kind
    for k, v in fields.items():
        if k in df.columns:
            df.loc[mask, k] = str(v)
    df.to_csv(path, index=False)
    return int(mask.sum())


def edit(derived: Path, fn) -> None:
    """Load the raw ledger (strings), let fn mutate the DataFrame in place, save it."""
    path = _path(derived)
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    fn(df)
    df.to_csv(path, index=False)


def totals(df: pd.DataFrame) -> dict:
    money_in = df[df.kind.isin(["sponsorship", "tip", "invoice"]) & df.status.isin(["COMPLETED", "PAID"])]
    paid_out = df[(df.kind == "payout") & df.status.isin(["SUCCESS", "PENDING", "PROCESSING", "UNCLAIMED"])]
    return {
        "raised": round(float(money_in.amount.sum()), 2),
        "sponsorships": int((money_in.kind != "tip").sum()),
        "tips": int((money_in.kind == "tip").sum()),
        "to_athletes": round(float(money_in.split_athlete.sum()), 2),
        "to_creators": round(float(money_in.split_creator.sum()), 2),
        "paid_out": round(float(paid_out.amount.sum()), 2),
        "pending": int(((df.kind != "payout") & df.status.isin(["CREATED", "PAYER_ACTION_REQUIRED", "SENT", "UNPAID"])).sum()),
        "simulated": bool((df.simulated.astype(str).str.lower() == "true").any()) if len(df) else False,
    }


def by_athlete(df: pd.DataFrame) -> pd.DataFrame:
    paid = df[df.kind.isin(["sponsorship", "tip", "invoice"]) & df.status.isin(["COMPLETED", "PAID"]) & (df.player_id != "")]
    if paid.empty:
        return pd.DataFrame(columns=["player_id", "athlete", "team", "raised", "sponsorships", "tips", "to_athlete", "to_creator", "sponsors"])
    g = paid.groupby(["player_id", "athlete", "team"])
    out = g.agg(raised=("amount", "sum"), sponsorships=("kind", lambda s: int((s != "tip").sum())), tips=("kind", lambda s: int((s == "tip").sum())),
                to_athlete=("split_athlete", "sum"), to_creator=("split_creator", "sum"),
                sponsors=("payer", lambda s: ", ".join(sorted({x for x in s if x and not str(x).startswith("fan-")})))).reset_index()
    for c in ("raised", "to_athlete", "to_creator"):
        out[c] = out[c].round(2)
    return out.sort_values("raised", ascending=False).reset_index(drop=True)


# -- "presented by" register ---------------------------------------------------------------------------------------
def _sp_path(derived: Path) -> Path:
    return Path(derived) / "sponsorships.json"


def sponsorships(derived: Path) -> list[dict]:
    p = _sp_path(derived)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def add_sponsorship(derived: Path, player_id: str, sponsor: str, languages: list[str], weeks: int, ref: str, simulated: bool = False) -> None:
    recs = [r for r in sponsorships(derived) if not (r.get("player_id") == player_id and r.get("ref") == ref)]
    recs.append({"player_id": player_id, "sponsor": sponsor, "languages": list(languages), "weeks": int(weeks), "ref": ref,
                 "since": now_iso(), "simulated": bool(simulated)})
    _sp_path(derived).parent.mkdir(parents=True, exist_ok=True)
    _sp_path(derived).write_text(json.dumps(recs, indent=1, ensure_ascii=False), encoding="utf-8")


def presented_by(derived: Path, player_id: str, language: str = "en") -> str | None:
    """The sponsor tag to show on an athlete's story in this language, if one is live."""
    for r in reversed(sponsorships(derived)):
        if r.get("player_id") == player_id and (language in r.get("languages", []) or not r.get("languages")):
            return r.get("sponsor")
    return None
