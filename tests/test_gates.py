"""The claim gate CLI and the governance policies: what the pipeline and the Editor-in-chief flow rely on."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KITS = ROOT / "data" / "derived" / "kits"


def run(*args, **kw):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=300, **kw)


def test_claim_gate_passes_the_shipped_kits():
    r = run("scripts/check_kits.py", "--translations", "--format", "json")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    report = json.loads(r.stdout)
    assert report["blocked"] == 0
    assert {row["language"] for row in report["rows"]} >= {"en", "hi"}


def test_claim_gate_blocks_a_made_up_number(tmp_path):
    src = sorted(KITS.glob("*.json"))[0]
    kit = json.loads(src.read_text(encoding="utf-8"))
    kit["formats"]["article"] += " She also scored 999 runs in the final."
    kits = tmp_path / "kits"
    kits.mkdir()
    (kits / src.name).write_text(json.dumps(kit), encoding="utf-8")
    r = run("scripts/check_kits.py", "--kits", str(kits), "--format", "json")
    assert r.returncode == 1
    rows = {row["format"]: row for row in json.loads(r.stdout)["rows"]}
    assert rows["article"]["passed"] is False
    assert any("999" in b for b in rows["article"]["blocked"])
    assert rows["video_script"]["passed"] is True


def test_governance_policies_hold():
    r = run("scripts/policy_check.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 failed" in r.stdout
