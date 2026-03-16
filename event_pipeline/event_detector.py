"""
EventDetector — extracts event mentions from lead bios, categories, and interest signals.

For each lead it returns a list of EventDetection objects, one per detected event.
Each detection carries:
  - the matched EventEntry (or a generic Tier-C placeholder)
  - the evidence text that triggered it
  - the participant role inferred from context
  - a recency hint (is the event upcoming/recent vs historical?)

Usage
-----
    from event_pipeline.event_detector import detect_events
    detections = detect_events(lead)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import Lead
from event_pipeline.event_registry import (
    ALL_KNOWN_EVENTS,
    EventEntry,
    _TIER_C_KEYWORDS,
    is_tier_c_keyword,
)


# ── Role-in-event patterns ─────────────────────────────────────────────────────
# These help distinguish exhibitors (highest value) from visitors (low value).

_EXHIBITOR_PATTERNS = re.compile(
    r"\b(exhibiting|exhibitor|showing at|presenting at|booth at|stand at"
    r"|featured at|represented at|gallery at|showing work|presenting work"
    r"|exposing|expone en|expone|exhibe en|participa en|presenta en"
    r"|stand en|estand en)\b",
    re.IGNORECASE,
)

_SPEAKER_PATTERNS = re.compile(
    r"\b(speaker at|speaking at|talk at|lecture at|panelist at|keynote at"
    r"|moderator at|jury|jurado|conferencia|charla en)\b",
    re.IGNORECASE,
)

_VISITOR_PATTERNS = re.compile(
    r"\b(visiting|see you at|going to|attending|will be at|joining|stopping by"
    r"|check out|don't miss|voy a|estaré en|nos vemos en|te veo en)\b",
    re.IGNORECASE,
)

# Recency indicators — suggest the event is upcoming or just happened
_RECENCY_PATTERNS = re.compile(
    r"\b(this week|next week|opening soon|coming soon|see you there|tomorrow"
    r"|tonight|this month|esta semana|próxima semana|mañana|esta noche"
    r"|hoy|today|just opened|recently opened|now open|open through"
    r"|on view|on show|on display)\b",
    re.IGNORECASE,
)

# Year extraction — helps date the event mention
_YEAR_RE = re.compile(r"\b(20[1-9]\d)\b")


@dataclass
class EventDetection:
    """A single event mention detected in a lead's profile data."""

    event_name: str                             # canonical name or raw match
    event_type: str                             # from EventEntry or inferred
    prestige_tier: str                          # A | B | C
    evidence_text: str                          # bio excerpt that triggered this
    participant_role: str                       # exhibitor | speaker | visitor | unknown
    recency_hint: bool                          # True = upcoming/just happened
    year_hint: int = 0                          # extracted year (0 = unknown)
    entry: EventEntry | None = None             # None for Tier-C generics
    location_city: str = ""
    location_country: str = ""
    lat: float = 0.0
    lon: float = 0.0
    confidence: float = 0.5


def _infer_role(text: str) -> str:
    if _EXHIBITOR_PATTERNS.search(text):
        return "exhibitor"
    if _SPEAKER_PATTERNS.search(text):
        return "speaker"
    if _VISITOR_PATTERNS.search(text):
        return "visitor"
    return "unknown"


def _extract_year(text: str) -> int:
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else 0


def _has_recency(text: str) -> bool:
    return bool(_RECENCY_PATTERNS.search(text))


def _build_text_pool(lead: Lead) -> list[str]:
    """Collect all text fields from a lead into a pool for scanning."""
    pool = []
    if lead.bio:
        pool.append(lead.bio)
    if lead.category:
        pool.append(lead.category)
    for sig in (lead.interest_signals or []):
        pool.append(sig)
    if isinstance(lead.raw_data, dict):
        # Some scrapers store captions / post text in raw_data
        for key in ("caption", "captions", "post_text", "description"):
            val = lead.raw_data.get(key)
            if isinstance(val, str):
                pool.append(val)
            elif isinstance(val, list):
                pool.extend(str(v) for v in val)
    return pool


def _detect_known_events(text_pool: list[str]) -> list[EventDetection]:
    """Scan text pool against all known EventRegistry entries."""
    detections: list[EventDetection] = []
    full_text = " ".join(text_pool).lower()

    for entry in ALL_KNOWN_EVENTS:
        # Check canonical name and all aliases
        terms_to_check = [entry.canonical_name] + list(entry.aliases)
        for term in terms_to_check:
            if term in full_text:
                # Find the actual evidence snippet (±80 chars around the match)
                idx = full_text.find(term)
                snippet_start = max(0, idx - 80)
                snippet_end = min(len(full_text), idx + len(term) + 80)
                evidence = full_text[snippet_start:snippet_end].strip()

                detections.append(EventDetection(
                    event_name=entry.canonical_name,
                    event_type=entry.event_type,
                    prestige_tier=entry.prestige_tier,
                    evidence_text=evidence,
                    participant_role=_infer_role(evidence),
                    recency_hint=_has_recency(evidence),
                    year_hint=_extract_year(evidence),
                    entry=entry,
                    location_city=entry.location_city,
                    location_country=entry.location_country,
                    lat=entry.lat,
                    lon=entry.lon,
                    confidence=0.85,  # high — known event matched
                ))
                break  # only add once per entry regardless of alias matches

    return detections


def _detect_tier_c_events(text_pool: list[str], known_names: set[str]) -> list[EventDetection]:
    """Detect generic Tier-C event keywords not already captured by known events."""
    detections: list[EventDetection] = []
    full_text = " ".join(text_pool).lower()

    for kw in _TIER_C_KEYWORDS:
        if kw in full_text and kw not in known_names:
            idx = full_text.find(kw)
            snippet_start = max(0, idx - 60)
            snippet_end = min(len(full_text), idx + len(kw) + 60)
            evidence = full_text[snippet_start:snippet_end].strip()

            # Infer event_type from keyword
            if any(t in kw for t in ("opening", "inauguración", "vernissage", "apertura")):
                ev_type = "gallery_opening"
            elif any(t in kw for t in ("launch", "lanzamiento")):
                ev_type = "launch_event"
            elif any(t in kw for t in ("award", "prize", "premio")):
                ev_type = "award_ceremony"
            else:
                ev_type = "exhibition"

            detections.append(EventDetection(
                event_name=kw,
                event_type=ev_type,
                prestige_tier="C",
                evidence_text=evidence,
                participant_role=_infer_role(evidence),
                recency_hint=_has_recency(evidence),
                year_hint=_extract_year(evidence),
                entry=None,
                confidence=0.55,  # lower — generic keyword, not a named event
            ))

    return detections


def detect_events(lead: Lead) -> list[EventDetection]:
    """
    Detect all event mentions in a lead's profile data.

    Returns a deduplicated list of EventDetection objects sorted by
    prestige (A → B → C) then recency.

    Parameters
    ----------
    lead : Lead
        The lead to scan.

    Returns
    -------
    list[EventDetection]
        Empty list if no events detected.
    """
    text_pool = _build_text_pool(lead)
    if not text_pool:
        return []

    known = _detect_known_events(text_pool)
    known_names = {d.event_name for d in known}
    tier_c = _detect_tier_c_events(text_pool, known_names)

    all_detections = known + tier_c

    # Sort: prestige A first, then B, then C; recency hints bump up within tier
    tier_order = {"A": 0, "B": 1, "C": 2, "unknown": 3}
    all_detections.sort(
        key=lambda d: (tier_order.get(d.prestige_tier, 3), not d.recency_hint)
    )

    return all_detections
