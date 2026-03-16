"""
Twitter / X platform-specific scoring.

Signals
-------
- Verified badge detected in bio
- Follower count (generic buckets, dampened)
- Niche authority keywords
"""
from __future__ import annotations

from models import Lead
from scoring.thresholds import GENERIC_FOLLOWER_BUCKETS, follower_score

_NICHE_AUTHORITY: list[str] = [
    "art director", "interior", "design", "architect", "curator",
    "collector", "gallery", "luxury", "hospitality", "atelier",
    "galería", "escultor", "sculptor",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Twitter/X-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    bio_lower = (lead.bio or "").lower()

    # Verified badge (+20)
    if any(w in bio_lower for w in ("✓", "✔", "verified")):
        score += 20
        reasons.append("verified badge detected → +20pts")

    # Follower count — dampened (Twitter followers are inflated)
    follower_pts = follower_score(lead.followers, GENERIC_FOLLOWER_BUCKETS)
    if follower_pts:
        pts = min(50, round(follower_pts * 0.6))
        score += pts
        reasons.append(f"followers → +{pts}pts")

    # Niche authority keywords in bio (up to 20 pts)
    hits = sum(1 for kw in _NICHE_AUTHORITY if kw in bio_lower)
    if hits:
        pts = min(20, hits * 5)
        score += pts
        reasons.append(f"{hits} niche authority keyword(s) → +{pts}pts")

    return min(100.0, score), reasons
