"""Event — a known or inferred industry event detected from lead signals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_VALID_EVENT_TYPES = frozenset({
    "design_week", "art_fair", "gallery_opening", "exhibition",
    "launch_event", "conference", "trade_show", "award_ceremony", "unknown",
})
_VALID_PRESTIGE_TIERS = frozenset({"A", "B", "C", "unknown"})


@dataclass
class Event:
    """
    An industry event detected from lead bios, posts, or captions.

    Events are network nodes — they connect actors who participate in them
    and project opportunities that emerge around them.

    Prestige tiers:
        A — global flagship (Art Basel, Salone del Mobile, Frieze)
        B — regional flagship (Design Week, Casa Cor, ARCO)
        C — local / emerging (gallery openings, pop-ups, local fairs)
    """

    name: str
    event_type: str = "unknown"             # design_week | art_fair | gallery_opening | …
    prestige_tier: str = "unknown"          # A | B | C

    # Geography
    location_city: str = ""
    location_country: str = ""
    lat: float = 0.0
    lon: float = 0.0

    # Timing
    event_date: str = ""                    # ISO date string or year string
    event_year: int = 0

    # Participation
    participant_lead_ids: list[int] = field(default_factory=list)
    participant_count: int = 0

    # Signal provenance (which lead bios mentioned this event)
    detected_from_lead_ids: list[int] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)

    # Scoring
    event_signal_score: float = 0.0        # avg EventSignalScore of participants

    # Metadata
    raw_data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.event_type not in _VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event_type {self.event_type!r}. Must be one of: {sorted(_VALID_EVENT_TYPES)}")
        if self.prestige_tier not in _VALID_PRESTIGE_TIERS:
            raise ValueError(f"Invalid prestige_tier {self.prestige_tier!r}. Must be one of: {sorted(_VALID_PRESTIGE_TIERS)}")
