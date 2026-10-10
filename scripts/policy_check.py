"""Governance checks that must hold on every merge (the "govern" stage of the pipeline).

Policies, each with a plain-language reason:
  1. The repository is MIT-licensed and the LICENSE file is present (the data notice inside it stays).
  2. No secrets are tracked: .env files must be ignored, and no file in the tree may contain an API key pattern.
  3. Every published story kit carries a claim-check result that is still true: the stored `checks` must agree with
     a fresh run of the claim gate, so a kit can never ship with a stale PASS.
  4. Every fact in every kit names its source (Cricsheet, Wikimedia, Wikidata) — no fact, no number.
  5. Editorial constraints of the Unseen XI hold in the shipped selection: at most three athletes per country and at
     least three from outside India, England and Australia.
  6. Nothing simulated is presented as measured: the dashboard's synthetic funnel stays behind its SIMULATED switch
     (the string must still be labelled in the page source).

Exit code 1 when any policy fails. Standard library only.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_kits import check_kit  # noqa: E402

KEY_RX = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|v1\.[A-Za-z0-9_\-]{40,}|ghp_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_\-]{20,})")
BIG_THREE = {"India", "England", "Australia"}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return [ROOT / l for l in out.stdout.splitlines() if l.strip()]
    except Exception:
        pass
    return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def main() -> int:
    failures: list[str] = []
    ok: list[str] = []

    lic = ROOT / "LICENSE"
    if lic.exists() and "MIT License" in lic.read_text(encoding="utf-8", errors="ignore"):
        ok.append("MIT licence present")
    else:
        failures.append("LICENSE missing or not MIT")

    files = tracked_files()
    if any(p.name == ".env" for p in files):
        failures.append(".env is tracked — secrets must stay out of the repository")
    leaks = []
    for p in files:
        if p.suffix in {".py", ".toml", ".yml", ".yaml", ".md", ".txt", ".json", ".cfg", ".ini", ".bat", ".sh"} and p.stat().st_size < 2_000_000:
            try:
                if KEY_RX.search(p.read_text(encoding="utf-8", errors="ignore")):
                    leaks.append(str(p.relative_to(ROOT)))
            except Exception:
                pass
    if leaks:
        failures.append("API-key-like strings in: " + ", ".join(leaks[:5]))
    else:
        ok.append("no tracked secrets")

    kits = sorted((ROOT / "data" / "derived" / "kits").glob("*.json"))
    stale, sourceless = [], []
    for f in kits:
        kit = json.loads(f.read_text(encoding="utf-8"))
        fresh = {r["format"]: r["passed"] for r in check_kit(kit)}
        stored = {k: bool(v.get("passed")) for k, v in (kit.get("checks") or {}).items()}
        for fmt, passed in fresh.items():
            if stored.get(fmt) is not passed:
                stale.append(f"{kit['name']}/{fmt}")
        for fact in kit.get("facts", []):
            if not str(fact.get("source", "")).strip():
                sourceless.append(f"{kit['name']}/{fact.get('id')}")
    if stale:
        failures.append("stored claim-check results disagree with a fresh run: " + ", ".join(stale[:6]))
    else:
        ok.append(f"claim-check results current for {len(kits)} kits")
    if sourceless:
        failures.append("facts without a source: " + ", ".join(sourceless[:6]))
    else:
        ok.append("every fact names its source")

    xi = ROOT / "data" / "derived" / "unseen_xi.csv"
    if xi.exists():
        rows = list(csv.DictReader(xi.open(encoding="utf-8")))
        per_country = Counter(r["team"] for r in rows)
        outside = sum(1 for r in rows if r["team"] not in BIG_THREE)
        if any(n > 3 for n in per_country.values()):
            failures.append("more than three athletes from one country: " + str(dict(per_country)))
        elif outside < 3:
            failures.append(f"only {outside} athletes from outside India/England/Australia")
        else:
            ok.append(f"XI constraints hold ({len(rows)} athletes, {outside} from outside the big three)")
    else:
        failures.append("data/derived/unseen_xi.csv missing")

    impact = ROOT / "app" / "pages" / "6_Impact_Dashboard.py"
    pages = list((ROOT / "app" / "pages").glob("*Impact*.py"))
    src = (pages[0] if pages else impact)
    if src.exists() and "SIMULATED" in src.read_text(encoding="utf-8", errors="ignore"):
        ok.append("simulated funnel stays labelled")
    else:
        failures.append("impact dashboard no longer labels the simulated funnel")

    for line in ok:
        print("PASS ", line)
    for line in failures:
        print("FAIL ", line)
    print(f"\n{len(ok)} policies hold, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
