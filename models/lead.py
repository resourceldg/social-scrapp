from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

_VALID_LEAD_PROFILES = frozenset({
    "buyer", "specifier", "project_actor", "influencer", "gallery_node", "aspirational"
})


@dataclass(slots=True)
class Lead:
    source_platform: str
    search_term: str
    name: str = ""
    social_handle: str = ""
    profile_url: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    city: str = ""
    country: str = ""
    bio: str = ""
    category: str = ""
    lead_type: str = ""
    interest_signals: List[str] = field(default_factory=list)
    followers: str = ""
    engagement_hint: str = ""
    score: int = 0
    lead_profile: str = "aspirational"  # buyer | specifier | project_actor | influencer | gallery_node | aspirational
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lead_profile not in _VALID_LEAD_PROFILES:
            raise ValueError(
                f"Invalid lead_profile {self.lead_profile!r}. "
                f"Must be one of: {sorted(_VALID_LEAD_PROFILES)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
