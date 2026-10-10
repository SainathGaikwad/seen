"""Print the Gemini models your key can use (helps pick LLM_MODEL when names change).

    python scripts\\list_models.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root, so `seen` imports work from anywhere

from seen.config import ROOT  # noqa: E402  (importing loads .env)

try:
    from google import genai
except ImportError:
    raise SystemExit("pip install google-genai")

if not os.environ.get("GEMINI_API_KEY"):
    raise SystemExit(f"GEMINI_API_KEY is not set (put it in {ROOT / '.env'})")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in client.models.list():
    name = getattr(m, "name", "")
    actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
    if "generateContent" in " ".join(map(str, actions)) or not actions:
        print(name.replace("models/", ""))
