"""
Backward-compatible scoring entry point.

All callers that import `score_lead` continue to work unchanged.
The implementation now:
  1. Detects the lead's business profile (buyer / specifier / project_actor / …)
  2. Applies the RankingMode that corresponds to that profile
  3. Returns the score (0–100, comparable across all profiles)

The detected profile key is stored as `lead.lead_profile` if the attribute
exists on the object (Lead uses slots=True, so this only happens when the
caller explicitly sets it before passing).  To get the full breakdown use:

    from scoring.profile_classifier import detect_profile_from_lead
    from scoring.score_engine import ScoreEngine
    profile = detect_profile_from_lead(lead)
    result  = ScoreEngine(mode=profile.mode).score(lead)
"""
from __future__ import annotations

from models import Lead
from scoring.profile_classifier import detect_profile_from_lead
from scoring.score_engine import ScoreEngine
from scoring.weights_config import RankingMode

# Cache de engines por modo para no reinstanciar en cada llamada
_engines: dict[RankingMode, ScoreEngine] = {}


def _get_engine(mode: RankingMode) -> ScoreEngine:
    if mode not in _engines:
        _engines[mode] = ScoreEngine(mode=mode)
    return _engines[mode]


def score_lead(lead: Lead) -> int:
    """Return the composite score for a lead (0–100).

    Automatically selects the RankingMode that corresponds to the lead's
    detected business profile, so weights reflect what matters for THAT
    type of actor in the luxury art / collectible design ecosystem.

    The score is comparable across all profiles (single unified scale).
    """
    profile = detect_profile_from_lead(lead)
    return _get_engine(profile.mode).score(lead).final_score


def score_lead_with_profile(lead: Lead) -> tuple[int, str]:
    """Return (score, profile_key) for callers that need both.

    Use this when you want to persist the profile alongside the score
    without running the full ScoreEngine twice.
    """
    profile = detect_profile_from_lead(lead)
    score = _get_engine(profile.mode).score(lead).final_score
    return score, profile.key


def score_lead_full(lead: Lead):
    """Return (final_score, profile_key, LeadScoreResult) for callers that need the full BI breakdown."""
    profile = detect_profile_from_lead(lead)
    result = _get_engine(profile.mode).score(lead)
    return result.final_score, profile.key, result
