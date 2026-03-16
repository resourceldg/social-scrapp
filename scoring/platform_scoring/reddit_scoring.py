"""
Reddit platform-specific scoring.

Signals
-------
- Subreddit size (subscribers via REDDIT_SUBSCRIBER_BUCKETS) for /r/ profiles
- User karma level for /user/ profiles
- Community relevance keywords (niche of the subreddit / user)
"""
from __future__ import annotations

from models import Lead
from scoring.thresholds import REDDIT_SUBSCRIBER_BUCKETS, follower_score, parse_followers

_COMMUNITY_KEYWORDS: list[str] = [
    "interior design", "architecture", "art", "collector", "gallery",
    "luxury", "design", "furniture", "hospitality", "real estate",
    "contemporary art", "sculpture", "escultura",
    "interiorism", "galería", "decorator",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Reddit-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    is_subreddit = "/r/" in (lead.profile_url or "").lower()

    if is_subreddit:
        # Subreddit subscriber count
        sub_pts = follower_score(lead.followers, REDDIT_SUBSCRIBER_BUCKETS)
        if sub_pts:
            score += sub_pts
            reasons.append(f"subreddit subscriber tier → +{sub_pts}pts")
    else:
        # User karma
        karma = parse_followers(lead.followers)
        if karma >= 10_000:
            score += 20
            reasons.append(f"high karma ({lead.followers}) → +20pts")
        elif karma >= 1_000:
            score += 10
            reasons.append(f"decent karma ({lead.followers}) → +10pts")
        elif karma >= 100:
            score += 5
            reasons.append(f"some karma ({lead.followers}) → +5pts")

    # Community / niche relevance
    text = " ".join([
        lead.bio, lead.category, lead.search_term, lead.name,
    ]).lower()
    comm_hits = sum(1 for kw in _COMMUNITY_KEYWORDS if kw in text)
    if comm_hits:
        pts = min(30, comm_hits * 8)
        score += pts
        reasons.append(f"{comm_hits} community relevance keyword(s) → +{pts}pts")

    return min(100.0, score), reasons
