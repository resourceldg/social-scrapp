"""
Project Intelligence Engine.

Infers structured Project entities from lead signals, clusters co-located
leads into ProjectClusters, and ranks them by opportunity density.

Pipeline
--------
1. project_detector   — extract project signals from individual leads
2. project_clusterer  — group leads by (location, timeline, signals) → ProjectCluster
3. project_ranker     — score clusters by opportunity density + actor quality

Public API
----------
from project_engine import ProjectDetection, ProjectCluster
from project_engine import detect_project, cluster_leads, rank_clusters
"""
from project_engine.project_detector import ProjectDetection, detect_project
from project_engine.project_clusterer import ProjectCluster, cluster_leads
from project_engine.project_ranker import rank_clusters

__all__ = [
    "ProjectDetection", "detect_project",
    "ProjectCluster", "cluster_leads",
    "rank_clusters",
]
