"""
Score A/B testing framework.

Runs a batch of leads through multiple RankingMode configurations simultaneously
and compares results to determine which mode best separates high-quality leads
from low-quality ones — and, when conversion feedback is available, which mode
produces the highest precision on converted leads.

Usage
-----
    from scoring.ab_test import ABTestRunner, ABTestReport
    from scoring.weights_config import RankingMode
    from models import Lead

    runner = ABTestRunner(
        variants=[RankingMode.OUTREACH_PRIORITY, RankingMode.SPECIFIER_NETWORK],
    )
    report = runner.run(leads)
    print(report.summary())

    # With conversion feedback
    report = runner.run(leads, converted_urls={"https://instagram.com/studioA"})
    print(report.precision_by_variant)
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from typing import Iterable

from models import Lead
from scoring.score_engine import ScoreEngine
from scoring.score_result import LeadScoreResult
from scoring.weights_config import RankingMode


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class VariantResult:
    """Scoring outcome for a single lead under one RankingMode."""
    mode: str
    profile_url: str
    final_score: int
    opportunity_score: int
    opportunity_classification: str
    lead_classification: str
    confidence: float
    spam_risk: float


@dataclass
class ABTestReport:
    """
    Aggregated comparison of N RankingMode variants over a lead batch.

    Attributes
    ----------
    variants        : RankingMode values tested
    n_leads         : number of leads scored
    avg_score       : mean final_score per variant
    avg_opportunity : mean opportunity_score per variant
    high_opp_count  : number of leads classified as active_project or specifier_network
    avg_confidence  : mean confidence per variant
    precision       : fraction of converted leads in top-quartile per variant
                      (only populated when converted_urls is provided)
    score_std       : score standard deviation per variant (spread/discrimination)
    raw             : per-lead VariantResult lists keyed by mode name
    """
    variants: list[str]
    n_leads: int
    avg_score: dict[str, float] = field(default_factory=dict)
    avg_opportunity: dict[str, float] = field(default_factory=dict)
    high_opp_count: dict[str, int] = field(default_factory=dict)
    avg_confidence: dict[str, float] = field(default_factory=dict)
    precision: dict[str, float] = field(default_factory=dict)
    score_std: dict[str, float] = field(default_factory=dict)
    raw: dict[str, list[VariantResult]] = field(default_factory=dict)

    _HIGH_OPP = frozenset({"active_project", "specifier_network"})

    def summary(self) -> str:
        """Return a human-readable multi-line comparison table."""
        lines = [
            f"A/B Test — {self.n_leads} leads × {len(self.variants)} variants",
            f"{'Mode':<28} {'AvgScore':>9} {'StdDev':>8} {'AvgOpp':>8} {'HighOpp':>8} {'Conf':>7}"
            + (" {'Precision':>10}" if self.precision else ""),
        ]
        lines.append("-" * 70)
        for mode in sorted(self.variants, key=lambda m: self.avg_score.get(m, 0), reverse=True):
            prec = f"  {self.precision[mode]:.0%}" if mode in self.precision else ""
            lines.append(
                f"{mode:<28} "
                f"{self.avg_score.get(mode, 0):9.1f} "
                f"{self.score_std.get(mode, 0):8.1f} "
                f"{self.avg_opportunity.get(mode, 0):8.1f} "
                f"{self.high_opp_count.get(mode, 0):8d} "
                f"{self.avg_confidence.get(mode, 0):7.2f}"
                f"{prec}"
            )
        if self.precision:
            best = max(self.precision, key=self.precision.get)  # type: ignore[arg-type]
            lines.append(f"\nHighest precision on converted leads: {best} ({self.precision[best]:.0%})")
        return "\n".join(lines)

    def recommended_mode(self, converted_urls: set[str] | None = None) -> str:
        """
        Return the mode name that performs best.

        Priority (in order):
        1. Highest precision on converted leads (if feedback available)
        2. Highest avg_opportunity score
        3. Highest avg_score
        """
        if self.precision:
            return max(self.precision, key=self.precision.get)  # type: ignore[arg-type]
        if self.avg_opportunity:
            return max(self.avg_opportunity, key=self.avg_opportunity.get)  # type: ignore[arg-type]
        return max(self.avg_score, key=self.avg_score.get)  # type: ignore[arg-type]


# ── Runner ─────────────────────────────────────────────────────────────────────

class ABTestRunner:
    """
    Score a lead batch under multiple RankingMode variants and compare results.

    Parameters
    ----------
    variants : list of RankingMode values to compare.
               Defaults to all available modes.
    top_pct  : fraction of leads considered "top-ranked" for precision calculation.
               Default 0.25 = top quartile.
    """

    def __init__(
        self,
        variants: list[RankingMode] | None = None,
        top_pct: float = 0.25,
    ) -> None:
        self.variants = variants or list(RankingMode)
        self.top_pct = top_pct
        self._engines: dict[RankingMode, ScoreEngine] = {
            mode: ScoreEngine(mode=mode) for mode in self.variants
        }

    def run(
        self,
        leads: Iterable[Lead],
        converted_urls: set[str] | None = None,
    ) -> ABTestReport:
        """
        Score all leads under each variant and return an ABTestReport.

        Parameters
        ----------
        leads          : iterable of Lead objects to score
        converted_urls : set of profile_url strings known to have converted.
                         When provided, precision-at-top-quartile is computed.
        """
        leads = list(leads)
        report = ABTestReport(variants=[m.value for m in self.variants], n_leads=len(leads))

        for mode in self.variants:
            results = self._score_batch(mode, leads)
            mode_name = mode.value
            report.raw[mode_name] = results

            scores = [r.final_score for r in results]
            opp_scores = [r.opportunity_score for r in results]
            confs = [r.confidence for r in results]

            report.avg_score[mode_name] = round(statistics.mean(scores), 1) if scores else 0.0
            report.score_std[mode_name] = round(statistics.stdev(scores), 1) if len(scores) > 1 else 0.0
            report.avg_opportunity[mode_name] = round(statistics.mean(opp_scores), 1) if opp_scores else 0.0
            report.avg_confidence[mode_name] = round(statistics.mean(confs), 2) if confs else 0.0
            report.high_opp_count[mode_name] = sum(
                1 for r in results if r.opportunity_classification in ABTestReport._HIGH_OPP
            )

            if converted_urls:
                report.precision[mode_name] = self._precision_at_top(
                    results, converted_urls
                )

        return report

    def assign_variant(self, profile_url: str) -> RankingMode:
        """
        Deterministically assign a lead to a variant based on URL hash.

        Useful for live traffic splitting — the same lead always gets the
        same variant, ensuring consistent scoring in production.
        """
        h = int(hashlib.md5(profile_url.encode()).hexdigest(), 16)
        return self.variants[h % len(self.variants)]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _score_batch(self, mode: RankingMode, leads: list[Lead]) -> list[VariantResult]:
        engine = self._engines[mode]
        results: list[VariantResult] = []
        for lead in leads:
            try:
                sr: LeadScoreResult = engine.score(lead)
                results.append(VariantResult(
                    mode=mode.value,
                    profile_url=lead.profile_url,
                    final_score=sr.final_score,
                    opportunity_score=sr.opportunity_score,
                    opportunity_classification=sr.opportunity_classification,
                    lead_classification=sr.lead_classification,
                    confidence=sr.confidence,
                    spam_risk=sr.spam_risk,
                ))
            except Exception:
                pass
        return results

    def _precision_at_top(
        self, results: list[VariantResult], converted_urls: set[str]
    ) -> float:
        """Precision = converted leads in top-k / k, where k = top_pct of all results."""
        if not results or not converted_urls:
            return 0.0
        sorted_r = sorted(results, key=lambda r: r.final_score, reverse=True)
        k = max(1, round(len(sorted_r) * self.top_pct))
        top_k = sorted_r[:k]
        hits = sum(1 for r in top_k if r.profile_url in converted_urls)
        return round(hits / k, 3)
