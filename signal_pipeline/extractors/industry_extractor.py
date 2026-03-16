"""
Industry signal extractor.

Detects industry context signals that confirm the lead operates in
the target sectors: art, design, architecture, hospitality, real estate.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline._matching import compile_patterns
from signal_pipeline.signal_types import Signal, SignalType

# (pattern, weight)
_INDUSTRY_PATTERNS: list[tuple[str, float]] = [
    ("interior design", 1.0),
    ("interiorismo", 1.0),
    ("diseño de interiores", 1.0),
    ("architecture", 1.0),
    ("arquitectura", 1.0),
    ("collectible design", 1.0),
    ("diseño de colección", 1.0),
    ("sculpture", 0.9),
    ("escultura", 0.9),
    ("art gallery", 1.0),
    ("galería de arte", 1.0),
    ("galeria de arte", 1.0),
    ("contemporary art", 1.0),
    ("arte contemporáneo", 1.0),
    ("arte contemporaneo", 1.0),
    ("hospitality design", 1.0),
    ("hotel design", 1.0),
    ("diseño hotelero", 1.0),
    ("real estate", 0.8),
    ("bienes raíces", 0.8),
    ("bienes raices", 0.8),
    ("inmobiliaria", 0.8),
    ("luxury real estate", 0.9),
    ("design studio", 0.9),
    ("estudio de diseño", 0.9),
    ("art studio", 0.9),
    ("estudio de arte", 0.9),
    ("atelier", 0.9),
    ("furniture design", 0.8),
    ("diseño de mobiliario", 0.8),
    ("object design", 0.8),
    ("diseño de objetos", 0.8),
    ("decoración", 0.7),
    ("decoration", 0.7),
    ("artes decorativas", 0.8),
    ("decorative arts", 0.8),
    ("fine art", 0.9),
    ("bellas artes", 0.9),
    ("landscape architecture", 0.8),
    ("arquitectura paisajista", 0.8),
    # ── Portuguese (PT-BR / PT-PT) ─────────────────────────────────────────────
    ("arquitetura", 1.0),
    ("design de interiores", 1.0),
    ("galeria de arte", 1.0),
    ("arte contemporânea", 1.0),
    ("arte contemporanea", 1.0),
    ("design de mobiliário", 0.8),
    ("design de moveis", 0.8),
    ("estúdio de design", 0.9),
    ("estudio de design", 0.9),
    ("design hoteleiro", 1.0),
    ("imobiliária", 0.8),
    ("imobiliaria", 0.8),
    ("decoração", 0.7),
    ("decoracao", 0.7),
    ("belas artes", 0.9),
    ("escultura", 0.9),      # already in ES list but PT spelling identical
]

_COMPILED = compile_patterns(_INDUSTRY_PATTERNS)


def extract_industry_signals(lead: Lead) -> list[Signal]:
    """Extract industry context signals from bio, category, and lead_type."""
    signals: list[Signal] = []

    fields = {
        "bio": (lead.bio or "").lower(),
        "category": (lead.category or "").lower(),
        "lead_type": (lead.lead_type or "").lower(),
    }

    for field_name, text in fields.items():
        if not text:
            continue
        for pattern, compiled_re, weight in _COMPILED:
            if compiled_re.search(text):
                signals.append(Signal(
                    signal_type=SignalType.INDUSTRY,
                    value=pattern,
                    source=field_name,
                    weight=weight,
                ))

    seen: dict[str, Signal] = {}
    for s in signals:
        if s.value not in seen or s.weight > seen[s.value].weight:
            seen[s.value] = s
    return list(seen.values())
