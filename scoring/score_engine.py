"""
ScoreEngine — the main Signal Intelligence orchestrator.

Pipeline
--------
1.  Signal extraction     — extract role/industry/luxury/project/market signals
2.  Dimension scoring     — compute 7 universal dimension scores (0–100 each)
3.  Platform scoring      — compute platform-specific score (0–100)
4.  Platform multipliers  — scale each dimension by platform factors
5.  Ranking mode weights  — compute weighted sum → base final_score
6.  Business scoring      — BuyingPower, Specifier, ProjectSignal (0–100 each)
7.  Opportunity engine    — OpportunityScore + lead/opportunity classification
8.  Result assembly       — LeadScoreResult with full breakdown

Formula (base score)
--------------------
    adjusted[d] = dimension_score[d] × platform_multiplier[d]
    final = min(100, round(Σ adjusted[d] × weight[d]))

Formula (opportunity score)
---------------------------
    opportunity = base × w_base + buying_power × w_bp
                  + specifier × w_spec + project × w_proj
    (weights depend on RankingMode)
"""
from __future__ import annotations

import importlib
import logging

from event_pipeline import detect_events, score_event_signal
from models import Lead
from opportunity_engine.opportunity_classifier import classify_lead, classify_opportunity
from opportunity_engine.opportunity_scorer import compute_opportunity_score
from scoring.base_scoring import (
    compute_confidence,
    score_authority,
    score_commercial_intent,
    score_contactability,
    score_data_quality,
    score_premium_fit,
    score_relevance,
    score_spam_risk,
)
from scoring.business_scoring import (
    score_buying_power,
    score_project_signal,
    score_specifier,
)
from scoring.score_result import LeadScoreResult
from scoring.weights_config import RANKING_WEIGHTS, RankingMode, get_platform_multipliers
from signal_pipeline.signal_extractor import SignalExtractor

logger = logging.getLogger(__name__)

# Maps platform names to their scorer module paths
_PLATFORM_SCORER_MODULES: dict[str, str] = {
    "instagram": "scoring.platform_scoring.instagram_scoring",
    "linkedin": "scoring.platform_scoring.linkedin_scoring",
    "pinterest": "scoring.platform_scoring.pinterest_scoring",
    "reddit": "scoring.platform_scoring.reddit_scoring",
    "twitter": "scoring.platform_scoring.twitter_scoring",
    "facebook": "scoring.platform_scoring.facebook_scoring",
    "behance": "scoring.platform_scoring.behance_scoring",
}

_signal_extractor = SignalExtractor()


def _get_platform_score(lead: Lead) -> tuple[float, list[str]]:
    """Dispatch to the appropriate platform scorer module."""
    module_path = _PLATFORM_SCORER_MODULES.get(lead.source_platform.lower())
    if not module_path:
        return 0.0, [f"no platform scorer for '{lead.source_platform}'"]
    module = importlib.import_module(module_path)
    return module.score_platform_specific(lead)


