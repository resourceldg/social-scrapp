"""
Signal Normalization Layer.

Converts platform-specific raw signals into a unified, platform-comparable
feature vector (NormalizedSignals). This ensures that a LinkedIn curator
and an Instagram gallery curator score comparably on authority and role.

Platform raw signals → normalized:
  followers / subscribers / karma  →  authority_signal   (0–100)
  job_title / bio_role             →  role_signal        (0–100)
  hashtags / boards / subreddits   →  relevance_signal   (0–100)
  luxury keywords                  →  luxury_signal      (0–100)
  project keywords + recency       →  project_signal     (0–100)
  city / country / bio location    →  market_signal      (0–100)
  cross-type coherence             →  signal_density     (0–100)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from models import Lead
from signal_pipeline.signal_types import SignalSet

logger = logging.getLogger(__name__)


@dataclass
class NormalizedSignals:
    """
    Platform-agnostic normalized feature vector for a single lead.

    All values are normalized to 0–100 and comparable across platforms.
    Use this as the input to business scoring modules.
    """

    authority_signal: float = 0.0    # Follower/karma/subscriber strength
    role_signal: float = 0.0         # Professional role quality
    relevance_signal: float = 0.0    # Topic relevance to niche
    luxury_signal: float = 0.0       # Luxury/premium market indicators
    project_signal: float = 0.0      # Active project indicators
    market_signal: float = 0.0       # Target market presence
    signal_density: float = 0.0      # Overall signal richness (0–100)


def normalize_signals(lead: Lead, signal_set: SignalSet) -> NormalizedSignals:
    """
    Convert a SignalSet + Lead raw data into a normalized feature vector.

    Parameters
    ----------
    lead : Lead
        The lead being scored (provides raw follower data for authority).
    signal_set : SignalSet
        Extracted signals from the signal pipeline.

    Returns
    -------
    NormalizedSignals
        All values 0–100, platform-comparable.
    """
    authority = _normalize_authority(lead, signal_set)
    role = _normalize_role(signal_set)
    relevance = _normalize_relevance(signal_set)
    luxury = _normalize_luxury(signal_set)
    project = _normalize_project(signal_set)
    market = _normalize_market(signal_set)

    # Signal density: reward multi-type coherence
    # More active types × higher average weight = higher density score
    types_active = signal_set.active_types
    if types_active > 0:
        avg_weight = signal_set.weighted_density / signal_set.density if signal_set.density else 0
        density = min(100.0, types_active * avg_weight * 12.0)
    else:
        density = 0.0

    logger.debug(
        "Normalized signals for %s/%s: auth=%.1f role=%.1f rel=%.1f lux=%.1f proj=%.1f mkt=%.1f dens=%.1f",
        lead.source_platform,
        lead.social_handle or lead.name,
        authority, role, relevance, luxury, project, market, density,
    )

    return NormalizedSignals(
        authority_signal=round(authority, 1),
        role_signal=round(role, 1),
        relevance_signal=round(relevance, 1),
        luxury_signal=round(luxury, 1),
        project_signal=round(project, 1),
        market_signal=round(market, 1),
        signal_density=round(density, 1),
    )


def _normalize_authority(lead: Lead, signal_set: SignalSet) -> float:
    """Authority from followers, amplified by role signal quality."""
    base = 0.0
    followers_str = (lead.followers or "").strip()
    if followers_str:
        from scoring.thresholds import GENERIC_FOLLOWER_BUCKETS, follower_score
        base = float(follower_score(followers_str, GENERIC_FOLLOWER_BUCKETS))

    # Role quality bonus: strong roles amplify authority signal up to +20
    role_bonus = min(20.0, len(signal_set.role_signals) * 4.0)
    return min(100.0, base + role_bonus)


def _normalize_role(signal_set: SignalSet) -> float:
    """Role signal strength as 0–100."""
    if not signal_set.role_signals:
        return 0.0
    total_weight = sum(s.weight for s in signal_set.role_signals)
    # 5.0 total weight ≈ 100 pts (e.g., 5 strong role signals)
    return min(100.0, total_weight * 20.0)


def _normalize_relevance(signal_set: SignalSet) -> float:
    """Relevance from industry + luxury signals combined."""
    combined = signal_set.industry_signals + signal_set.luxury_signals
    if not combined:
        return 0.0
    total_weight = sum(s.weight for s in combined)
    return min(100.0, total_weight * 12.0)


def _normalize_luxury(signal_set: SignalSet) -> float:
    """Pure luxury/premium market signal strength."""
    if not signal_set.luxury_signals:
        return 0.0
    total_weight = sum(s.weight for s in signal_set.luxury_signals)
    return min(100.0, total_weight * 18.0)


def _normalize_project(signal_set: SignalSet) -> float:
    """Project signal strength, boosted by recency factor."""
    if not signal_set.project_signals:
        return 0.0
    total_weight = sum(s.weight for s in signal_set.project_signals)
    recency_multiplier = 1.0 + (signal_set.recency_score * 0.5)  # up to 1.5×
    return min(100.0, total_weight * 15.0 * recency_multiplier)


def _normalize_market(signal_set: SignalSet) -> float:
    """Market signal strength — first match weighted most heavily."""
    if not signal_set.market_signals:
        return 0.0
    total_weight = sum(s.weight for s in signal_set.market_signals)
    return min(100.0, total_weight * 20.0)
