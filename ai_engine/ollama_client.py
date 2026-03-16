"""
Ollama client — low-level JSON-mode interface to the local Ollama API.

Improvements over utils/llm_classifier._call_ollama():
  - Configurable model (defaults to best available: qwen2.5:7b → 3b → 1.5b)
  - Strict JSON extraction with nested-object support
  - Retry with exponential backoff (network hiccups)
  - Per-call timeout control
  - Availability check caches result for N seconds

Usage
-----
    from ai_engine.ollama_client import call_ollama, is_ai_available, get_model

    if is_ai_available():
        result = call_ollama(prompt, max_tokens=300)
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from functools import lru_cache

logger = logging.getLogger(__name__)

_OLLAMA_BASE = "http://localhost:11434"
_GENERATE_URL = f"{_OLLAMA_BASE}/api/generate"
_TAGS_URL = f"{_OLLAMA_BASE}/api/tags"

# Model preference order — use best available
_MODEL_PREFERENCE = ["qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b", "llama3.2:3b", "mistral:7b"]

# Availability cache TTL in seconds (avoid hammering Ollama on every lead)
_AVAIL_CACHE_TTL = 120
_avail_cache: tuple[float, bool] | None = None

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_BARE_RE  = re.compile(r"\{[\s\S]*\}")   # greedy — handles nested objects


def _extract_json(text: str) -> dict | None:
    """Extract the first valid JSON object from an LLM response string."""
    # Try fenced code block first
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare JSON object
    m = _JSON_BARE_RE.search(text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _http_post(url: str, payload: dict, timeout: int) -> dict | None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def get_model() -> str:
    """Return the best available Ollama model name, or the fallback."""
    try:
        req = urllib.request.Request(_TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            available = {m["name"] for m in data.get("models", [])}
            for preferred in _MODEL_PREFERENCE:
                base = preferred.split(":")[0]
                for name in available:
                    if base in name:
                        return name
    except Exception:
        pass
    return _MODEL_PREFERENCE[-1]   # fallback


def is_ai_available() -> bool:
    """Return True if Ollama is running and at least one usable model is loaded.
    Result is cached for _AVAIL_CACHE_TTL seconds."""
    global _avail_cache
    now = time.monotonic()
    if _avail_cache is not None:
        ts, val = _avail_cache
        if now - ts < _AVAIL_CACHE_TTL:
            return val

    available = False
    try:
        req = urllib.request.Request(_TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            available = any(
                pref.split(":")[0] in m
                for pref in _MODEL_PREFERENCE
                for m in models
            )
    except Exception:
        pass

    _avail_cache = (now, available)
    return available


def call_ollama(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.1,
    timeout: int = 25,
    retries: int = 2,
) -> dict | None:
    """
    Call the local Ollama API and return the first JSON object in the response.

    Parameters
    ----------
    prompt : str
        Full prompt string (system + user combined).
    max_tokens : int
        Maximum tokens to generate.
    temperature : float
        0.0 = deterministic, higher = more creative.
    timeout : int
        Per-attempt timeout in seconds.
    retries : int
        Number of retry attempts on transient errors.

    Returns
    -------
    dict | None
        Parsed JSON dict from the response, or None on failure.
    """
    model = get_model()
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    for attempt in range(retries + 1):
        response = _http_post(_GENERATE_URL, payload, timeout)
        if response:
            raw = response.get("response", "").strip()
            parsed = _extract_json(raw)
            if parsed:
                return parsed
            logger.debug("Ollama response had no valid JSON (attempt %d): %s", attempt, raw[:200])
        if attempt < retries:
            time.sleep(1.5 ** attempt)

    logger.debug("call_ollama failed after %d attempts", retries + 1)
    return None
