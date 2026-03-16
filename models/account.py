"""Account — aggregates leads that belong to the same firm/studio/brand."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_VALID_ACCOUNT_TYPES = frozenset({
    "studio", "brand", "developer", "gallery", "hotel_group",
    "architecture_firm", "design_firm", "real_estate", "unknown",
})


@dataclass
class Account:
    """
    A company, studio, or brand entity inferred from one or more leads.

    Accounts aggregate leads that share the same domain, business name, or
    are co-workers on the same project.  They enable portfolio-level scoring:
    "What is the collective buying power of all architects at Studio X?"
    """

    name: str
    website: str = ""
    city: str = ""
    country: str = ""
    account_type: str = "unknown"         # studio | brand | developer | gallery | …

    # Aggregated scoring
    buying_power_score: float = 0.0       # max of member lead scores
    specifier_score: float = 0.0
    authority_rank: float = 0.0           # avg follower-weighted authority

    # Membership
    lead_ids: list[int] = field(default_factory=list)
    lead_count: int = 0

    # Graph
    network_influence_score: float = 0.0  # computed by network_engine after graph build

    # Metadata
    raw_data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.account_type not in _VALID_ACCOUNT_TYPES:
            raise ValueError(
                f"Invalid account_type {self.account_type!r}. "
                f"Must be one of: {sorted(_VALID_ACCOUNT_TYPES)}"
            )
