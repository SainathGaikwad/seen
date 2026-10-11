"""Provider-agnostic LLM access. Without a key SEEN runs in TEMPLATE mode.

Set LLM_PROVIDER to gemini | nebius | anthropic | openai and the matching *_API_KEY.
  gemini   Google Gemini via google-genai (GEMINI_API_KEY)
  nebius   NVIDIA Nemotron open models served by Nebius Token Factory, OpenAI-compatible (NEBIUS_API_KEY)
All calls ask for JSON and run at low temperature. Numbers are never trusted from
the model: the claim checker verifies every figure against the fact bundle.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)
for noisy in ("google_genai", "google_genai.models", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# Model names change; the first available one in each list is used unless LLM_MODEL is set.
CANDIDATE_MODELS = {
    "gemini": ["gemini-3.8-flash", "gemini-3-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
    # NVIDIA Nemotron 3 open models on Nebius Token Factory (ids as listed in the Token Factory catalogue;
    # `GET {NEBIUS_BASE_URL}/models` shows what the account can use)
    "nebius": ["nvidia/nemotron-3-super-120b-a12b", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "nvidia/Nemotron-3_5-Lightning"],
    "anthropic": ["claude-sonnet-4-20250514"],
    "openai": ["gpt-4o-mini"],
}
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
LABELS = {"gemini": "Gemini", "nebius": "NVIDIA Nemotron on Nebius Token Factory", "anthropic": "Claude", "openai": "OpenAI"}
PACE = {"gemini": 7.0}   # seconds to wait after a served call (free tiers have per-minute limits); other providers: no pause
_resolved_model: dict[str, str] = {}
_unusable: set[str] = set()   # models that returned 404 or hit a per-day quota in this process: not asked again this run
_budget = {"remaining": 10**9, "used": 0, "cache_hits": 0, "skipped": 0}
_cache_dir: Path | None = None


def configure(max_calls: int | None = None, cache_dir: str | Path | None = None) -> None:
    """Per-run call budget (free tiers are ~20 requests/day/model) and a prompt cache so re-runs cost nothing."""
    if max_calls is not None:
        _budget["remaining"] = int(max_calls)
    if cache_dir is not None:
        global _cache_dir
        _cache_dir = Path(cache_dir)
        _cache_dir.mkdir(parents=True, exist_ok=True)


def usage() -> dict:
    return dict(_budget)


class BudgetExhausted(RuntimeError):
    pass


def provider() -> str:
    p = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if p == "gemini" and os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if p == "nebius" and os.environ.get("NEBIUS_API_KEY"):
        return "nebius"
    if p == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if p == "openai" and os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "none"


def available() -> bool:
    return provider() != "none"


def model_label() -> str:
    """Human-readable 'which model answers' for the UI, e.g. 'Gemini (gemini-3.8-flash)'."""
    p = provider()
    if p == "none":
        return "no model (template mode)"
    models = _models(p)
    return f"{LABELS.get(p, p)} ({models[0] if models else '?'})"


def _models(p: str) -> list[str]:
    """The model that answered last goes first, but the other candidates stay in the list: when the first is
    overloaded (503) for a whole retry cycle the call moves on instead of giving up."""
    override = os.environ.get("LLM_MODEL", "").strip() or (os.environ.get("NEBIUS_MODEL", "").strip() if p == "nebius" else "")
    if override:
        return [override]
    cands = list(CANDIDATE_MODELS.get(p, []))
    first = _resolved_model.get(p)
    if first in cands:
        cands.remove(first)
        cands.insert(0, first)
    return cands


def _is_daily_quota(exc: Exception) -> bool:
    """A per-day quota will not clear by waiting: move to the next model (quotas are per model)."""
    s = str(exc)
    return "PerDay" in s or "per day" in s.lower() or "_free_tier_requests" in s


def _is_not_found(exc: Exception) -> bool:
    s = str(exc)
    return "404" in s or "NOT_FOUND" in s or "not found" in s.lower() or "no longer available" in s


def _is_rate_limited(exc: Exception) -> bool:
    """429 (quota) and 503 (model overloaded) are both transient: wait and retry."""
    s = str(exc)
    return ("429" in s or "RESOURCE_EXHAUSTED" in s or "rate limit" in s.lower() or "quota" in s.lower()
            or "503" in s or "UNAVAILABLE" in s or "overloaded" in s.lower())


# Gemini "thinking" models spend output tokens on reasoning before the answer; with a small max_output_tokens the
# visible JSON gets cut off. Ask for no/low thinking where the model allows it, and remember which setting each model accepts.
_GEMINI_THINKING_VARIANTS = ({"thinking_budget": 0}, {"thinking_level": "low"}, None)
_gemini_variant: dict[str, int] = {}


def _gemini_call(client, model: str, contents: str, max_tokens: int) -> str:
    base = {"temperature": 0.2, "max_output_tokens": max(int(max_tokens), 8192), "automatic_function_calling": {"disable": True}}
    start = _gemini_variant.get(model, 0)
    last: Exception | None = None
    for i in range(start, len(_GEMINI_THINKING_VARIANTS)):
        cfg = dict(base)
        if _GEMINI_THINKING_VARIANTS[i] is not None:
            cfg["thinking_config"] = dict(_GEMINI_THINKING_VARIANTS[i])
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        except Exception as exc:
            if _GEMINI_THINKING_VARIANTS[i] is None or _is_rate_limited(exc) or _is_daily_quota(exc) or _is_not_found(exc):
                raise  # a real failure (or the plain config): let the caller's retry logic classify it
            last = exc
            log.info("model %s rejected thinking setting %s (%s); trying the next", model, _GEMINI_THINKING_VARIANTS[i], str(exc)[:80])
            continue  # an SDK/validation or 400 error for this thinking setting: try the next one
        _gemini_variant[model] = i
        try:
            fr = str(resp.candidates[0].finish_reason)
            if "MAX_TOKENS" in fr:
                log.warning("Gemini response hit max_output_tokens (%s); the JSON may be truncated", model)
        except Exception:
            pass
        return resp.text or ""
    raise last if last else RuntimeError("Gemini call failed")


# Nemotron 3 models reason before answering; the reasoning tokens are not needed for a JSON answer, so the chat
# template is asked to skip them. A server that rejects the extra field gets the plain request instead.
_NEBIUS_VARIANTS = ({"chat_template_kwargs": {"enable_thinking": False}}, None)
_nebius_variant: dict[str, int] = {}


def _nebius_call(model: str, system: str, user: str, max_tokens: int, client=None) -> str:
    from openai import OpenAI  # type: ignore
    client = client or OpenAI(api_key=os.environ["NEBIUS_API_KEY"], base_url=os.environ.get("NEBIUS_BASE_URL", NEBIUS_BASE_URL), timeout=120)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last: Exception | None = None
    for i in range(_nebius_variant.get(model, 0), len(_NEBIUS_VARIANTS)):
        kwargs = {"model": model, "temperature": 0.2, "max_tokens": max(int(max_tokens), 4096), "messages": messages}
        if _NEBIUS_VARIANTS[i] is not None:
            kwargs["extra_body"] = dict(_NEBIUS_VARIANTS[i])
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            if _NEBIUS_VARIANTS[i] is None or _is_rate_limited(exc) or _is_daily_quota(exc) or _is_not_found(exc) or "401" in str(exc):
                raise
            last = exc
            log.info("model %s rejected %s (%s); trying the plain request", model, _NEBIUS_VARIANTS[i], str(exc)[:80])
            continue
        _nebius_variant[model] = i
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", "") == "length":
            log.warning("Nemotron response hit max_tokens (%s); the JSON may be truncated", model)
        text = choice.message.content or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # strip any reasoning block that still arrives
    raise last if last else RuntimeError("Nebius call failed")


_SDK = {"gemini": "google-genai", "nebius": "openai", "openai": "openai", "anthropic": "anthropic"}


def _call(p: str, model: str, system: str, user: str, max_tokens: int) -> str:
    try:
        if p == "gemini":
            from google import genai  # type: ignore
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            return _gemini_call(client, model, f"{system}\n\n{user}", max_tokens)
        if p == "nebius":
            return _nebius_call(model, system, user, max_tokens)
        if p == "anthropic":
            import anthropic  # type: ignore
            client = anthropic.Anthropic()
            msg = client.messages.create(model=model, max_tokens=max_tokens, temperature=0.2, system=system,
                                         messages=[{"role": "user", "content": user}])
            return "".join(getattr(b, "text", "") for b in msg.content)
        if p == "openai":
            from openai import OpenAI  # type: ignore
            client = OpenAI()
            resp = client.chat.completions.create(model=model, temperature=0.2, max_tokens=max_tokens,
                                                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return resp.choices[0].message.content or ""
    except ImportError as exc:
        raise RuntimeError(f"the {_SDK.get(p, p)} package is not installed (pip install {_SDK.get(p, p)}): {exc}") from exc
    raise RuntimeError("No LLM provider configured (see .env.example)")


def complete(system: str, user: str, max_tokens: int = 2000) -> str:
    """Returns raw text (expected to be JSON). Tries candidate models on 404; backs off on rate limits."""
    p = provider()
    if p == "none":
        raise RuntimeError("No LLM provider configured (see .env.example)")
    key = hashlib.sha1(f"{p}\n{system}\n{user}".encode("utf-8")).hexdigest()
    if _cache_dir is not None:
        cf = _cache_dir / f"{key}.json"
        if cf.exists():
            try:
                cached = json.loads(cf.read_text(encoding="utf-8"))["text"]
            except Exception:
                cached = ""
            if parse_json(cached) is not None:   # a truncated or non-JSON answer is not worth keeping: ask again
                _budget["cache_hits"] += 1
                return cached
            log.info("ignoring an unusable cached answer (%s); re-requesting", cf.name)
    if _budget["remaining"] <= 0:
        raise BudgetExhausted("LLM call budget for this run is used up (raise llm.max_calls_per_run in config.yaml)")
    models = [m for m in _models(p) if m not in _unusable]
    if not models:
        _budget["skipped"] += 1
        raise RuntimeError("every candidate model is unavailable or out of daily quota for this run "
                           "(quota resets daily; run `python scripts/list_models.py` and set LLM_MODEL, or enable billing)")
    last: Exception | None = None
    RATE_WAITS = (10, 20, 40, 60)   # 429 per-minute limits clear quickly; a rejected request is not counted
    BUSY_WAITS = (20, 60, 60)       # 503 overloaded: fewer retries, since each attempt may count against the day's quota
    for model in models:
        attempt = 0
        while True:
            if _budget["remaining"] <= 0:
                raise BudgetExhausted("LLM call budget for this run is used up (raise llm.max_calls_per_run in config.yaml)")
            try:
                out = _call(p, model, system, user, max_tokens)
                _budget["remaining"] -= 1   # only requests the provider actually served count against the daily budget
                _budget["used"] += 1
                _resolved_model[p] = model
                if _cache_dir is not None and parse_json(out) is not None:   # cache only answers that parse
                    (_cache_dir / f"{key}.json").write_text(json.dumps({"model": model, "text": out}), encoding="utf-8")
                elif parse_json(out) is None:
                    log.warning("model %s returned no parseable JSON (%s chars); the template will be kept for this item", model, len(out))
                time.sleep(PACE.get(p, 0.0))  # stay under free-tier per-minute limits (rejected requests are retried, not counted)
                return out
            except Exception as exc:  # provider SDKs raise different types; classify by message
                last = exc
                if _is_daily_quota(exc):
                    log.warning("daily quota reached for %s; not using it again this run", model)
                    _unusable.add(model)
                    _resolved_model.pop(p, None)
                    break
                if _is_rate_limited(exc):
                    overloaded = "503" in str(exc) or "UNAVAILABLE" in str(exc)
                    waits = BUSY_WAITS if overloaded else RATE_WAITS
                    if attempt >= len(waits):
                        log.warning("%s still %s after %ss; trying the next model", model, "overloaded" if overloaded else "rate-limited", sum(waits))
                        break
                    log.warning("LLM %s (%s); waiting %ss", "overloaded" if overloaded else "rate-limited", model, waits[attempt])
                    time.sleep(waits[attempt])
                    attempt += 1
                    continue
                if _is_not_found(exc):
                    log.warning("model %s unavailable; not using it again this run", model)
                    _unusable.add(model)
                    break
                _budget["remaining"] -= 1   # an unexplained failure may still have been served: count it
                _budget["used"] += 1
                raise
    raise RuntimeError(f"LLM call failed for all candidate models: {str(last)[:200]}")


def quick(system: str, user: str, max_tokens: int = 1500, timeout: float = 40.0) -> str:
    """One attempt on the preferred model with a short timeout: no cache, no retries, no backoff. For interactive
    agents (the Sponsor Desk) that would rather fall back to rules than keep a person waiting. Raises on any failure."""
    p = provider()
    if p == "none":
        raise RuntimeError("No LLM provider configured (see .env.example)")
    models = [m for m in _models(p) if m not in _unusable] or _models(p)
    model = models[0]
    try:
        if p == "gemini":
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=int(timeout * 1000)))
            out = _gemini_call(client, model, f"{system}\n\n{user}", max_tokens)
        elif p == "nebius":
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=os.environ["NEBIUS_API_KEY"], base_url=os.environ.get("NEBIUS_BASE_URL", NEBIUS_BASE_URL), timeout=timeout, max_retries=0)
            out = _nebius_call(model, system, user, max_tokens, client=client)
        elif p == "openai":
            from openai import OpenAI  # type: ignore
            client = OpenAI(timeout=timeout, max_retries=0)
            resp = client.chat.completions.create(model=model, temperature=0.2, max_tokens=max_tokens,
                                                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            out = resp.choices[0].message.content or ""
        elif p == "anthropic":
            import anthropic  # type: ignore
            client = anthropic.Anthropic(timeout=timeout, max_retries=0)
            msg = client.messages.create(model=model, max_tokens=max_tokens, temperature=0.2, system=system, messages=[{"role": "user", "content": user}])
            out = "".join(getattr(b, "text", "") for b in msg.content)
        else:
            raise RuntimeError(f"unknown provider {p}")
    except Exception as exc:
        if _is_daily_quota(exc) or _is_not_found(exc):
            _unusable.add(model)
        raise
    _budget["used"] += 1
    _budget["remaining"] -= 1
    _resolved_model[p] = model
    return out


def parse_json(text: str) -> dict | None:
    """Extract the first complete JSON object from a model response (tolerates ```json fences and any
    reasoning text before the object). Returns None when no object parses, e.g. a truncated answer."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
