"""
Pinterest platform-specific scoring.

Signals
-------
- Follower count (generic buckets, dampened — Pinterest followers less predictive)
- Design / luxury niche keywords in bio and category
- Board topic signals (inferred from bio/category text)
"""
from __future__ import annotations

from models import Lead
from scoring.thresholds import GENERIC_FOLLOWER_BUCKETS, follower_score

_DESIGN_KEYWORDS: list[str] = [
    "interior design", "interiorismo", "luxury interior", "diseño de interiores",
    "architecture", "arquitectura",
    "collectible", "bespoke",
    "home decor", "design inspiration",
    "luxury home", "luxury furniture",
    "art collector", "fine art",
    "sculpture", "escultura",
    "boutique hotel", "hospitality",
]

_BOARD_SIGNALS: list[str] = [
    "interior", "design", "luxury", "art", "arte",
    "decor", "architecture", "collect", "hotel", "boutique",
    "atelier", "gallery", "galería",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Pinterest-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    # Follower count — dampened (Pinterest follower counts less predictive)
    follower_pts = follower_score(lead.followers, GENERIC_FOLLOWER_BUCKETS)
    if follower_pts:
        pts = min(30, round(follower_pts * 0.4))
        score += pts
        reasons.append(f"followers → +{pts}pts")

    bio_lower = (lead.bio or "").lower()
    cat_lower = (lead.category or "").lower()
    combined = f"{bio_lower} {cat_lower}"

    # Design niche keywords (up to 35 pts)
    design_hits = sum(1 for kw in _DESIGN_KEYWORDS if kw in combined)
    if design_hits:
        pts = min(35, design_hits * 10)
        score += pts
        reasons.append(f"{design_hits} design keyword(s) → +{pts}pts")

    # Board topic signals (up to 20 pts)
    board_hits = sum(1 for s in _BOARD_SIGNALS if s in combined)
    if board_hits:
        pts = min(20, board_hits * 4)
        score += pts
        reasons.append(f"{board_hits} board topic signal(s) → +{pts}pts")

    return min(100.0, score), reasons
