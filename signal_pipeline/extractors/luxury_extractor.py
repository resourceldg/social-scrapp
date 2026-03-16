"""
Luxury signal extractor.

Detects premium market positioning signals that indicate the lead operates
in the luxury / high-end segment of art, design, or hospitality.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline._matching import compile_patterns
from signal_pipeline.signal_types import Signal, SignalType

# (pattern, weight)
_LUXURY_PATTERNS: list[tuple[str, float]] = [
    ("luxury", 1.0),
    ("lujo", 1.0),
    ("bespoke", 1.0),
    ("a medida", 1.0),
    ("premium", 0.5),      # too generic on its own — reduced from 0.9
    ("curated", 0.3),      # marketing buzzword in 2025 — minimal weight
    ("curada", 0.3),
    ("curado", 0.3),
    ("private collection", 1.0),
    ("colección privada", 1.0),
    ("coleccion privada", 1.0),
    ("high-end", 1.0),
    ("high end", 1.0),
    ("exclusivo", 0.5),    # generic marketing term — reduced from 0.9
    ("exclusiva", 0.5),
    ("exclusive", 0.5),
    ("obra única", 1.0),
    ("obra unica", 1.0),
    ("one of a kind", 1.0),
    ("limited edition", 0.9),
    ("edición limitada", 0.9),
    ("edicion limitada", 0.9),
    ("handcrafted", 0.8),
    ("artesanal", 0.8),
    ("artisanal", 0.8),
    ("craftsmanship", 0.8),
    ("artesanía", 0.8),
    ("artesania", 0.8),
    ("boutique", 0.5),     # "boutique hotel" is strong but bare "boutique" is not
    ("maison", 0.9),
    ("atelier", 0.9),
    ("prestige", 0.8),
    ("prestigious", 0.8),
    ("ultra-luxury", 1.0),
    ("ultra luxury", 1.0),
    ("five-star", 0.9),
    ("5-star", 0.9),
]

_COMPILED = compile_patterns(_LUXURY_PATTERNS)


def extract_luxury_signals(lead: Lead) -> list[Signal]:
    """Extract luxury/premium positioning signals from bio and category."""
    signals: list[Signal] = []

    fields = {
        "bio": (lead.bio or "").lower(),
        "category": (lead.category or "").lower(),
    }

    for field_name, text in fields.items():
        if not text:
            continue
        for pattern, compiled_re, weight in _COMPILED:
            if compiled_re.search(text):
                signals.append(Signal(
                    signal_type=SignalType.LUXURY,
                    value=pattern,
                    source=field_name,
                    weight=weight,
                ))

    seen: dict[str, Signal] = {}
    for s in signals:
        if s.value not in seen or s.weight > seen[s.value].weight:
            seen[s.value] = s
    return list(seen.values())
