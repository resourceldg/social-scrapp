from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


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
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
