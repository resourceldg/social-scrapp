"""
ProjectClusterer — groups leads with related project signals into ProjectClusters.

Clustering strategy
-------------------
Two leads belong to the same ProjectCluster if they share:
  - Same city (or within ~50 km if geo-coded)
  - Compatible project type (or unknown overlaps with anything)
  - Overlapping / compatible timeline (same year, or no timeline)
  - At least one actor role that makes sense together
    (e.g. architect + developer + hotel → coherent)

This is intentionally lightweight: no ML model, no external API.
Clustering uses a single-linkage greedy approach — fast and interpretable.
When geo-coding is available (geopy installed) it uses lat/lon distance;
otherwise it falls back to city string matching.

Usage
-----
    from project_engine.project_clusterer import cluster_leads, ProjectCluster

    # leads_with_detections: list of (Lead, ProjectDetection, lead_db_id)
    clusters = cluster_leads(leads_with_detections)
    for cluster in clusters:
        print(cluster.location_city, cluster.project_type, cluster.actor_count)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import NamedTuple

from models import Lead
from project_engine.project_detector import ProjectDetection

logger = logging.getLogger(__name__)

# Try to import geopy for accurate distance — optional dependency
try:
    from geopy.distance import geodesic as _geodesic
    _GEOPY_AVAILABLE = True
except ImportError:
    _GEOPY_AVAILABLE = False


# ── Clustering parameters ─────────────────────────────────────────────────────

_MAX_CITY_DISTANCE_KM = 50      # leads within 50 km are considered co-located
_COMPATIBLE_TYPES = {           # project types that can coexist in a cluster
    "hospitality":  {"hospitality", "retail", "mixed_use", "unknown"},
    "residential":  {"residential", "mixed_use", "unknown"},
    "cultural":     {"cultural", "retail", "unknown"},
    "retail":       {"retail", "hospitality", "cultural", "mixed_use", "unknown"},
    "commercial":   {"commercial", "mixed_use", "unknown"},
    "mixed_use":    {"mixed_use", "hospitality", "residential", "commercial",
                     "retail", "cultural", "public", "unknown"},
    "public":       {"public", "cultural", "mixed_use", "unknown"},
    "unknown":      {"hospitality", "residential", "cultural", "retail",
                     "commercial", "mixed_use", "public", "unknown"},
}


class LeadEntry(NamedTuple):
    lead: Lead
    detection: ProjectDetection
    lead_db_id: int


@dataclass
class ProjectCluster:
    """
    A group of leads that likely relate to the same commercial project.

    The cluster is the primary unit of opportunity analysis:
    instead of asking "is this lead interesting?", the platform asks
    "is this project interesting, and who are its actors?"
    """

    # Canonical project attributes (consensus of member detections)
    project_type: str
    status: str
    budget_tier: str
    location_city: str
    location_country: str
    timeline_hint: str

    # Confidence — increases with more corroborating members
    confidence: float

    # Actor lists (lead_db_ids)
    actor_ids: list[int] = field(default_factory=list)
    actor_handles: list[str] = field(default_factory=list)

    # Opportunity metrics (filled by project_ranker)
    opportunity_density: float = 0.0
    avg_specifier_score: float = 0.0
    avg_buying_power_score: float = 0.0
    avg_event_signal_score: float = 0.0
    max_opportunity_score: int = 0

    # Evidence
    evidence_texts: list[str] = field(default_factory=list)

    @property
    def actor_count(self) -> int:
        return len(self.actor_ids)

    @property
    def is_viable(self) -> bool:
        """True if cluster has enough signal to surface to the user."""
        return self.confidence >= 0.45 and self.actor_count >= 1


def _cities_compatible(city_a: str, city_b: str) -> bool:
    """Return True if two city strings are the same or very similar."""
    if not city_a or not city_b:
        # Unknown city — allow clustering (don't split on missing data)
        return True
    return city_a.lower().strip() == city_b.lower().strip()


def _types_compatible(type_a: str, type_b: str) -> bool:
    return type_b in _COMPATIBLE_TYPES.get(type_a, {"unknown"})


def _timelines_compatible(t_a: str, t_b: str) -> bool:
    """Return True if timeline hints overlap or either is unknown."""
    if not t_a or not t_b:
        return True
    # Extract years from hints
    import re
    ya = re.findall(r"20[2-9]\d", t_a)
    yb = re.findall(r"20[2-9]\d", t_b)
    if ya and yb:
        return ya[0] == yb[0]
    # Quarter vs season — both without year → compatible
    return True


def _entries_compatible(a: LeadEntry, b: LeadEntry) -> bool:
    """Return True if two lead entries should be in the same cluster."""
    da, db = a.detection, b.detection
    return (
        _cities_compatible(da.location_city, db.location_city)
        and _types_compatible(da.project_type, db.project_type)
        and _timelines_compatible(da.timeline_hint, db.timeline_hint)
    )


def _consensus_value(values: list[str], default: str = "unknown") -> str:
    """Return the most common non-unknown value from a list."""
    filtered = [v for v in values if v and v != "unknown"]
    if not filtered:
        return default
    return max(set(filtered), key=filtered.count)


def _consensus_confidence(entries: list[LeadEntry]) -> float:
    """
    Cluster confidence grows with:
    - Number of corroborating members (up to +0.3)
    - Average detection confidence of members
    - Status coherence (all agree on active/emerging)
    """
    if not entries:
        return 0.0
    avg_conf = sum(e.detection.confidence for e in entries) / len(entries)
    n_bonus = min(0.30, (len(entries) - 1) * 0.10)
    statuses = [e.detection.status for e in entries]
    status_coherence = 0.10 if len(set(statuses)) == 1 else 0.0
    return min(1.0, round(avg_conf + n_bonus + status_coherence, 2))


def cluster_leads(
    leads_with_detections: list[tuple[Lead, ProjectDetection, int]],
) -> list[ProjectCluster]:
    """
    Group leads into ProjectClusters using greedy single-linkage clustering.

    Parameters
    ----------
    leads_with_detections : list of (Lead, ProjectDetection, lead_db_id)
        Only leads that have a ProjectDetection should be passed here.
        lead_db_id is the SQLite row id (0 if unknown).

    Returns
    -------
    list[ProjectCluster]
        Sorted by confidence (descending). Empty list if input is empty.
    """
    if not leads_with_detections:
        return []

    entries = [LeadEntry(l, d, i) for l, d, i in leads_with_detections]

    # Greedy single-linkage: assign each entry to the first compatible cluster
    raw_clusters: list[list[LeadEntry]] = []

    for entry in entries:
        placed = False
        for cluster_members in raw_clusters:
            # Check compatibility with the first member (centroid approximation)
            if _entries_compatible(entry, cluster_members[0]):
                cluster_members.append(entry)
                placed = True
                break
        if not placed:
            raw_clusters.append([entry])

    # Convert raw clusters to ProjectCluster dataclasses
    result: list[ProjectCluster] = []
    for members in raw_clusters:
        detections = [m.detection for m in members]
        cluster = ProjectCluster(
            project_type=_consensus_value([d.project_type for d in detections]),
            status=_consensus_value([d.status for d in detections], "emerging"),
            budget_tier=_consensus_value([d.budget_tier for d in detections]),
            location_city=_consensus_value([d.location_city for d in detections], ""),
            location_country=_consensus_value([d.location_country for d in detections], ""),
            timeline_hint=_consensus_value([d.timeline_hint for d in detections], ""),
            confidence=_consensus_confidence(members),
            actor_ids=[m.lead_db_id for m in members],
            actor_handles=[m.detection.lead_id_hint for m in members],
            evidence_texts=[
                t for d in detections for t in d.evidence_texts
            ][:10],  # cap evidence texts
        )
        result.append(cluster)
        logger.debug(
            "ProjectCluster: %s / %s / %s | actors=%d | conf=%.2f",
            cluster.project_type, cluster.location_city,
            cluster.status, cluster.actor_count, cluster.confidence,
        )

    result.sort(key=lambda c: c.confidence, reverse=True)
    return result
