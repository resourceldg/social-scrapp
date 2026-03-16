"""
Network Intelligence Engine.

Builds a typed relationship graph from leads, projects, events and accounts.
Computes graph metrics (PageRank, centrality) to derive NetworkInfluenceScore
and ActorCentralityScore for each lead.

Pipeline
--------
1. mention_parser      — extract @mentions + collaboration signals from bio text
2. relationship_inferrer — assign confidence to each raw relationship
3. graph_builder       — construct NetworkX DiGraph from all entities + relationships
4. graph_metrics       — compute per-node metrics → NetworkInfluenceScore

Public API
----------
from network_engine import parse_mentions, build_graph, compute_graph_metrics
from network_engine import NetworkGraph, ActorMetrics
"""
from network_engine.mention_parser import MentionResult, parse_mentions
from network_engine.graph_builder import NetworkGraph, build_graph
from network_engine.graph_metrics import ActorMetrics, compute_graph_metrics

__all__ = [
    "MentionResult", "parse_mentions",
    "NetworkGraph", "build_graph",
    "ActorMetrics", "compute_graph_metrics",
]
