"""
Market signal extractor.

Detects geographic market signals indicating the lead operates in
or targets high-value markets relevant to the art/design ecosystem.

Tier 1 markets: primary acquisition targets (Miami, Madrid, Barcelona, etc.)
Tier 2 markets: secondary markets with strong premium design activity
"""
from __future__ import annotations

from models import Lead
from signal_pipeline._matching import compile_patterns
from signal_pipeline.signal_types import Signal, SignalType

# (pattern, weight)
_MARKET_PATTERNS: list[tuple[str, float]] = [
    # ── Tier 1: primary target markets ────────────────────────────────────────
    ("miami", 1.0),
    ("madrid", 1.0),
    ("barcelona", 1.0),
    ("cdmx", 1.0),
    ("ciudad de méxico", 1.0),
    ("ciudad de mexico", 1.0),
    ("mexico city", 1.0),
    ("punta del este", 1.0),
    ("são paulo", 1.0),
    ("sao paulo", 1.0),
    ("lisbon", 1.0),
    ("lisboa", 1.0),
    # ── Tier 2: secondary premium markets ─────────────────────────────────────
    ("new york", 0.9),
    ("nueva york", 0.9),
    ("los angeles", 0.8),
    ("london", 0.9),
    ("londres", 0.9),
    ("paris", 0.9),
    ("parís", 0.9),
    ("dubai", 0.9),
    ("abu dhabi", 0.8),
    ("montecarlo", 0.9),
    ("monaco", 0.9),
    ("aspen", 0.9),
    ("hamptons", 0.8),
    ("palm beach", 0.8),
    ("bogotá", 0.8),
    ("bogota", 0.8),
    ("buenos aires", 0.9),
    ("santiago", 0.7),
    ("monterrey", 0.8),
    ("guadalajara", 0.7),
    ("cancún", 0.7),
    ("cancun", 0.7),
    ("tulum", 0.8),
    ("marbella", 0.8),
    ("ibiza", 0.7),
    ("milan", 0.9),
    ("milán", 0.9),
    ("zürich", 0.8),
    ("zurich", 0.8),
    ("geneva", 0.8),
    ("ginebra", 0.8),
    ("singapore", 0.8),
    ("hong kong", 0.8),
    ("los cabos", 0.8),
    ("cabo san lucas", 0.8),
    # ── Brazilian cities (PT-BR market) ───────────────────────────────────────
    ("rio de janeiro", 0.8),
    ("río de janeiro", 0.8),
    ("belo horizonte", 0.7),
    ("brasília", 0.7),
    ("brasilia", 0.7),
    ("curitiba", 0.7),
    ("porto alegre", 0.7),
    # ── Portuguese cities ─────────────────────────────────────────────────────
    ("porto", 0.7),
    # ── Italian cities (Milan already covered, add Rome) ─────────────────────
    ("roma", 0.7),
    ("rome", 0.7),
]

_COMPILED = compile_patterns(_MARKET_PATTERNS)


def extract_market_signals(lead: Lead) -> list[Signal]:
    """Extract geographic market signals from bio, city, country, and category."""
    signals: list[Signal] = []

    fields = {
        "bio": (lead.bio or "").lower(),
        "city": (lead.city or "").lower(),
        "country": (lead.country or "").lower(),
        "category": (lead.category or "").lower(),
    }

    for field_name, text in fields.items():
        if not text:
            continue
        for pattern, compiled_re, weight in _COMPILED:
            if compiled_re.search(text):
                signals.append(Signal(
                    signal_type=SignalType.MARKET,
                    value=pattern,
                    source=field_name,
                    weight=weight,
                ))

    seen: dict[str, Signal] = {}
    for s in signals:
        if s.value not in seen or s.weight > seen[s.value].weight:
            seen[s.value] = s
    return list(seen.values())
