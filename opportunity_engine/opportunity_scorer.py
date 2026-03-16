"""
OpportunityScorer — computes the final OpportunityScore.

Formula (default OUTREACH_PRIORITY):
    OpportunityScore =
        base_lead_score    × w_base
        + buying_power     × w_buying
        + specifier_score  × w_specifier
        + project_signal   × w_project

Each RankingMode shifts these weights to surface different opportunity types.
The two new modes (SPECIFIER_NETWORK, HOT_PROJECT_DETECTION) are defined here
in addition to the existing modes already present in the base engine.
"""
from __future__ import annotations

from dataclasses import dataclass

from scoring.weights_config import RankingMode


@dataclass(frozen=True)
class OpportunityWeights:
    """Weights applied to the six opportunity components. Must sum to 1.0."""

    base_lead: float
    buying_power: float
    specifier: float
    project_signal: float
    event_signal: float = 0.0
    network_influence: float = 0.0

    def __post_init__(self) -> None:
        total = (
            self.base_lead + self.buying_power + self.specifier
            + self.project_signal + self.event_signal + self.network_influence
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"OpportunityWeights must sum to 1.0, got {total:.4f}")


# Weight table — keyed by RankingMode so the engine uses a single mode enum
# event_signal and network_influence are new dimensions; existing weights
# are proportionally reduced to accommodate them while preserving relative ratios.
OPPORTUNITY_WEIGHTS: dict[RankingMode, OpportunityWeights] = {
    # Cold outreach: balanced — events and network add meaningful signal
    RankingMode.OUTREACH_PRIORITY: OpportunityWeights(
        base_lead=0.35, buying_power=0.15, specifier=0.15,
        project_signal=0.15, event_signal=0.10, network_influence=0.10,
    ),
    # Influencer / brand collab: lead quality + network reach dominate
    RankingMode.AUTHORITY_FIRST: OpportunityWeights(
        base_lead=0.40, buying_power=0.15, specifier=0.10,
        project_signal=0.10, event_signal=0.10, network_influence=0.15,
    ),
    # High-end buyer: economic capacity + event circuit presence
    RankingMode.PREMIUM_FIT_FIRST: OpportunityWeights(
        base_lead=0.30, buying_power=0.30, specifier=0.12,
        project_signal=0.12, event_signal=0.10, network_influence=0.06,
    ),
    # Contactability: reachability first; events/network secondary
    RankingMode.CONTACTABILITY_FIRST: OpportunityWeights(
        base_lead=0.38, buying_power=0.18, specifier=0.18,
        project_signal=0.15, event_signal=0.06, network_influence=0.05,
    ),
    # Brand awareness: relevance + event visibility + network
    RankingMode.BRAND_RELEVANCE: OpportunityWeights(
        base_lead=0.33, buying_power=0.12, specifier=0.20,
        project_signal=0.15, event_signal=0.12, network_influence=0.08,
    ),
    # Architect / designer network: specifier + event circuit dominate
    RankingMode.SPECIFIER_NETWORK: OpportunityWeights(
        base_lead=0.22, buying_power=0.12, specifier=0.38,
        project_signal=0.12, event_signal=0.10, network_influence=0.06,
    ),
    # Hot leads: project signal dominates; events confirm urgency
    RankingMode.HOT_PROJECT_DETECTION: OpportunityWeights(
        base_lead=0.22, buying_power=0.12, specifier=0.12,
        project_signal=0.38, event_signal=0.10, network_influence=0.06,
    ),
}


def compute_opportunity_score(
    base_lead_score: float,
    buying_power_score: float,
    specifier_score: float,
    project_signal_score: float,
    mode: RankingMode = RankingMode.OUTREACH_PRIORITY,
    event_signal_score: float = 0.0,
    network_influence_score: float = 0.0,
) -> tuple[int, list[str]]:
    """
    Compute the final opportunity score (0–100) and explanatory reasons.

    Parameters
    ----------
    base_lead_score : float
        Composite score from ScoreEngine (0–100).
    buying_power_score : float
        From score_buying_power() (0–100).
    specifier_score : float
        From score_specifier() (0–100).
    project_signal_score : float
        From score_project_signal() (0–100).
    mode : RankingMode
        Determines weight distribution. Defaults to OUTREACH_PRIORITY.
    event_signal_score : float
        From event_pipeline.score_event_signal() (0–100). Default 0.
    network_influence_score : float
        From network_engine.graph_metrics (0–100). Default 0 until Phase 4.

    Returns
    -------
    tuple[int, list[str]]
        (opportunity_score_0_to_100, reasons)
    """
    w = OPPORTUNITY_WEIGHTS[mode]

    weighted = (
        base_lead_score      * w.base_lead
        + buying_power_score * w.buying_power
        + specifier_score    * w.specifier
        + project_signal_score * w.project_signal
        + event_signal_score * w.event_signal
        + network_influence_score * w.network_influence
    )
    final = min(100, max(0, round(weighted)))

    reasons: list[str] = []
    if base_lead_score >= 60:
        reasons.append(f"strong base lead score ({round(base_lead_score)})")
    if buying_power_score >= 50:
        reasons.append(f"significant buying power ({round(buying_power_score)})")
    if specifier_score >= 50:
        reasons.append(f"high specifier potential ({round(specifier_score)})")
    if project_signal_score >= 50:
        reasons.append(f"active project signals ({round(project_signal_score)})")
    if event_signal_score >= 40:
        reasons.append(f"strong event circuit presence ({round(event_signal_score)})")
    if network_influence_score >= 40:
        reasons.append(f"network hub — high centrality ({round(network_influence_score)})")

    return final, reasons
