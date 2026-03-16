"""
GraphBuilder — constructs a typed NetworkX DiGraph from leads, projects,
events, accounts and relationships.

Node schema
-----------
Every node has:
  id        — unique node ID (string: "lead:42", "project:7", etc.)
  type      — lead | account | project | event
  label     — human-readable name
  + type-specific attributes

Edge schema
-----------
Every edge has:
  relation_type  — COLLABORATES_WITH | DESIGNED_BY | WORKS_ON | etc.
  confidence     — 0.0–1.0
  platform       — source platform if known
  evidence       — bio excerpt

Usage
-----
    from network_engine.graph_builder import build_graph, NetworkGraph

    graph = build_graph(leads, mention_results)
    nx.write_gexf(graph.G, "graph.gexf")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

from models import Lead
from network_engine.mention_parser import MentionResult

logger = logging.getLogger(__name__)


def _lead_node_id(handle: str, platform: str = "") -> str:
    return f"lead:{handle.lower()}:{platform.lower()}" if platform else f"lead:{handle.lower()}"


def _project_node_id(project_id: int) -> str:
    return f"project:{project_id}"


def _event_node_id(event_name: str) -> str:
    return f"event:{event_name.lower().replace(' ', '_')}"


def _account_node_id(account_id: int) -> str:
    return f"account:{account_id}"


@dataclass
class NetworkGraph:
    """
    Wrapper around a NetworkX DiGraph with typed helper methods.

    Attributes
    ----------
    G : nx.DiGraph
        The underlying graph. None if networkx is not installed.
    node_count : int
    edge_count : int
    """
    G: object     # nx.DiGraph or None
    node_count: int = 0
    edge_count: int = 0

    def is_empty(self) -> bool:
        return self.node_count == 0

    def export_gexf(self, path: str) -> None:
        """Write the graph to a GEXF file (Gephi-compatible)."""
        if not _NX_AVAILABLE or self.G is None:
            logger.warning("networkx not available — cannot export GEXF")
            return
        nx.write_gexf(self.G, path)
        logger.info("Graph exported to %s (%d nodes, %d edges)", path, self.node_count, self.edge_count)

    def export_graphml(self, path: str) -> None:
        if not _NX_AVAILABLE or self.G is None:
            return
        nx.write_graphml(self.G, path)

    def to_json(self) -> dict:
        """Serialize graph to a JSON-serializable dict (node-link format)."""
        if not _NX_AVAILABLE or self.G is None:
            return {"nodes": [], "links": []}
        import networkx as nx
        return nx.node_link_data(self.G)


def build_graph(
    leads: list[Lead],
    mention_results: list[MentionResult] | None = None,
    lead_db_ids: dict[str, int] | None = None,
) -> NetworkGraph:
    """
    Build a NetworkX DiGraph from leads and mention relationships.

    Parameters
    ----------
    leads : list[Lead]
        All leads to add as nodes.
    mention_results : list[MentionResult], optional
        Output from mention_parser.parse_mentions() for all leads.
    lead_db_ids : dict[str, int], optional
        Mapping social_handle → DB id (for cross-referencing with DB).

    Returns
    -------
    NetworkGraph
        Contains the built graph. Falls back to an empty NetworkGraph
        if networkx is not installed.
    """
    if not _NX_AVAILABLE:
        logger.warning("networkx not installed — graph build skipped. Run: pip install networkx")
        return NetworkGraph(G=None, node_count=0, edge_count=0)

    G = nx.DiGraph()
    db_ids = lead_db_ids or {}

    # ── Add lead nodes ─────────────────────────────────────────────────────────
    handle_to_node_id: dict[str, str] = {}

    for lead in leads:
        handle = (lead.social_handle or lead.name or "").lower()
        if not handle:
            continue
        node_id = _lead_node_id(handle, lead.source_platform)
        handle_to_node_id[handle] = node_id

        raw = lead.raw_data if isinstance(lead.raw_data, dict) else {}
        G.add_node(
            node_id,
            type="lead",
            label=lead.name or lead.social_handle or handle,
            handle=handle,
            platform=lead.source_platform or "",
            lead_type=lead.lead_type or "",
            lead_profile=lead.lead_profile or "",
            city=lead.city or "",
            country=lead.country or "",
            score=lead.score,
            followers=str(lead.followers or ""),
            bio=(lead.bio or "")[:140],
            profile_url=raw.get("profile_url", ""),
            db_id=db_ids.get(handle, 0),
            # BI scores (populated after scoring, overwritten below)
            specifier_score=raw.get("specifier_score", 0.0),
            buying_power_score=raw.get("buying_power_score", 0.0),
            project_signal_score=raw.get("project_signal_score", 0.0),
            event_signal_score=raw.get("event_signal_score", 0.0),
            opportunity_score=raw.get("opportunity_score", 0),
            opportunity_classification=raw.get("opportunity_classification", ""),
        )

    # ── Add relationship edges from mention_results ────────────────────────────
    if mention_results:
        for mention in mention_results:
            source_handle = mention.source_handle.lower()
            target_handle = mention.target_handle.lower()

            source_id = handle_to_node_id.get(source_handle)
            if not source_id:
                continue  # source lead not in our DB

            # Target may not be in our DB — add as unknown node
            target_id = handle_to_node_id.get(target_handle)
            if not target_id:
                target_id = _lead_node_id(target_handle)
                if target_id not in G.nodes:
                    G.add_node(
                        target_id,
                        type="lead",
                        label=f"@{target_handle}",
                        handle=target_handle,
                        platform=mention.source_platform,
                        lead_type="unknown",
                        lead_profile="aspirational",
                        city="", country="",
                        score=0, db_id=0,
                        specifier_score=0.0, buying_power_score=0.0,
                        event_signal_score=0.0, opportunity_score=0,
                        opportunity_classification="",
                    )
                handle_to_node_id[target_handle] = target_id

            # Avoid self-loops
            if source_id == target_id:
                continue

            # If edge already exists, keep the one with higher confidence
            if G.has_edge(source_id, target_id):
                existing_conf = G[source_id][target_id].get("confidence", 0)
                if mention.confidence <= existing_conf:
                    continue

            G.add_edge(
                source_id,
                target_id,
                relation_type=mention.relation_type,
                confidence=mention.confidence,
                platform=mention.source_platform,
                evidence=mention.evidence_text[:200],
            )

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()
    logger.info(
        "Graph built: %d nodes, %d edges",
        node_count, edge_count,
    )
    return NetworkGraph(G=G, node_count=node_count, edge_count=edge_count)
