"""
Opportunity Engine.

Computes the final OpportunityScore and classifies commercial opportunities.

Usage
-----
    from opportunity_engine import compute_opportunity_score, classify_opportunity, classify_lead
    from scoring.weights_config import RankingMode

    opp_score, reasons = compute_opportunity_score(
        base_lead_score=72,
        buying_power_score=65,
        specifier_score=80,
        project_signal_score=40,
        mode=RankingMode.SPECIFIER_NETWORK,
    )
    opp_type = classify_opportunity("architect", 65, 80, 40, opp_score)
"""
from opportunity_engine.opportunity_classifier import classify_lead, classify_opportunity
from opportunity_engine.opportunity_scorer import (
    OpportunityWeights,
    compute_opportunity_score,
)

__all__ = [
    "compute_opportunity_score",
    "OpportunityWeights",
    "classify_lead",
    "classify_opportunity",
]