class ScoreEngine:
    """
    Multi-layer, platform-aware, signal-intelligent lead scoring engine.

    Parameters
    ----------
    mode : RankingMode
        Determines how dimension weights are combined for both the base score
        and the opportunity score.
        Defaults to OUTREACH_PRIORITY (balanced for cold outreach).

    Examples
    --------
    >>> engine = ScoreEngine(mode=RankingMode.SPECIFIER_NETWORK)
    >>> result = engine.score(lead)
    >>> print(result.opportunity_score, result.opportunity_classification)
    >>> print(result.reasons)
    """

    def __init__(self, mode: RankingMode = RankingMode.OUTREACH_PRIORITY) -> None:
        self.mode = mode
        self._weights = RANKING_WEIGHTS[mode]

    def score(self, lead: Lead) -> LeadScoreResult:
        """
        Compute the full Signal Intelligence scoring breakdown for a single lead.

        Returns
        -------
        LeadScoreResult
            Contains final_score, all dimension scores, business intelligence
            scores, classifications, reasons, warnings, and confidence.
        """
        # ── Step 1: extract signals ────────────────────────────────────────────
        signal_set = _signal_extractor.extract(lead)

        # ── Step 2: compute dimension scores ──────────────────────────────────
        contactability, c_reasons = score_contactability(lead)
        relevance, r_reasons = score_relevance(lead)
        authority, a_reasons = score_authority(lead)
        commercial_intent, ci_reasons = score_commercial_intent(lead)
        premium_fit, pf_reasons = score_premium_fit(lead)
        data_quality, dq_warnings = score_data_quality(lead)
        platform_specific, ps_reasons = _get_platform_score(lead)

        # ── Step 3: apply platform multipliers ────────────────────────────────
        mults = get_platform_multipliers(lead.source_platform)

        adj_contactability = contactability * mults.contactability
        adj_relevance = relevance * mults.relevance
        adj_authority = authority * mults.authority
        adj_commercial_intent = commercial_intent * mults.commercial_intent
        adj_premium_fit = premium_fit * mults.premium_fit
        adj_platform_specific = platform_specific * mults.platform_specific
        adj_data_quality = data_quality * mults.data_quality

        # ── Step 4: apply ranking mode weights (base score) ───────────────────
        w = self._weights
        final = (
            adj_contactability * w.contactability
            + adj_relevance * w.relevance
            + adj_authority * w.authority
            + adj_commercial_intent * w.commercial_intent
            + adj_premium_fit * w.premium_fit
            + adj_platform_specific * w.platform_specific
            + adj_data_quality * w.data_quality
        )
        final_score = min(100, max(0, round(final)))

        # ── Step 5: business intelligence scoring ─────────────────────────────
        buying_power, bp_reasons = score_buying_power(lead, signal_set)
        specifier, sp_reasons = score_specifier(lead, signal_set)
        project_signal, proj_reasons = score_project_signal(lead, signal_set)

        # ── Step 5b: event intelligence scoring ───────────────────────────────
        event_detections = detect_events(lead)
        event_signal, ev_reasons = score_event_signal(lead, event_detections)

        # ── Step 6: opportunity score + classification ─────────────────────────
        opportunity_score, opp_reasons = compute_opportunity_score(
            base_lead_score=float(final_score),
            buying_power_score=buying_power,
            specifier_score=specifier,
            project_signal_score=project_signal,
            event_signal_score=event_signal,
            network_influence_score=0.0,   # populated by network_engine in Phase 4
            mode=self.mode,
        )
        lead_classification = classify_lead(lead, signal_set)
        opportunity_classification = classify_opportunity(
            lead_classification=lead_classification,
            buying_power_score=buying_power,
            specifier_score=specifier,
            project_signal_score=project_signal,
            opportunity_score=float(opportunity_score),
        )

        # ── Step 7: spam risk + assemble result ───────────────────────────────
        spam_risk, spam_flags = score_spam_risk(lead)
        if spam_flags:
            logger.debug(
                "Spam risk %.0f for %s/%s: %s",
                spam_risk,
                lead.source_platform,
                lead.social_handle or lead.name,
                "; ".join(spam_flags),
            )

        all_reasons = (
            c_reasons + r_reasons + a_reasons
            + ci_reasons + pf_reasons + ps_reasons
            + bp_reasons + sp_reasons + proj_reasons
            + ev_reasons + opp_reasons
        )
        confidence = compute_confidence(lead)

        if final_score < 5:
            missing = [
                f for f, v in [
                    ("bio", lead.bio),
                    ("followers", lead.followers),
                    ("email", lead.email),
                    ("lead_type", lead.lead_type),
                ]
                if not v
            ]
            logger.warning(
                "Low score (%d) for %s/%s — missing fields: %s. "
                "Run profile enrichment to populate data before scoring.",
                final_score,
                lead.source_platform,
                lead.social_handle or lead.name,
                ", ".join(missing) or "none",
            )

        logger.debug(
            "Scored %s/%s: base=%d opp=%d [%s] conf=%.2f mode=%s",
            lead.source_platform,
            lead.social_handle or lead.name,
            final_score,
            opportunity_score,
            opportunity_classification,
            confidence,
            self.mode.value,
        )

        return LeadScoreResult(
            final_score=final_score,
            contactability_score=round(contactability, 1),
            relevance_score=round(relevance, 1),
            authority_score=round(authority, 1),
            commercial_intent_score=round(commercial_intent, 1),
            premium_fit_score=round(premium_fit, 1),
            platform_specific_score=round(platform_specific, 1),
            data_quality_score=round(data_quality, 1),
            ranking_mode=self.mode.value,
            buying_power_score=round(buying_power, 1),
            specifier_score=round(specifier, 1),
            project_signal_score=round(project_signal, 1),
            event_signal_score=round(event_signal, 1),
            network_influence_score=0.0,
            opportunity_score=opportunity_score,
            lead_classification=lead_classification,
            opportunity_classification=opportunity_classification,
            signal_density=signal_set.active_types,
            spam_risk=round(spam_risk, 1),
            reasons=all_reasons,
            warnings=dq_warnings,
            confidence=round(confidence, 2),
        )
