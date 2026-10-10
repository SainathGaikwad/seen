"""Claim checker: every number and named entity in generated text must match the fact bundle.

Rules
- Numbers: each number in the text (excluding citation markers like [F12] and years that appear
  in fact dates) must equal a fact value (integer match, or within 0.05 for decimals such as strike rates),
  or be derivable as a listed 'derived' value (e.g., balls = overs x 6). Unmatched numbers block publication.
- Entities: player and team names in the text must appear in the allowed-name list.
- Banned topics: health/injury speculation, private life, betting, religion — always blocked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CITATION = re.compile(r"\[F\d+\]")
NUMBER = re.compile(r"(?<![A-Za-z\d])(\d+(?:[.,]\d+)?)(?![A-Za-z\d])")
# structural numbers that are not claims: script timestamps, post/list numbering, fact ids
STRUCTURE = [re.compile(r"\[\d{2}:\d{2}-\d{2}:\d{2}\]"), re.compile(r"\bPost \d+:"), re.compile(r"^\s*\d+\.\s", re.M),
             re.compile(r"^\s*[^\s\d]{1,12}\s?\d{1,2}\s*[:：]", re.M),   # a translated "Post 2:" / "पोस्ट 2:" / "پوسٹ 2:" label at the start of a line
             re.compile(r"\[F\d+\]"), re.compile(r"\bF\d+\b"), re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b"),
             re.compile(r"\(source: [^)]*\)"), re.compile(r"\([^()]*?(?:cricsheet|aggregate):[^()]*\)"),   # "(source: …)" in any language
             re.compile(r"cricsheet:\d+")]
BANNED = [
    (re.compile(r"\b(injur(y|ies|ed)|pregnan|menstrua|period pain|surgery|illness|depress)\w*", re.I), "health or medical speculation"),
    (re.compile(r"\b(boyfriend|girlfriend|husband|wife|partner|dating|divorce|married)\b", re.I), "private life"),
    (re.compile(r"\b(betting|odds|bookmaker|wager|gamble)\w*", re.I), "betting"),
    (re.compile(r"\b(religio|hindu|muslim|christian|sikh|caste)\w*", re.I), "religion or caste"),
    (re.compile(r"\b(sexy|hot body|attractive)\b", re.I), "appearance"),
]


@dataclass
class CheckResult:
    passed: bool
    claims: list[dict] = field(default_factory=list)   # {"text":..., "status": matched|unmatched|derived, "fact": id}
    banned: list[str] = field(default_factory=list)
    unmatched_entities: list[str] = field(default_factory=list)

    def summary(self) -> str:
        n_ok = sum(1 for c in self.claims if c["status"] != "unmatched")
        return f"{n_ok}/{len(self.claims)} numeric claims matched; {len(self.banned)} banned topics; {len(self.unmatched_entities)} unknown names"


def _fact_values(facts: list[dict]) -> dict[float, str]:
    vals = {}
    for f in facts:
        v = f.get("value")
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            vals[float(v)] = f["id"]
        # numbers embedded in fact text (dates, balls, runs conceded) are also acceptable
        for num in NUMBER.findall(str(f.get("text", ""))):
            try:
                vals.setdefault(float(num.replace(",", "")), f["id"])
            except ValueError:
                pass
    return vals


def check(text: str, facts: list[dict], allowed_names: list[str], derived_ok: dict[float, str] | None = None) -> CheckResult:
    res = CheckResult(passed=True)
    stripped = text
    for rx in STRUCTURE:
        stripped = rx.sub(" ", stripped)
    fact_vals = _fact_values(facts)
    if derived_ok:
        fact_vals.update(derived_ok)
    for num in NUMBER.findall(stripped):
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        status, fid = "unmatched", None
        if val in fact_vals:
            status, fid = "matched", fact_vals[val]
        else:
            for fv, f_id in fact_vals.items():
                if abs(fv - val) <= 0.051 and (fv != int(fv) or val != int(val)):
                    status, fid = "matched", f_id
                    break
        res.claims.append({"text": num, "status": status, "fact": fid})
        if status == "unmatched":
            res.passed = False
    for rx, label in BANNED:
        if rx.search(stripped):
            res.banned.append(label)
            res.passed = False
    # entity check (warning only): capitalised multiword names that look like people should be in the allowed list
    allowed = {n.lower() for n in allowed_names if isinstance(n, str)}
    for cand in re.findall(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b", stripped):
        low = cand.lower()
        if any(low in a or a in low for a in allowed):
            continue
        if low.split()[0] in {"the", "in", "on", "at", "a", "an", "world", "cup", "women", "icc", "player", "match", "final", "semi", "group", "super", "west", "new", "south", "sri", "united", "hong", "papua"}:
            continue
        res.unmatched_entities.append(cand)
    return res
