"""Claim gate for story kits — the deterministic check that stands between a model and publication.

Re-verifies every number in every format of every kit against the kit's fact bundle (seen/stories/claim_check.py)
and reports PASS / BLOCKED per athlete and format. Used by CI (verify + govern stages), by the GitLab Duo
"Editor-in-chief" flow when it reviews a merge request, and by anyone locally:

    python scripts/check_kits.py                       # every kit, markdown report, exit 1 if anything is blocked
    python scripts/check_kits.py --changed origin/main # only kits changed against a git ref (falls back to all)
    python scripts/check_kits.py --format json --out report.json
    python scripts/check_kits.py --translations        # also re-verify the Hindi / Urdu kits

Standard library + seen/stories/claim_check.py only, so it runs anywhere the repository is checked out.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seen.stories import claim_check  # noqa: E402  (stdlib-only module)

FORMATS = ["video_script", "social_posts", "article", "infographic", "creator_brief", "commentator_note", "quiz", "sponsor_hook"]
GUIDANCE_MARKER = "\n--- guidance (not claims) ---\n"   # boilerplate appended to some formats; never a claim


def _numbers_in_json(text: str, key: str) -> str:
    """Infographic and quiz formats are JSON: check the numeric values inside (mirrors compiler.run_checks)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}
    nums: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k != "fact":
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            nums.append(str(o))

    walk(data)
    if key == "quiz":
        return " ".join(str(q.get("answer", "")) for q in (data if isinstance(data, list) else []))
    return " ".join(nums)


def check_kit(kit: dict) -> list[dict]:
    allowed = [kit["name"], kit["team"]] + [f["value"] for f in kit["facts"] if isinstance(f.get("value"), str)]
    rows = []
    for key in FORMATS:
        text = (kit.get("formats") or {}).get(key, "")
        if not text:
            continue
        text = text.split(GUIDANCE_MARKER)[0]
        if key in ("infographic", "quiz"):
            text = _numbers_in_json(text, key)
        res = claim_check.check(text, kit["facts"], allowed)
        bad = [c for c in res.claims if c["status"] == "unmatched"]
        rows.append({
            "athlete": kit["name"], "player_id": kit["player_id"], "language": "en", "format": key,
            "passed": res.passed, "summary": res.summary(),
            "blocked": [c.get("note") or f"{c['text']} is not in any fact" for c in bad],
            "banned": list(res.banned),
        })
    return rows


def check_translation(kit: dict, loc: dict) -> list[dict]:
    allowed = [kit["name"], kit["team"]] + [f["value"] for f in kit["facts"] if isinstance(f.get("value"), str)]
    rows = []
    for key, text in (loc.get("formats") or {}).items():
        if not text:
            continue
        res = claim_check.check(text.split(GUIDANCE_MARKER)[0], kit["facts"], allowed)
        bad = [c for c in res.claims if c["status"] == "unmatched"]
        rows.append({
            "athlete": kit["name"], "player_id": kit["player_id"], "language": loc.get("language", "?"), "format": key,
            "passed": res.passed, "summary": res.summary(),
            "blocked": [c.get("note") or f"{c['text']} is not in any fact" for c in bad],
            "banned": list(res.banned),
        })
    return rows


def changed_kits(base: str, kits_dir: Path) -> set[str] | None:
    """Kit files changed against a git ref; None when git cannot answer (then everything is checked)."""
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD", "--", str(kits_dir.relative_to(ROOT))],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            out = subprocess.run(["git", "diff", "--name-only", base, "--", str(kits_dir.relative_to(ROOT))],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None
        return {Path(line.strip()).name for line in out.stdout.splitlines() if line.strip()}
    except Exception:
        return None


def to_markdown(rows: list[dict], scope: str) -> str:
    n_bad = sum(1 for r in rows if not r["passed"])
    head = ("## Claim gate — BLOCKED" if n_bad else "## Claim gate — PASS")
    lines = [head, "", f"{scope}: {len(rows)} format(s) checked, {len(rows) - n_bad} verified, {n_bad} blocked.", "",
             "| Athlete | Lang | Format | Result | Detail |", "|---|---|---|---|---|"]
    for r in rows:
        detail = r["summary"]
        if r["blocked"]:
            detail += " — " + "; ".join(r["blocked"])
        if r["banned"]:
            detail += " — banned topics: " + ", ".join(r["banned"])
        lines.append(f"| {r['athlete']} | {r['language']} | `{r['format']}` | {'✅ PASS' if r['passed'] else '⛔ BLOCKED'} | {detail} |")
    lines.append("")
    lines.append("Every number in a draft must match a sourced fact in the kit's bundle (unit included); anything else is blocked before publication.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kits", default=str(ROOT / "data" / "derived" / "kits"))
    ap.add_argument("--localized", default=str(ROOT / "data" / "derived" / "localized"))
    ap.add_argument("--changed", metavar="GIT_REF", help="only kits changed against this ref (e.g. origin/main)")
    ap.add_argument("--translations", action="store_true", help="also re-verify translated kits")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out", help="write the report here as well as to stdout")
    args = ap.parse_args()

    kits_dir, loc_dir = Path(args.kits), Path(args.localized)
    files = sorted(kits_dir.glob("*.json"))
    scope = "All kits"
    if args.changed:
        changed = changed_kits(args.changed, kits_dir)
        if changed is None:
            scope = f"All kits (could not diff against {args.changed})"
        elif not changed:
            scope = f"No kit changed against {args.changed}; checked all kits"
        else:
            files = [f for f in files if f.name in changed]
            scope = f"Kits changed against {args.changed}"
    rows: list[dict] = []
    for f in files:
        kit = json.loads(f.read_text(encoding="utf-8"))
        rows.extend(check_kit(kit))
        if args.translations:
            for lf in sorted(loc_dir.glob(f"{kit['player_id']}_*.json")):
                loc = json.loads(lf.read_text(encoding="utf-8"))
                if str(loc.get("status", "")).startswith("translated"):
                    rows.extend(check_translation(kit, loc))
    report = json.dumps({"scope": scope, "rows": rows, "blocked": sum(1 for r in rows if not r["passed"])}, indent=1, ensure_ascii=False) \
        if args.format == "json" else to_markdown(rows, scope)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 1 if any(not r["passed"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
