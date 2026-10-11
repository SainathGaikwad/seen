"""Shared helpers for the SEEN Streamlit app."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seen.config import load_config  # noqa: E402


def _secrets_to_env() -> None:
    """Hosted Streamlit (Community Cloud) keeps keys in st.secrets; the pipeline code reads os.environ.
    Copy top-level string secrets across once, never overriding a value the environment already has."""
    import os
    try:
        for k, v in st.secrets.items():
            if isinstance(v, str) and k.isupper():
                os.environ.setdefault(k, v)
    except Exception:   # no secrets file: normal for local runs
        pass


_secrets_to_env()
CFG = load_config()
DERIVED = Path(CFG["paths"]["derived"])
MANUAL = Path(CFG["paths"]["manual"])

CSS = """
<style>
:root { --seen-ink:#0f172a; --seen-muted:#64748b; --seen-accent:#0ea5a4; --seen-warn:#b45309; --seen-card:#ffffff; --seen-line:#e2e8f0; }
.block-container { padding-top: 1.2rem; max-width: 1180px; }
.seen-banner { background:#fff7ed; border:1px solid #fed7aa; color:#7c2d12; padding:.5rem .8rem; border-radius:8px; font-size:.85rem; margin-bottom:.8rem; }
.seen-banner.live { background:#ecfeff; border-color:#a5f3fc; color:#155e75; }
.presented { background:#eef2ff; color:#3730a3; border-radius:999px; padding:1px 8px; font-weight:600; }
.xi-card { border:1px solid var(--seen-line); border-radius:14px; padding:.9rem 1rem; background:var(--seen-card); box-shadow:0 1px 2px rgba(15,23,42,.06); min-height:172px; }
.xi-card h4 { margin:0 0 .15rem 0; font-size:1.02rem; color:var(--seen-ink); }
.xi-card .meta { color:var(--seen-muted); font-size:.8rem; margin-bottom:.45rem; }
.xi-card .ranks { display:flex; flex-wrap:wrap; gap:.4rem .5rem; font-size:.8rem; margin-bottom:.45rem; }
.xi-card .ranks span { background:#f1f5f9; border-radius:999px; padding:.1rem .55rem; white-space:nowrap; }
.xi-card .why { font-size:.8rem; color:#334155; line-height:1.3; }
.gapbar { height:6px; background:#e2e8f0; border-radius:4px; overflow:hidden; margin:.35rem 0 .5rem 0; }
.gapbar > div { height:6px; background:linear-gradient(90deg,#0ea5a4,#f59e0b); }
.badge { display:inline-block; font-size:.7rem; padding:.1rem .45rem; border-radius:6px; background:#ecfdf5; color:#065f46; margin-left:.3rem; }
.badge.warn { background:#fef3c7; color:#92400e; }
.badge.no { background:#fee2e2; color:#991b1b; }
.phone { width:360px; margin:0 auto; border:12px solid #0f172a; border-radius:36px; padding:14px 12px; background:#f8fafc; box-shadow:0 10px 30px rgba(15,23,42,.25); }
.fan-card { background:#fff; border-radius:16px; padding:.9rem; margin-bottom:.7rem; border:1px solid #e2e8f0; }
.fan-card .kicker { font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:#0ea5a4; }
.fan-card h3 { margin:.1rem 0 .3rem 0; font-size:1.15rem; }
.fan-card p { font-size:.86rem; color:#334155; margin:.2rem 0; }
.fact { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:.78rem; color:#334155; background:#f8fafc; border-left:3px solid #0ea5a4; padding:.25rem .5rem; margin:.15rem 0; }
.ok { color:#047857; } .bad { color:#b91c1c; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _read_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


def load_csv(name: str) -> pd.DataFrame:
    p = DERIVED / name
    if not p.exists():
        return pd.DataFrame()
    return _read_csv(str(p), p.stat().st_mtime)


def load_json(name: str, default=None):
    p = DERIVED / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(name: str, data) -> None:
    (DERIVED / name).write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def load_kit(player_id: str) -> dict | None:
    p = DERIVED / "kits" / f"{player_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_kit(kit: dict) -> None:
    (DERIVED / "kits" / f"{kit['player_id']}.json").write_text(json.dumps(kit, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def load_localized(player_id: str, lang: str) -> dict | None:
    p = DERIVED / "localized" / f"{player_id}_{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def meta() -> dict:
    return load_json("run_meta.json", {}) or {}


def require_run() -> bool:
    if not (DERIVED / "unseen_xi.csv").exists():
        st.warning("No pipeline output found. Run `python -m seen.pipeline all --source cricsheet --attention live` "
                   "(or `--attention fixture` for a synthetic demo) and refresh.")
        return False
    return True


def data_banner() -> None:
    m = meta()
    src = m.get("attention_source") or "unknown"
    live = "SYNTHETIC" not in src.upper()
    story = m.get("story_mode", "template")
    provider = m.get("llm_provider", "none")
    from seen import llm  # noqa: E402  (local import: the app must still render when no LLM SDK is installed)
    live_model = llm.model_label()
    txt = (f"<b>Attention data:</b> {src} · <b>Window:</b> {m.get('window','?')} · <b>Stories:</b> {story} "
           f"(pipeline LLM: {provider}; live: {live_model}) · <b>Performance data:</b> Cricsheet (ODC-BY)")
    if not live:
        txt = "⚠️ " + txt + " · <b>Fan funnel numbers on the dashboard are SIMULATED where labelled.</b>"
    st.markdown(f'<div class="seen-banner {"live" if live else ""}">{txt}</div>', unsafe_allow_html=True)


def consent_map() -> dict:
    p = MANUAL / "consent.csv"
    if not p.exists():
        return {}
    df = pd.read_csv(p)
    return {str(r.player_id): str(r.consent).strip().lower() in ("yes", "true", "1") for _, r in df.iterrows()}


def set_consent(player_id: str, value: bool) -> None:
    p = MANUAL / "consent.csv"
    df = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["player_id", "consent"])
    df = df[df.player_id.astype(str) != str(player_id)]
    df = pd.concat([df, pd.DataFrame([{"player_id": player_id, "consent": "yes" if value else "no"}])], ignore_index=True)
    df.to_csv(p, index=False)


def publications() -> list[dict]:
    return load_json("publications.json", []) or []


def add_publication(rec: dict) -> None:
    """One live publication per athlete: publishing her again replaces the earlier record (the dashboard measures the latest)."""
    pubs = [p for p in publications() if p.get("player_id") != rec.get("player_id")]
    pubs.append(rec)
    save_json("publications.json", pubs)


def pick_athlete(label: str, df: pd.DataFrame, key: str = "selected_player"):
    """Athlete selectbox shared by the pages: keeps the athlete chosen on another page (session state) as the default,
    otherwise the first athlete of the frame. Returns the selected row."""
    names = df["name"].tolist()
    pre = st.session_state.get(key)
    match = df[df.player_id == pre] if pre else df.iloc[0:0]
    default = match["name"].iloc[0] if not match.empty else names[0]
    pick = st.selectbox(label, names, index=names.index(default))
    row = df[df["name"] == pick].iloc[0]
    st.session_state[key] = row.player_id
    return row


def tidy_sentence(text: str) -> str:
    """Display clean-up after citations are stripped: no space before punctuation, single spaces."""
    import re
    text = re.sub(r"\s+([.,;:!?।۔])", r"\1", text)   # incl. the Devanagari danda and the Urdu full stop
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def fmt_int(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "–"


def gap_bar(gap_z: float) -> str:
    pct = max(4, min(100, int(50 + 20 * float(gap_z or 0))))
    return f'<div class="gapbar"><div style="width:{pct}%"></div></div>'


def xi_card(r, show_slot: bool = True) -> str:
    art = '<span class="badge no">no Wikipedia article</span>' if bool(r.no_article) else ""
    conf = str(r.gap_confidence)
    slot = f"#{int(r.xi_slot)} · " if show_slot and "xi_slot" in r else ""
    why = str(r.why_now) if "why_now" in r and isinstance(r.why_now, str) else ""
    return (f'<div class="xi-card"><h4>{slot}{r["name"]}</h4>'
            f'<div class="meta">{r.team} · {r.role} · {int(r.matches)} matches{art}</div>'
            f'<div class="ranks"><span>impact #{int(r.impact_rank)}</span><span>attention #{int(r.attention_rank)}</span>'
            f'<span>gap {conf}</span></div>{gap_bar(r.gap_z)}<div class="why">{why}</div></div>')


def today() -> date:
    w = load_json("window.json", {}) or {}
    return pd.to_datetime(w.get("end", date.today().isoformat())).date()
