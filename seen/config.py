"""Configuration loading (config.yaml + environment)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    # resolve paths relative to project root
    for key, value in cfg["paths"].items():
        p = Path(value)
        cfg["paths"][key] = str(p if p.is_absolute() else ROOT / p)
    for key in ("raw", "cache", "derived", "manual"):
        Path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)
    Path(cfg["paths"]["db"]).parent.mkdir(parents=True, exist_ok=True)
    return cfg


def user_agent() -> str:
    return os.environ.get("SEEN_USER_AGENT", "SEEN-hackathon/0.1 (https://github.com/; contact unknown)")


def market_tier(team: str, cfg: dict) -> int:
    if team in cfg["markets"].get("tier3", []):
        return 3
    if team in cfg["markets"].get("tier2", []):
        return 2
    return 1
