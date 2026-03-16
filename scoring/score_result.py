"""LeadScoreResult — full scoring breakdown for a single lead."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LeadScoreResult:
    """
    Complete scoring output for a lead, including base dimensions,
    business intelligence scores, and opportunity classification.

    Attributes
    ----------
    final_score : int
        Composite base score 0–100 under the chosen ranking mode.
    *_score : float
        Raw dimension scores (0–100) before platform multipliers.
    buying_power_score : float
        Estimated economic capacity / budget authority (0–100).
    specifier_score : float
        Influence over purchasing decisions (0–100).
    project_signal_score : float
        Active project signal strength, recency-weighted (0–100).
    opportunity_score : int
        Final composite opportunity score (0–100), combining all components.
    lead_classification : str
        Type of lead: architect, collector, gallery, hospitality, etc.
    opportunity_classification : str
        Commercial opportunity type: active_project, specifier_network,
        direct_buyer, strategic_partner, or low_signal.
    signal_density : int
        Number of distinct signal types active for this lead (0–5).
    ranking_mode : str
        Name of the RankingMode used.
    reasons : list[str]
        Positive signals that contributed to the score.
    warnings : list[str]
        Data quality issues that may reduce confidence.
    confidence : float
        0.0–1.0 estimate of how reliable the score is, based on data
        completeness (bio, followers, name, lead_type, etc.).
    """

    # ── Base dimension scores ──────────────────────────────────────────────────
    final_score: int
    contactability_score: float
    relevance_score: float
    authority_score: float
    commercial_intent_score: float
    premium_fit_score: float
    platform_specific_score: float
    data_quality_score: float
    ranking_mode: str

    # ── Business intelligence scores ──────────────────────────────────────────
    buying_power_score: float = 0.0
    specifier_score: float = 0.0
    project_signal_score: float = 0.0
    opportunity_score: int = 0

    # ── Classifications ────────────────────────────────────────────────────────
    lead_classification: str = "unknown"
    opportunity_classification: str = "low_signal"

    # ── Signal metadata ────────────────────────────────────────────────────────
    signal_density: int = 0

    # ── Authenticity guard ─────────────────────────────────────────────────────
    spam_risk: float = 0.0
    """0–100. High values indicate a likely spam/inauthentic account. Scores
    above 60 should be treated with caution; above 80 are probably noise."""

    # ── Explanability ──────────────────────────────────────────────────────────
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def as_int(self) -> int:
        """Backward-compatible helper returning just the final score."""
        return self.final_score
