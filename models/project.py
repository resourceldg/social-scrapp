"""Project — a commercial construction/design project inferred from lead signals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_VALID_STATUSES = frozenset({"active", "emerging", "completed", "rumour"})
_VALID_PROJECT_TYPES = frozenset({
    "hospitality", "residential", "commercial", "cultural",
    "retail", "mixed_use", "public", "unknown",
})
_VALID_BUDGET_TIERS = frozenset({"micro", "mid", "high", "ultra", "unknown"})


@dataclass
class Project:
    """
    A commercial project inferred from one or more lead signals.

    Projects are first-class entities — the pipeline starts here (projects-first),
    then expands to actors, then scores opportunities.

    Confidence reflects how many independent signals corroborate the project.
    A confidence ≥ 0.7 is considered reliable enough to surface to the user.
    """

    name: str                                   # inferred or extracted name
    project_type: str = "unknown"               # hospitality | residential | …
    status: str = "emerging"                    # active | emerging | completed | rumour

    # Geography
    location_city: str = ""
    location_country: str = ""
    lat: float = 0.0
    lon: float = 0.0

    # Timeline (ISO date strings or empty)
    inferred_start: str = ""
    inferred_end: str = ""

    # Economic
    budget_tier: str = "unknown"                # micro | mid | high | ultra

    # Confidence
    confidence: float = 0.0                     # 0.0–1.0

    # Actors
    source_lead_ids: list[int] = field(default_factory=list)   # leads that triggered this
    account_id: int | None = None               # owning account if known

    # Opportunity
    opportunity_density: float = 0.0            # 0.0–1.0: how many high-value actors

    # AI enrichment
    ai_summary: str = ""
    ai_recommended_approach: str = ""
    ai_key_actors: list[str] = field(default_factory=list)

    # Signal provenance
    signal_sources: list[str] = field(default_factory=list)    # bio excerpts / post IDs

    # Metadata
    raw_data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"Invalid project status {self.status!r}. Must be one of: {sorted(_VALID_STATUSES)}")
        if self.project_type not in _VALID_PROJECT_TYPES:
            raise ValueError(f"Invalid project_type {self.project_type!r}. Must be one of: {sorted(_VALID_PROJECT_TYPES)}")
        if self.budget_tier not in _VALID_BUDGET_TIERS:
            raise ValueError(f"Invalid budget_tier {self.budget_tier!r}. Must be one of: {sorted(_VALID_BUDGET_TIERS)}")
