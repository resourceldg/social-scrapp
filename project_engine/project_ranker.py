"""
ProjectRanker — scores ProjectClusters by opportunity density.

OpportunityDensity measures how commercially attractive a cluster is:
    - How many specifiers (architects, designers) are in the cluster?
    - How high is the aggregate buying power?
    - Are there active project signals (not just rumours)?
    - Are actors in the cluster present in the event circuit?
    - How many actors are there (more = stronger signal)?

Formula
-------
OpportunityDensity (0.0–1.0) =
    specifier_component   × 0.30
  + buying_power_component × 0.25
  + status_component       × 0.20
  + event_component        × 0.15
  + actor_density_component × 0.10

Usage
-----
    from project_engine.project_ranker import rank_clusters

    # Enrich clusters with BI scores from leads before calling this.
    ranked = rank_clusters(clusters)
    for cluster in ranked:
        print(f"{cluster.location_city} {cluster.project_type}: "
              f"density={cluster.opportunity_density:.2f}")
"""
from __future__ import annotations

from project_engine.project_clusterer import ProjectCluster

_STATUS_SCORE: dict[str, float] = {
    "active":    1.0,
    "emerging":  0.6,
    "completed": 0.2,
    "rumour":    0.3,
}

_BUDGET_MULTIPLIER: dict[str, float] = {
    "ultra":   1.30,
    "high":    1.15,
    "mid":     1.00,
    "micro":   0.80,
    "unknown": 0.90,
}

# Max actor count before the actor_density component saturates
_ACTOR_DENSITY_CAP = 8


def _normalize(value: float, max_val: float = 100.0) -> float:
    return min(1.0, max(0.0, value / max_val))


def _compute_opportunity_density(cluster: ProjectCluster) -> float:
    # Component 1: specifier quality (0–1)
    specifier = _normalize(cluster.avg_specifier_score)

    # Component 2: buying power (0–1)
    buying = _normalize(cluster.avg_buying_power_score)

    # Component 3: project status urgency (0–1)
    status = _STATUS_SCORE.get(cluster.status, 0.4)

    # Component 4: event circuit presence (0–1)
    event = _normalize(cluster.avg_event_signal_score)

    # Component 5: actor density (0–1), capped at _ACTOR_DENSITY_CAP
    actor_density = min(1.0, cluster.actor_count / _ACTOR_DENSITY_CAP)

    raw = (
        specifier    * 0.30
        + buying     * 0.25
        + status     * 0.20
        + event      * 0.15
        + actor_density * 0.10
    )

    # Budget tier multiplier — luxury projects are more attractive
    multiplier = _BUDGET_MULTIPLIER.get(cluster.budget_tier, 1.0)
    return min(1.0, round(raw * multiplier, 3))


def enrich_cluster_scores(
    cluster: ProjectCluster,
    lead_scores: list[dict],
) -> ProjectCluster:
    """
    Populate BI score aggregates on a cluster from its member lead scores.

    Parameters
    ----------
    cluster : ProjectCluster
    lead_scores : list[dict]
        Each dict must have: specifier_score, buying_power_score,
        event_signal_score, opportunity_score (all floats).
        Pass the raw_data dicts (or LeadScoreResult field dicts) for each actor.

    Returns
    -------
    ProjectCluster
        Same cluster with avg_specifier_score, avg_buying_power_score,
        avg_event_signal_score, max_opportunity_score populated.
    """
    if not lead_scores:
        return cluster

    cluster.avg_specifier_score = round(
        sum(s.get("specifier_score", 0) for s in lead_scores) / len(lead_scores), 1
    )
    cluster.avg_buying_power_score = round(
        sum(s.get("buying_power_score", 0) for s in lead_scores) / len(lead_scores), 1
    )
    cluster.avg_event_signal_score = round(
        sum(s.get("event_signal_score", 0) for s in lead_scores) / len(lead_scores), 1
    )
    cluster.max_opportunity_score = int(
        max((s.get("opportunity_score", 0) for s in lead_scores), default=0)
    )
    return cluster


def rank_clusters(clusters: list[ProjectCluster]) -> list[ProjectCluster]:
    """
    Compute OpportunityDensity for each cluster and return them sorted
    highest-density first.

    Call enrich_cluster_scores() on each cluster before calling this
    if you have BI score data available.

    Parameters
    ----------
    clusters : list[ProjectCluster]

    Returns
    -------
    list[ProjectCluster]
        Same objects mutated in place with opportunity_density set, sorted desc.
    """
    for cluster in clusters:
        cluster.opportunity_density = _compute_opportunity_density(cluster)

    clusters.sort(key=lambda c: (c.opportunity_density, c.confidence), reverse=True)
    return clusters
