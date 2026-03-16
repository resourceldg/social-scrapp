"""
LinkedIn platform-specific scoring.

Signals
-------
- Seniority tier (CEO/Founder > Director > Manager …)
- Job title relevance to our niche (interior, architecture, curator …)
- Company affiliation detected in bio
- Confirmed LinkedIn profile URL
"""
from __future__ import annotations

from models import Lead
from scoring.thresholds import LINKEDIN_SENIORITY

_TITLE_RELEVANCE: list[str] = [
    "interior", "architect", "arquitecto", "arquitecta",
    "curator", "curador", "curadora",
    "design", "designer", "diseñador",
    "gallery", "galería", "galeria",
    "art director", "art advisor", "art consultant",
    "collector", "coleccionista",
    "hospitality", "hotel",
    "real estate", "desarrollador",
    "luxury", "collectible",
    "sculptor", "escultor",
]

_COMPANY_SIGNALS: list[str] = [
    " at ", " en ", "@", "studio", "estudio", "firm",
    "gallery", "galería", "atelier", "taller",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score LinkedIn-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    bio_lower = (lead.bio or "").lower()
    name_lower = (lead.name or "").lower()
    combined = f"{bio_lower} {name_lower}"

    # Seniority tier — highest matching tier only (up to 22 pts)
    for keywords, pts in LINKEDIN_SENIORITY:
        if any(kw in combined for kw in keywords):
            score += pts
            reasons.append(f"seniority tier: {keywords[0]} → +{pts}pts")
            break

    # Job title / niche relevance (up to 25 pts)
    title_hits = sum(1 for kw in _TITLE_RELEVANCE if kw in bio_lower)
    if title_hits:
        title_pts = min(25, title_hits * 8)
        score += title_pts
        reasons.append(f"{title_hits} relevant title keyword(s) → +{title_pts}pts")

    # Company affiliation in bio (+10)
    if any(s in bio_lower for s in _COMPANY_SIGNALS):
        score += 10
        reasons.append("company affiliation detected")

    # Confirmed LinkedIn URL (+5 sanity bonus)
    if "linkedin.com" in (lead.profile_url or "").lower():
        score += 5

    return min(100.0, score), reasons
