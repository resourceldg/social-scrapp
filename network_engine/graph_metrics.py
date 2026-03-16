"""
GraphMetrics — computes per-node network intelligence scores from a NetworkGraph.

Metrics computed
----------------
For each lead node:

  pagerank_score        (0–100)  — relative global importance in the graph
  betweenness_score     (0–100)  — broker: sits between many pairs of nodes
  degree_score          (0–100)  — raw connection count (in + out)
  cross_project_score   (0–100)  — appears connected to multiple project clusters
  network_influence_score (0–100) — composite of the above

Formula
-------
  NetworkInfluenceScore =
    pagerank_score    × 0.40
    + betweenness     × 0.30
    + degree_score    × 0.20
    + cross_project   × 0.10

Usage
-----
    from network_engine.graph_metrics import compute_graph_metrics, ActorMetrics

    metrics = compute_graph_metrics(network_graph)
    for handle, m in metrics.items():
        print(handle, m.network_influence_score)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

from network_engine.graph_builder import NetworkGraph

logger = logging.getLogger(__name__)


@dataclass
class ActorMetrics:
    """Per-node network intelligence metrics."""
    handle: str
    node_id: str
    db_id: int

    pagerank_score: float = 0.0             # 0–100
    betweenness_score: float = 0.0          # 0–100
    degree_score: float = 0.0              # 0–100
    cross_project_score: float = 0.0       # 0–100

    network_influence_score: float = 0.0   # 0–100 composite
    actor_centrality_score: float = 0.0    # 0–100 (degree-only, simpler)


def _normalize_dict(d: dict, scale: float = 100.0) -> dict:
    """Normalize a dict of float values to [0, scale]."""
    if not d:
        return d
    max_val = max(d.values()) or 1.0
    return {k: round((v / max_val) * scale, 2) for k, v in d.items()}


def compute_graph_metrics(network_graph: NetworkGraph) -> dict[str, ActorMetrics]:
    """
    Compute network intelligence metrics for all lead nodes in the graph.

    Parameters
    ----------
    network_graph : NetworkGraph
        Output from build_graph().

    Returns
    -------
    dict[str, ActorMetrics]
        Keyed by node_id. Empty dict if graph is empty or networkx unavailable.
    """
    if not _NX_AVAILABLE:
        logger.warning("networkx not installed — graph metrics skipped")
        return {}

    G = network_graph.G
    if G is None or G.number_of_nodes() == 0:
        return {}

    # ── PageRank ──────────────────────────────────────────────────────────────
    try:
        pr_raw = nx.pagerank(G, alpha=0.85, max_iter=100)
    except Exception as e:
        logger.warning("PageRank failed: %s", e)
        pr_raw = {n: 0.0 for n in G.nodes}
    pr = _normalize_dict(pr_raw)

    # ── Betweenness centrality ─────────────────────────────────────────────────
    # Use approximate for large graphs (k=min(500, n))
    n = G.number_of_nodes()
    try:
        k = min(500, n) if n > 100 else None
        btw_raw = nx.betweenness_centrality(G, k=k, normalized=True)
    except Exception as e:
        logger.warning("Betweenness centrality failed: %s", e)
        btw_raw = {n: 0.0 for n in G.nodes}
    btw = _normalize_dict(btw_raw)

    # ── Degree (in + out) ─────────────────────────────────────────────────────
    degree_raw = {node: G.in_degree(node) + G.out_degree(node) for node in G.nodes}
    degree = _normalize_dict(degree_raw)

    # ── Cross-project score: nodes connected to many distinct communities ──────
    # Approximated as clustering coefficient of the undirected version
    G_undirected = G.to_undirected()
    try:
        clustering_raw = nx.clustering(G_undirected)
    except Exception:
        clustering_raw = {n: 0.0 for n in G.nodes}
    cross_project = {k: round(v * 100, 2) for k, v in clustering_raw.items()}

    # ── Assemble ActorMetrics for lead nodes ──────────────────────────────────
    result: dict[str, ActorMetrics] = {}

    for node_id, attrs in G.nodes(data=True):
        if attrs.get("type") != "lead":
            continue

        handle = attrs.get("handle", node_id)
        db_id = attrs.get("db_id", 0)

        pr_s  = pr.get(node_id, 0.0)
        btw_s = btw.get(node_id, 0.0)
        deg_s = degree.get(node_id, 0.0)
        cp_s  = cross_project.get(node_id, 0.0)

        network_influence = round(
            pr_s  * 0.40
            + btw_s * 0.30
            + deg_s * 0.20
            + cp_s  * 0.10,
            1,
        )
        actor_centrality = round(deg_s, 1)

        metrics = ActorMetrics(
            handle=handle,
            node_id=node_id,
            db_id=db_id,
            pagerank_score=pr_s,
            betweenness_score=btw_s,
            degree_score=deg_s,
            cross_project_score=cp_s,
            network_influence_score=network_influence,
            actor_centrality_score=actor_centrality,
        )
        result[node_id] = metrics

    logger.info(
        "Graph metrics computed for %d lead nodes", len(result)
    )
    return result
