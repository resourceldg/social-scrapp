"""
ProjectSignalScore — detects active projects with purchase intent.

An active project is a time-bound opportunity: the lead is currently
working on something that may require art objects or design specifications.

Signal recency is the primary differentiator:
  "opening soon"   →  highest urgency (imminent purchase window)
  "under construction" → high urgency (procurement phase)
  "renovation"     →  medium urgency (budget may be allocated)
  "design project" →  lower urgency (generic, no timeline)

Purchase-intent signals compound the project score further.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline.signal_types import SignalSet

# Direct purchase-intent keywords (bio / category text)
# (pattern, weight)
_PURCHASE_INTENT: list[tuple[str, float]] = [
    ("looking for", 1.2),
    ("buscando", 1.2),
    ("buscamos", 1.2),
    ("need pieces", 1.5),
    ("necesitamos piezas", 1.5),
    ("sourcing", 1.3),
    ("open to proposals", 1.3),
    ("accepting proposals", 1.3),
    ("commission", 1.2),
    ("by commission", 1.2),
    ("commissions open", 1.5),
    ("por encargo", 1.3),
    ("encargos abiertos", 1.5),
    ("dm for info", 1.0),
    ("contact for projects", 1.2),
    ("contacto para proyectos", 1.2),
    ("available for projects", 1.2),
    ("disponible para proyectos", 1.2),
    ("inquiries welcome", 1.1),
    ("consultas bienvenidas", 1.1),
]


def score_project_signal(
    lead: Lead,
    signal_set: SignalSet,
) -> tuple[float, list[str]]:
    """
    Score active project signal strength (0–100).

    Parameters
    ----------
    lead : Lead
        The lead being scored.
    signal_set : SignalSet
        Pre-extracted signals for this lead.

    Returns
    -------
    tuple[float, list[str]]
        (score_0_to_100, reasons)
    """
    score = 0.0
    reasons: list[str] = []

    bio_lower = (lead.bio or "").lower()
    cat_lower = (lead.category or "").lower()
    combined = f"{bio_lower} {cat_lower}"

    # ── Extracted project signals (up to 40 pts) ──────────────────────────────
    if signal_set.project_signals:
        total_weight = sum(s.weight for s in signal_set.project_signals)
        pts = min(40.0, total_weight * 10.0)
        score += pts

        recent_count = sum(1 for s in signal_set.project_signals if s.recency_hint)
        if recent_count:
            reasons.append(
                f"{recent_count} active/recent project signal(s) detected → +{round(pts)}pts"
            )
        else:
            reasons.append(
                f"{len(signal_set.project_signals)} project signal(s) detected → +{round(pts)}pts"
            )

        # ── Recency bonus (up to +20 pts) ─────────────────────────────────────
        recency_bonus = round(signal_set.recency_score * 20.0, 1)
        if recency_bonus:
            score += recency_bonus
            reasons.append(f"recency bonus (opening/launching signals) → +{round(recency_bonus)}pts")

    # ── Direct purchase-intent signals (up to 30 pts) ─────────────────────────
    intent_hits = [(kw, w) for kw, w in _PURCHASE_INTENT if kw in combined]
    if intent_hits:
        pts = min(30.0, sum(w for _, w in intent_hits) * 8.0)
        score += pts
        kw_list = ", ".join(kw for kw, _ in intent_hits[:3])
        reasons.append(f"purchase intent signals ({kw_list}) → +{round(pts)}pts")

    # ── Signal density amplifier (up to +10 pts) ──────────────────────────────
    # Multiple coherent signal types increase confidence in the opportunity
    n_types = sum([
        bool(signal_set.project_signals),
        bool(signal_set.role_signals),
        bool(signal_set.industry_signals),
    ])
    if n_types >= 3 and score > 0:
        density_bonus = min(10.0, n_types * 2.5)
        score += density_bonus
        reasons.append(f"signal density bonus ({n_types} active types) → +{round(density_bonus)}pts")

    return min(100.0, score), reasons
