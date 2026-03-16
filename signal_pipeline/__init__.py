"""Signal Intelligence Pipeline.

Public API for signal extraction and normalization.

Usage
-----
    from signal_pipeline import SignalExtractor, normalize_signals

    extractor = SignalExtractor()
    signal_set = extractor.extract(lead)
    normalized = normalize_signals(lead, signal_set)
"""
from signal_pipeline.signal_extractor import SignalExtractor
from signal_pipeline.signal_normalizer import NormalizedSignals, normalize_signals
from signal_pipeline.signal_types import Signal, SignalSet, SignalType

__all__ = [
    "SignalExtractor",
    "SignalSet",
    "Signal",
    "SignalType",
    "NormalizedSignals",
    "normalize_signals",
]
