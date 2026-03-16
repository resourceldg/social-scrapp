"""
Project signal extractor.

Project signals are the highest-value signals in the system because they
imply active need and purchase timing. Recency is the key differentiator:
"opening soon" >> "renovation" >> generic project language.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline._matching import compile_patterns
from signal_pipeline.signal_types import Signal, SignalType

# (pattern, weight, recency_hint)
# recency_hint=True means the signal implies imminent or ongoing activity
_PROJECT_PATTERNS: list[tuple[str, float, bool]] = [
    # ── Strong recency (opening/launching imminently) ─────────────────────────
    ("opening soon", 1.5, True),
    ("abriendo pronto", 1.5, True),
    ("próxima apertura", 1.5, True),
    ("proxima apertura", 1.5, True),
    ("launching soon", 1.5, True),
    ("coming soon", 1.4, True),
    ("próximamente", 1.4, True),
    ("proximamente", 1.4, True),
    ("under construction", 1.4, True),
    ("en construcción", 1.4, True),
    ("en construccion", 1.4, True),
    ("in progress", 1.3, True),
    ("en proceso", 1.3, True),
    ("currently working on", 1.3, True),
    ("trabajando en", 1.3, True),
    ("new project", 1.2, True),
    ("nuevo proyecto", 1.2, True),
    ("nueva apertura", 1.2, True),
    ("new opening", 1.2, True),
    ("obra en curso", 1.2, True),
    ("proyecto en curso", 1.2, True),
    ("project in development", 1.1, True),
    # ── Active project types (present-tense but less temporal) ────────────────
    ("renovation", 1.1, False),
    ("renovación", 1.1, False),
    ("renovacion", 1.1, False),
    ("installation", 1.0, False),
    ("instalación", 1.0, False),
    ("instalacion", 1.0, False),
    ("fit-out", 1.1, False),
    ("fitout", 1.1, False),
    ("hotel project", 1.2, False),
    ("proyecto hotelero", 1.2, False),
    ("residential project", 1.1, False),
    ("proyecto residencial", 1.1, False),
    ("hospitality project", 1.2, False),
    ("proyecto de hospitalidad", 1.2, False),
    ("design project", 1.0, False),
    ("proyecto de diseño", 1.0, False),
    ("interior architecture", 1.0, False),
    ("arquitectura de interiores", 1.0, False),
    # ── FF&E and institutional procurement signals ─────────────────────────────
    # These indicate the lead is actively purchasing for a project
    ("ff&e", 1.5, True),               # Furniture, Fixtures & Equipment
    ("furniture fixtures", 1.4, True),
    ("we specify", 1.4, False),        # Designers/architects specify products
    ("i specify", 1.4, False),
    ("specifying", 1.2, False),
    ("seeking suppliers", 1.5, True),
    ("buscando proveedores", 1.5, True),
    ("buscando proveedor", 1.5, True),
    ("looking for suppliers", 1.4, True),
    ("sourcing for", 1.4, True),
    ("licitación", 1.3, True),         # Formal procurement tender (ES)
    ("licitacion", 1.3, True),
    ("concurso de diseño", 1.3, True), # Design competition/tender
    ("amoblamiento", 1.3, True),       # Furnishing project (ES)
    ("amueblamiento", 1.3, True),
    ("furnishing project", 1.3, True),
    ("open call", 1.2, True),          # Artists/designers open calls
    ("convocatoria abierta", 1.2, True),
]

# Pre-compiled for word-boundary matching (3-tuple: pattern, compiled_re, weight, recency_hint)
_COMPILED = compile_patterns(_PROJECT_PATTERNS)


def extract_project_signals(lead: Lead) -> list[Signal]:
    """
    Extract active/recent project signals from bio and category.

    Signals with recency_hint=True imply imminent opportunity.
    """
    signals: list[Signal] = []

    fields = {
        "bio": (lead.bio or "").lower(),
        "category": (lead.category or "").lower(),
    }

    for field_name, text in fields.items():
        if not text:
            continue
        for pattern, compiled_re, weight, recency_hint in _COMPILED:
            if compiled_re.search(text):
                signals.append(Signal(
                    signal_type=SignalType.PROJECT,
                    value=pattern,
                    source=field_name,
                    weight=weight,
                    recency_hint=recency_hint,
                ))

    seen: dict[str, Signal] = {}
    for s in signals:
        if s.value not in seen or s.weight > seen[s.value].weight:
            seen[s.value] = s
    return list(seen.values())
