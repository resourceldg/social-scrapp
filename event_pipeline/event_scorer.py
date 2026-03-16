"""
EventSignalScore — measures how strongly a lead's event participation signals
commercial opportunity.

Formula
-------
EventSignalScore (0–100) =
    event_presence_score   (0–40)  — has any relevant event mention
  + prestige_bonus         (0–20)  — weighted by tier A/B/C prestige
  + role_score             (0–25)  — exhibitor > speaker > visitor > unknown
  + recency_score          (0–15)  — recent events score higher

Prestige multipliers by tier:
    A → ×1.5   (global flagship: Art Basel, Salone, Frieze)
    B → ×1.0   (regional flagship: Design Week, Casa Cor)
    C → ×0.5   (local: gallery openings, pop-ups)

Role scores:
    exhibitor → 25 pts
    speaker   → 18 pts
    visitor   → 10 pts
    unknown   → 6 pts

Recency:
    Any detection with recency_hint → 15 pts
    No recency hint → 0 pts

Usage
-----
    from event_pipeline.event_scorer import score_event_signal
    from event_pipeline.event_detector import detect_events

    detections = detect_events(lead)
    score, reasons = score_event_signal(lead, detections)
"""
from __future__ import annotations

from models import Lead
from event_pipeline.event_detector import EventDetection


_PRESTIGE_WEIGHT: dict[str, float] = {
    "A": 1.5,
    "B": 1.0,
    "C": 0.5,
    "unknown": 0.3,
}

_ROLE_SCORE: dict[str, float] = {
    "exhibitor": 25.0,
    "speaker": 18.0,
    "visitor": 10.0,
    "unknown": 6.0,
}

_MAX_EVENTS_CONSIDERED = 3   # top N events by prestige for scoring


def score_event_signal(
    lead: Lead,
    detections: list[EventDetection],
) -> tuple[float, list[str]]:
    """
    Compute EventSignalScore (0–100) for a lead given its event detections.

    Parameters
    ----------
    lead : Lead
        The lead being scored (used for platform context).
    detections : list[EventDetection]
        Output from detect_events(lead).

    Returns
    -------
    tuple[float, list[str]]
        (score_0_to_100, reasons)
    """
    if not detections:
        return 0.0, []

    reasons: list[str] = []
    score = 0.0

    # ── Event presence (0–40) ─────────────────────────────────────────────────
    top_events = detections[:_MAX_EVENTS_CONSIDERED]
    n = len(top_events)

    if n >= 1:
        score += 20.0
        reasons.append(f"participates in {n} relevant event(s)")
    if n >= 2:
        score += 10.0
    if n >= 3:
        score += 10.0

    # ── Prestige bonus (0–20) — best prestige tier from top events ────────────
    best_tier = top_events[0].prestige_tier if top_events else "unknown"
    prestige_bonus = {
        "A": 20.0,
        "B": 12.0,
        "C": 5.0,
        "unknown": 2.0,
    }.get(best_tier, 2.0)
    score += prestige_bonus

    if best_tier == "A":
        reasons.append(f"tier-A event: {top_events[0].event_name}")
    elif best_tier == "B":
        reasons.append(f"tier-B event: {top_events[0].event_name}")

    # ── Role score (0–25) — best role across top events ───────────────────────
    best_role = max(
        (d.participant_role for d in top_events),
        key=lambda r: _ROLE_SCORE.get(r, 0),
        default="unknown",
    )
    role_pts = _ROLE_SCORE.get(best_role, 6.0)
    score += role_pts

    if best_role == "exhibitor":
        reasons.append("exhibitor role (highest commercial signal)")
    elif best_role == "speaker":
        reasons.append("speaker/panelist role at industry event")
    elif best_role == "visitor":
        reasons.append("active event attendee")

    # ── Recency bonus (0–15) ──────────────────────────────────────────────────
    if any(d.recency_hint for d in top_events):
        score += 15.0
        reasons.append("event mention is recent or upcoming")

    # ── Platform context — Instagram/Behance amplify event signals ────────────
    platform = (lead.source_platform or "").lower()
    if platform in ("instagram", "behance"):
        score = min(100.0, score * 1.1)

    final = min(100.0, max(0.0, round(score, 1)))
    return final, reasons
