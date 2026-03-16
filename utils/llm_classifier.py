"""
Local LLM-based lead classifier using Ollama.

Uses qwen2.5:1.5b (~1GB RAM, CPU-only) to analyze bio text and return:
  - buying_intent   : 0–10 (likelihood of buying/specifying luxury art/design)
  - lead_type       : refined classification
  - reason          : one-line explanation

Falls back gracefully if Ollama is not running or model not available.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from typing import TypedDict

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_MODEL      = "qwen2.5:1.5b"
_TIMEOUT    = 15  # seconds per request

_PROMPT_TEMPLATE = """\
Eres un experto en identificar compradores de arte contemporáneo, diseño de colección y decoración de lujo.

Analiza esta bio profesional y responde ÚNICAMENTE con un JSON válido, sin texto adicional:

Bio: {bio}

Responde en este formato exacto:
{{
  "buying_intent": <número 0-10>,
  "lead_type": "<uno de: collector, interior_designer, gallery_director, art_advisor, hospitality_designer, architect, curator, none>",
  "reason": "<máximo 15 palabras explicando el score>"
}}

Criterios de buying_intent:
- 8-10: comprador directo o especificador activo de arte/diseño de lujo
- 5-7: profesional relacionado que influye en compras (diseñador, curador)
- 2-4: sector relacionado pero sin señal clara de compra
- 0-1: sin relación con el nicho
"""


class ClassificationResult(TypedDict):
    buying_intent: int
    lead_type: str
    reason: str
    source: str  # "llm" or "fallback"


def _call_ollama(bio: str) -> dict | None:
    payload = json.dumps({
        "model": _MODEL,
        "prompt": _PROMPT_TEMPLATE.format(bio=bio[:600]),
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 120},
    }).encode()

    req = urllib.request.Request(
        _OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            raw = data.get("response", "").strip()
            # Extract JSON from response (LLM sometimes adds extra text).
            # Use non-nested match to avoid greedy capture across multiple objects.
            m = re.search(r'\{[^{}]*\}', raw)
            if m:
                return json.loads(m.group())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        pass
    return None


def classify_bio(bio: str, existing_lead_type: str = "") -> ClassificationResult:
    """Classify a lead bio using local Ollama LLM.

    Returns ClassificationResult. On any error falls back to a neutral result
    so the enrichment pipeline is never blocked.
    """
    if not bio or len(bio.strip()) < 20:
        return ClassificationResult(
            buying_intent=0,
            lead_type=existing_lead_type or "none",
            reason="bio too short to classify",
            source="fallback",
        )

    result = _call_ollama(bio)
    if result:
        return ClassificationResult(
            buying_intent=max(0, min(10, int(result.get("buying_intent", 0)))),
            lead_type=result.get("lead_type", existing_lead_type or "none"),
            reason=result.get("reason", ""),
            source="llm",
        )

    logger.debug("Ollama unavailable — skipping LLM classification.")
    return ClassificationResult(
        buying_intent=0,
        lead_type=existing_lead_type or "none",
        reason="ollama unavailable",
        source="fallback",
    )


def is_ollama_available() -> bool:
    """Quick check if Ollama is running and the model is loaded."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return any(_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False
