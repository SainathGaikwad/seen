"""SEEN's money layer: sponsorships, fan tips and payouts on PayPal (sandbox).

The PayPal calls go through PayPal's own Agent Toolkit tool handlers, vendored under vendor/paypal_agent_toolkit
(Apache-2.0; see vendor/README.md). This package puts that directory on sys.path.
"""
from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parents[2] / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
