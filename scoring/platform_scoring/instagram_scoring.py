"""
Instagram platform-specific scoring.

Signals
-------
- Follower tier using INSTAGRAM_FOLLOWER_BUCKETS (calibrated for Instagram scale)
- Niche bio keywords (interior, luxury, design, art, etc.)
- Hashtag niche signals in bio
- Engagement data presence
"""
from __future__ import annotations

from models import Lead
from scoring.thresholds import INSTAGRAM_FOLLOWER_BUCKETS, follower_score

_NICHE_KEYWORDS: list[str] = [
    "interior", "interiorismo", "architecture", "arquitectura",
    "design", "diseño", "collector", "coleccionista",
    "galería", "gallery", "curator", "curador",
    "luxury", "premium", "bespoke", "collectible",
    "art", "arte", "sculpture", "escultura",
    "hospitality", "boutique hotel", "atelier",
]

_HASHTAG_NICHE: list[str] = [
    "#interiordesign", "#architecture", "#luxuryinteriors",
    "#collectibledesign", "#contemporaryart", "#artcollector",
    "#luxuryfurniture", "#bespoke", "#designstudio", "#interiordesigner",
    "#artgallery", "#sculpture", "#handcrafted",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Instagram-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    # Follower tier (up to 25 pts)
    follower_pts = follower_score(lead.followers, INSTAGRAM_FOLLOWER_BUCKETS)
    if follower_pts:
        score += follower_pts
        reasons.append(f"instagram follower tier → +{follower_pts}pts")

    bio_lower = (lead.bio or "").lower()

    # Niche bio keywords (up to 30 pts)
    hits = sum(1 for kw in _NICHE_KEYWORDS if kw in bio_lower)
    if hits:
        kw_pts = min(30, hits * 5)
        score += kw_pts
        reasons.append(f"{hits} niche bio keyword(s) → +{kw_pts}pts")

    # Hashtag niche signals (up to 15 pts)
    hashtag_hits = sum(1 for h in _HASHTAG_NICHE if h in bio_lower)
    if hashtag_hits:
        ht_pts = min(15, hashtag_hits * 5)
        score += ht_pts
        reasons.append(f"{hashtag_hits} niche hashtag(s) in bio → +{ht_pts}pts")

    # Engagement data present (+10)
    if lead.engagement_hint:
        score += 10
        reasons.append("engagement data present")

    # Posts count mentioned in engagement_hint (+5)
    eh_lower = (lead.engagement_hint or "").lower()
    if any(w in eh_lower for w in ("posts", "publicaciones")):
        score += 5

    return min(100.0, score), reasons
