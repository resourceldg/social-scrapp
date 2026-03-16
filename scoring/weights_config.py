"""Ranking modes, dimension weights, and per-platform multipliers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RankingMode(str, Enum):
    """Pre-defined weighting strategies for different use cases."""

    OUTREACH_PRIORITY = "outreach_priority"
    AUTHORITY_FIRST = "authority_first"
    PREMIUM_FIT_FIRST = "premium_fit_first"
    CONTACTABILITY_FIRST = "contactability_first"
    BRAND_RELEVANCE = "brand_relevance"
    # Signal intelligence modes
    SPECIFIER_NETWORK = "specifier_network"         # Architects / designers / curators
    HOT_PROJECT_DETECTION = "hot_project_detection"  # Imminent project opportunities


@dataclass(frozen=True)
class DimensionWeights:
    """Weights applied to each scoring dimension. Must sum to 1.0."""

    contactability: float
    relevance: float
    authority: float
    commercial_intent: float
    premium_fit: float
    platform_specific: float
    data_quality: float

    def __post_init__(self) -> None:
        total = (
            self.contactability
            + self.relevance
            + self.authority
            + self.commercial_intent
            + self.premium_fit
            + self.platform_specific
            + self.data_quality
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"DimensionWeights must sum to 1.0, got {total:.4f}")


# ── Ranking mode weight tables ─────────────────────────────────────────────────

RANKING_WEIGHTS: dict[RankingMode, DimensionWeights] = {
    # Best for cold outreach: prioritise reachability + relevance + intent
    RankingMode.OUTREACH_PRIORITY: DimensionWeights(
        contactability=0.22,
        relevance=0.20,
        authority=0.14,
        commercial_intent=0.18,
        premium_fit=0.12,
        platform_specific=0.10,
        data_quality=0.04,
    ),
    # Best for influencer / brand collaboration: reach matters most
    RankingMode.AUTHORITY_FIRST: DimensionWeights(
        contactability=0.06,
        relevance=0.20,
        authority=0.30,
        commercial_intent=0.10,
        premium_fit=0.12,
        platform_specific=0.18,
        data_quality=0.04,
    ),
    # Best for qualifying high-end buyers / collectors
    RankingMode.PREMIUM_FIT_FIRST: DimensionWeights(
        contactability=0.06,
        relevance=0.22,
        authority=0.14,
        commercial_intent=0.16,
        premium_fit=0.30,
        platform_specific=0.10,
        data_quality=0.02,
    ),
    # Best for warm leads that are easy to reach today
    RankingMode.CONTACTABILITY_FIRST: DimensionWeights(
        contactability=0.35,
        relevance=0.18,
        authority=0.12,
        commercial_intent=0.14,
        premium_fit=0.10,
        platform_specific=0.07,
        data_quality=0.04,
    ),
    # Best for building brand awareness in the right circles
    RankingMode.BRAND_RELEVANCE: DimensionWeights(
        contactability=0.06,
        relevance=0.32,
        authority=0.16,
        commercial_intent=0.10,
        premium_fit=0.20,
        platform_specific=0.14,
        data_quality=0.02,
    ),
    # Best for targeting architect / designer / curator networks
    # Relevance + authority dominate; contactability is secondary
    RankingMode.SPECIFIER_NETWORK: DimensionWeights(
        contactability=0.10,
        relevance=0.28,
        authority=0.24,
        commercial_intent=0.14,
        premium_fit=0.14,
        platform_specific=0.08,
        data_quality=0.02,
    ),
    # Best for surfacing leads with active project signals
    # Commercial intent + premium fit matter most; followers less important
    RankingMode.HOT_PROJECT_DETECTION: DimensionWeights(
        contactability=0.14,
        relevance=0.22,
        authority=0.10,
        commercial_intent=0.26,
        premium_fit=0.18,
        platform_specific=0.08,
        data_quality=0.02,
    ),
}


# ── Per-platform dimension multipliers ────────────────────────────────────────

@dataclass(frozen=True)
class PlatformMultipliers:
    """
    Scaling factors applied to each dimension score before weighting.

    Values > 1.0 amplify the dimension for this platform.
    Values < 1.0 dampen it (e.g. contactability on Instagram is hard to get).
    """

    contactability: float
    relevance: float
    authority: float
    commercial_intent: float
    premium_fit: float
    platform_specific: float
    data_quality: float


PLATFORM_MULTIPLIERS: dict[str, PlatformMultipliers] = {
    "instagram": PlatformMultipliers(
        contactability=0.8,
        relevance=1.2,
        authority=1.2,
        commercial_intent=1.0,
        premium_fit=1.3,
        platform_specific=1.4,
        data_quality=1.0,
    ),
    "linkedin": PlatformMultipliers(
        contactability=1.2,
        relevance=1.2,
        authority=1.5,
        commercial_intent=1.4,
        premium_fit=1.1,
        platform_specific=1.2,
        data_quality=1.0,
    ),
    "pinterest": PlatformMultipliers(
        contactability=0.7,
        relevance=1.3,
        authority=1.0,
        commercial_intent=0.9,
        premium_fit=1.4,
        platform_specific=1.3,
        data_quality=1.0,
    ),
    "reddit": PlatformMultipliers(
        contactability=0.6,
        relevance=1.3,
        authority=1.1,
        commercial_intent=0.8,
        premium_fit=0.9,
        platform_specific=1.2,
        data_quality=1.1,
    ),
    "twitter": PlatformMultipliers(
        contactability=0.9,
        relevance=1.2,
        authority=1.3,
        commercial_intent=1.0,
        premium_fit=1.0,
        platform_specific=1.2,
        data_quality=1.0,
    ),
    "facebook": PlatformMultipliers(
        contactability=1.3,
        relevance=1.1,
        authority=1.0,
        commercial_intent=1.2,
        premium_fit=1.0,
        platform_specific=1.1,
        data_quality=1.0,
    ),
    # Behance: portfolio platform — relevance + premium fit dominate.
    # Contactability is low (no DMs; contact via website/email in bio).
    # Authority amplified: appreciations count is a validated quality signal.
    # Platform-specific score heavily amplified: appreciation tiers are key.
    "behance": PlatformMultipliers(
        contactability=0.7,
        relevance=1.4,
        authority=1.3,
        commercial_intent=1.1,
        premium_fit=1.5,
        platform_specific=1.5,
        data_quality=1.0,
    ),
}

_NEUTRAL_MULTIPLIERS = PlatformMultipliers(
    contactability=1.0,
    relevance=1.0,
    authority=1.0,
    commercial_intent=1.0,
    premium_fit=1.0,
    platform_specific=1.0,
    data_quality=1.0,
)


def get_platform_multipliers(platform: str) -> PlatformMultipliers:
    """Return multipliers for the given platform, or neutral if unknown."""
    return PLATFORM_MULTIPLIERS.get(platform.lower(), _NEUTRAL_MULTIPLIERS)
