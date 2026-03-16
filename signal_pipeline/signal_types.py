"""Core data types for the Signal Intelligence Pipeline.

A Signal is a single detected piece of evidence about a lead.
A SignalSet aggregates all signals extracted from a lead across all categories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SignalType(str, Enum):
    ROLE = "role"
    INDUSTRY = "industry"
    LUXURY = "luxury"
    PROJECT = "project"
    MARKET = "market"


@dataclass(frozen=True)
class Signal:
    signal_type: SignalType
    value: str          # The matched term as found in the source text
    source: str         # Field where detected: "bio", "category", "lead_type", etc.
    weight: float = 1.0  # Relative strength of this signal (0.5–2.0)
    recency_hint: bool = False  # True if signal implies active/recent activity


@dataclass
class SignalSet:
    """
    Complete set of signals extracted from a single Lead.

    This is the primary input to all business scoring modules.
    Signal density and cross-category coherence both increase confidence.
    """

    role_signals: list[Signal] = field(default_factory=list)
    industry_signals: list[Signal] = field(default_factory=list)
    luxury_signals: list[Signal] = field(default_factory=list)
    project_signals: list[Signal] = field(default_factory=list)
    market_signals: list[Signal] = field(default_factory=list)

    @property
    def all_signals(self) -> list[Signal]:
        return (
            self.role_signals
            + self.industry_signals
            + self.luxury_signals
            + self.project_signals
            + self.market_signals
        )

    @property
    def density(self) -> int:
        """Total number of distinct signals detected."""
        return len(self.all_signals)

    @property
    def weighted_density(self) -> float:
        """Sum of signal weights — reflects coherence and signal strength."""
        return sum(s.weight for s in self.all_signals)

    @property
    def active_types(self) -> int:
        """Number of signal categories with at least one signal."""
        return sum([
            bool(self.role_signals),
            bool(self.industry_signals),
            bool(self.luxury_signals),
            bool(self.project_signals),
            bool(self.market_signals),
        ])

    @property
    def has_project_signals(self) -> bool:
        return bool(self.project_signals)

    @property
    def recency_score(self) -> float:
        """
        0.0–1.0 — fraction of project signals that imply recent/active work.
        Returns 0.0 if no project signals exist.
        """
        if not self.project_signals:
            return 0.0
        recent = sum(1 for s in self.project_signals if s.recency_hint)
        return recent / len(self.project_signals)

    def by_type(self, signal_type: SignalType) -> list[Signal]:
        return [s for s in self.all_signals if s.signal_type == signal_type]
