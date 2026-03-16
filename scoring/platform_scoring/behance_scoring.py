"""
Behance platform-specific scoring.

Signals
-------
- Portfolio quality tier (appreciations count — Behance's engagement metric)
- Follower tier using GENERIC_FOLLOWER_BUCKETS
- Niche bio/occupation keywords (interior, architect, gallery, etc.)
- Portfolio project count (data richness proxy)
- Presence of a website/external link (contactability signal)

Behance is the strongest platform for finding specifiers (architects,
interior designers, studios) who use portfolios to showcase real projects.
Portfolio quality (appreciations) is therefore the primary signal, ahead
of followers.
"""
from __future__ import annotations

import re

from models import Lead
from scoring.thresholds import GENERIC_FOLLOWER_BUCKETS, follower_score

# Behance-specific niche keywords that elevate relevance for the
# art/design/collectibles space
_NICHE_KEYWORDS: list[str] = [
    "interior", "interiorismo", "interior design", "diseño de interiores",
    "architecture", "arquitectura", "architect", "arquitecto",
    "gallery", "galería", "galerie",
    "curator", "curador", "curatorial",
    "luxury", "premium", "bespoke", "collectible",
    "art director", "creative director", "director creativo",
    "design studio", "estudio de diseño", "atelier",
    "furniture", "muebles", "hospitality", "boutique hotel",
    "sculpture", "escultura", "fine art",
    "art collection", "coleccionista", "collector",
    "handcrafted", "artesano", "maker",
]

# Occupations that signal a high-value lead for the furniture/art niche
_HIGH_VALUE_OCCUPATIONS: list[str] = [
    "interior designer", "interior architect", "architect",
    "art director", "creative director", "gallery owner",
    "curator", "design director", "furniture designer",
    "interiorista", "arquitecto", "diseñador",
]

# Appreciations tiers: (min_appreciations, points)
_APPRECIATION_BUCKETS: list[tuple[int, int]] = [
    (50_000, 30),
    (10_000, 25),
    (5_000, 20),
    (1_000, 15),
    (500, 10),
    (100, 5),
    (0, 0),
]

_APPR_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*([KkMm]?)\s*(?:appreciations?|apreciaciones?)", re.IGNORECASE)
_SUFFIX_MAP = {"K": 1_000, "M": 1_000_000, "k": 1_000, "m": 1_000_000}


def _parse_appreciations(text: str) -> int:
    """Parse appreciations count from card text (e.g. '3.2K Appreciations')."""
    if not text:
        return 0
    m = _APPR_RE.search(text)
    if not m:
        return 0
    num_str = m.group(1).replace(",", "")
    suffix = m.group(2)
    try:
        num = float(num_str)
    except ValueError:
        return 0
    return int(num * _SUFFIX_MAP.get(suffix, 1))


def score_platform_specific(lead: Lead) -> tuple[float, list[str]]:
    """Score Behance-specific signals (0–100)."""
    score = 0.0
    reasons: list[str] = []

    # ── Appreciations tier (up to 30 pts) ─────────────────────────────────────
    appr_text = ""
    if isinstance(lead.raw_data, dict):
        appr_text = lead.raw_data.get("appreciations", "") or ""
    if not appr_text:
        appr_text = lead.engagement_hint or ""

    appr_count = _parse_appreciations(appr_text)
    for threshold, pts in _APPRECIATION_BUCKETS:
        if appr_count >= threshold:
            if pts:
                score += pts
                reasons.append(f"appreciations tier ({appr_count:,}) → +{pts}pts")
            break

    # ── Follower tier (up to 20 pts, capped lower than on Instagram) ──────────
    follower_pts = min(20, follower_score(lead.followers, GENERIC_FOLLOWER_BUCKETS))
    if follower_pts:
        score += follower_pts
        reasons.append(f"follower tier → +{follower_pts}pts")

    # ── Occupation / bio niche keywords (up to 30 pts) ────────────────────────
    bio_lower = (lead.bio or "").lower()
    category_lower = (lead.category or "").lower()
    combined_text = f"{bio_lower} {category_lower}"

    # High-value occupation (+15 flat bonus)
    occupation = ""
    if isinstance(lead.raw_data, dict):
        occupation = (lead.raw_data.get("occupation", "") or "").lower()

    if occupation and any(occ in occupation for occ in _HIGH_VALUE_OCCUPATIONS):
        score += 15
        reasons.append(f"high-value occupation '{occupation}' → +15pts")
    elif occupation and any(occ in combined_text for occ in _HIGH_VALUE_OCCUPATIONS):
        score += 10
        reasons.append("high-value occupation in bio → +10pts")

    # Niche keyword hits
    hits = sum(1 for kw in _NICHE_KEYWORDS if kw in combined_text)
    if hits:
        kw_pts = min(30, hits * 4)
        score += kw_pts
        reasons.append(f"{hits} niche keyword(s) in profile → +{kw_pts}pts")

    # ── External website present (contactability bonus, +10) ─────────────────
    if lead.website:
        score += 10
        reasons.append("external website present → +10pts")

    return min(100.0, score), reasons
