"""
SignalExtractor — main orchestrator for signal extraction.

Runs all category extractors against a single Lead and returns
a complete SignalSet ready for normalization and scoring.

Usage
-----
    extractor = SignalExtractor()
    signals = extractor.extract(lead)
    print(signals.density, signals.active_types)
"""
from __future__ import annotations

from models import Lead
from signal_pipeline.extractors.industry_extractor import extract_industry_signals
from signal_pipeline.extractors.luxury_extractor import extract_luxury_signals
from signal_pipeline.extractors.market_extractor import extract_market_signals
from signal_pipeline.extractors.project_extractor import extract_project_signals
from signal_pipeline.extractors.role_extractor import extract_role_signals
from signal_pipeline.signal_types import SignalSet


class SignalExtractor:
    """
    Extracts and aggregates all signals from a Lead into a SignalSet.

    Each extractor is stateless and runs independently, making the pipeline
    easy to extend with new signal categories.
    """

    def extract(self, lead: Lead) -> SignalSet:
        """
        Run all extractors and return a unified SignalSet.

        Parameters
        ----------
        lead : Lead
            The lead to analyse.

        Returns
        -------
        SignalSet
            All detected signals grouped by type.
        """
        return SignalSet(
            role_signals=extract_role_signals(lead),
            industry_signals=extract_industry_signals(lead),
            luxury_signals=extract_luxury_signals(lead),
            project_signals=extract_project_signals(lead),
            market_signals=extract_market_signals(lead),
        )
