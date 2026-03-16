"""Relationship — a typed, confidence-weighted edge between any two entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


NodeType = Literal["lead", "account", "project", "event"]

RelationType = Literal[
    "WORKS_ON",            # lead → project
    "DESIGNED_BY",         # project → lead (designer/architect)
    "EXHIBITS_AT",         # lead → event
    "COLLABORATES_WITH",   # lead ↔ lead (bidirectional)
    "MENTIONED_WITH",      # lead ↔ lead (co-mentioned in same post/caption)
    "LOCATED_IN",          # lead | project | event → location
    "PARTICIPATES_IN",     # lead → event
    "MEMBER_OF",           # lead → account
    "COMMISSIONED_BY",     # project → account (developer / hotel group)
    "FEATURES",            # event → lead (event features this actor)
]

_VALID_NODE_TYPES: frozenset[str] = frozenset({"lead", "account", "project", "event"})
_VALID_RELATION_TYPES: frozenset[str] = frozenset({
    "WORKS_ON", "DESIGNED_BY", "EXHIBITS_AT", "COLLABORATES_WITH",
    "MENTIONED_WITH", "LOCATED_IN", "PARTICIPATES_IN", "MEMBER_OF",
    "COMMISSIONED_BY", "FEATURES",
})


@dataclass
class Relationship:
    """
    A typed, confidence-weighted directed edge between two entities in the
    commercial intelligence graph.

    confidence reflects how strongly the signal evidence supports this
    relationship (0.0 = speculation, 1.0 = directly stated).

    Cross-platform corroboration amplifies confidence: if the same relationship
    is detected on Instagram AND LinkedIn, confidence is boosted.
    """

    source_id: int                      # DB id of source entity
    source_type: NodeType               # lead | account | project | event
    target_id: int                      # DB id of target entity
    target_type: NodeType               # lead | account | project | event
    relation_type: RelationType

    confidence: float = 0.5            # 0.0–1.0

    source_platform: str = ""          # where detected (instagram, linkedin, …)
    evidence_text: str = ""            # bio excerpt or post caption that triggered this
    detected_at: str = ""

    # Cross-platform corroboration
    corroborating_platforms: list[str] = field(default_factory=list)

    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_type not in _VALID_NODE_TYPES:
            raise ValueError(f"Invalid source_type {self.source_type!r}")
        if self.target_type not in _VALID_NODE_TYPES:
            raise ValueError(f"Invalid target_type {self.target_type!r}")
        if self.relation_type not in _VALID_RELATION_TYPES:
            raise ValueError(f"Invalid relation_type {self.relation_type!r}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")
