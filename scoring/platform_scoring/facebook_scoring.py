"""
Facebook platform-specific scoring.

Signals
-------
- Page / profile category relevance (art, design, gallery, …)
- Business presence indicators
- Contact info in bio
- Commercial call-to-action signals
"""
from __future__ import annotations

from models import Lead

_PAGE_CATEGORIES: list[str] = [
    "art", "arte", "gallery", "galería", "galeria",
    "design", "diseño", "interior",
    "architecture", "arquitectura",
    "luxury", "boutique hotel",
    "collectible", "sculpture", "escultura",
    "atelier", "studio", "estudio",
]

_BUSINESS_SIGNALS: list[str] = [
    "page", "business", "company", "empresa",
    "studio", "estudio", "gallery", "galería",
    "shop", "tienda", "showroom",
]

_CTA_SIGNALS: list[str] = [
    "shop", "tienda", "order", "pedido",
    "contact us", "contáctanos", "contactanos",
    "whatsapp", "dm for info",
]


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Facebook-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    cat_lower = (lead.category or "").lower()
    bio_lower = (lead.bio or "").lower()
    combined = f"{cat_lower} {bio_lower}"

    # Page category relevance (up to 40 pts)
    cat_hits = sum(1 for kw in _PAGE_CATEGORIES if kw in combined)
    if cat_hits:
        pts = min(40, cat_hits * 10)
        score += pts
        reasons.append(f"{cat_hits} page category keyword(s) → +{pts}pts")

    # Business presence (up to 20 pts)
    biz_hits = sum(1 for kw in _BUSINESS_SIGNALS if kw in combined)
    if biz_hits:
        pts = min(20, biz_hits * 7)
        score += pts
        reasons.append("business presence signals detected")

    # Contact info in profile (+15)
    if lead.email or lead.phone:
        score += 15
        reasons.append("contact info in profile")

    # Commercial CTA (+10)
    if any(cta in combined for cta in _CTA_SIGNALS):
        score += 10
        reasons.append("commercial call-to-action detected")

    return min(100.0, score), reasons
