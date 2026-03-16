"""
Role signal extractor.

Detects professional roles that indicate a specifier, buyer, or influencer
in the art/design/architecture ecosystem.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline._matching import compile_patterns, wb_search
from signal_pipeline.signal_types import Signal, SignalType

# (pattern, weight)
_ROLE_PATTERNS: list[tuple[str, float]] = [
    ("architect", 1.0),
    ("arquitecto", 1.0),
    ("arquitecta", 1.0),
    ("interior designer", 1.0),
    ("interiorista", 1.0),
    ("interior design", 0.9),
    ("diseño de interiores", 0.9),
    ("curator", 1.0),
    ("curadora", 1.0),
    ("curador", 1.0),
    ("gallery director", 1.0),
    ("director de galería", 1.0),
    ("gallerist", 1.0),
    ("galerista", 1.0),
    ("art advisor", 1.0),
    ("art consultant", 1.0),
    ("asesor de arte", 1.0),
    ("asesora de arte", 1.0),
    ("design director", 1.0),
    ("director de diseño", 1.0),
    ("directora de diseño", 1.0),
    ("procurement", 0.9),
    ("purchasing manager", 0.9),
    ("art director", 0.9),
    ("director creativo", 0.9),
    ("directora creativa", 0.9),
    ("creative director", 0.9),
    ("founder", 0.8),
    ("fundador", 0.8),
    ("fundadora", 0.8),
    ("co-founder", 0.8),
    ("cofundador", 0.8),
    ("partner", 0.7),
    ("socio", 0.7),
    ("socia", 0.7),
    ("collector", 1.0),
    ("coleccionista", 1.0),
    ("developer", 0.8),
    ("promotor", 0.8),
    ("promotora", 0.8),
    ("developer inmobiliario", 0.9),
    ("real estate developer", 0.9),
    ("sculptor", 0.7),
    ("escultor", 0.7),
    ("escultora", 0.7),
    ("hospitality designer", 1.0),
    ("hotel designer", 1.0),
    ("design consultant", 0.9),
    ("consultor de diseño", 0.9),
    ("art director", 0.9),
    # ── Portuguese (PT-BR / PT-PT) ─────────────────────────────────────────────
    ("arquiteto", 1.0),
    ("arquiteta", 1.0),
    ("designer de interiores", 1.0),
    ("decorador", 0.8),
    ("decoradora", 0.8),
    ("curador", 0.9),       # already covered in ES but explicit for PT
    ("curadora", 0.9),
    ("galerista", 0.9),
    ("colecionador", 1.0),
    ("colecionadora", 1.0),
    ("consultor de arte", 1.0),
    ("consultora de arte", 1.0),
    ("diretor criativo", 0.9),
    ("diretora criativa", 0.9),
    ("comprador", 0.8),
    ("compradora", 0.8),
    ("incorporador", 0.9),   # real estate developer PT-BR
    ("incorporadora", 0.9),
]

# Pre-compiled for word-boundary matching (compiled once at import)
_COMPILED = compile_patterns(_ROLE_PATTERNS)


def extract_role_signals(lead: Lead) -> list[Signal]:
    """Extract role signals from bio, category, and lead_type."""
    signals: list[Signal] = []

    fields_to_check = {
        "bio": (lead.bio or "").lower(),
        "category": (lead.category or "").lower(),
        "lead_type": (lead.lead_type or "").lower(),
    }

    for field_name, text in fields_to_check.items():
        if not text:
            continue
        for pattern, compiled_re, weight in _COMPILED:
            if compiled_re.search(text):
                signals.append(Signal(
                    signal_type=SignalType.ROLE,
                    value=pattern,
                    source=field_name,
                    weight=weight,
                ))

    # Deduplicate by value — keep highest weight occurrence
    seen: dict[str, Signal] = {}
    for s in signals:
        if s.value not in seen or s.weight > seen[s.value].weight:
            seen[s.value] = s
    return list(seen.values())
