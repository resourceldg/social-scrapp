"""
ProjectAnalyst — AI reasoning over a ProjectCluster.

Takes a ProjectCluster (with BI scores populated by project_ranker) and
calls Ollama to infer project name, scope, budget range, urgency and
recommended commercial approach.

Falls back to rule-based synthesis when Ollama is unavailable.

Usage
-----
    from ai_engine.project_analyst import analyse_project_cluster, AIProjectAnalysis

    analysis = analyse_project_cluster(cluster)
    print(analysis.project_name, analysis.urgency, analysis.recommended_approach)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from project_engine.project_clusterer import ProjectCluster
from ai_engine.ollama_client import call_ollama, is_ai_available
from ai_engine.prompts.project_context import build_project_prompt

logger = logging.getLogger(__name__)

_VALID_URGENCY = frozenset({"immediate", "near_term", "long_term", "unknown"})

_BUDGET_RANGE_MAP = {
    "ultra": "$2M+ USD",
    "high":  "$200K–2M USD",
    "mid":   "$50K–200K USD",
    "micro": "< $50K USD",
    "unknown": "desconocido",
}

_STATUS_URGENCY_MAP = {
    "active":    "immediate",
    "emerging":  "near_term",
    "completed": "long_term",
    "rumour":    "unknown",
}


@dataclass
class AIProjectAnalysis:
    """AI-synthesised intelligence for a ProjectCluster."""
    project_name: str = ""
    summary: str = ""
    key_actors: list[str] = field(default_factory=list)
    estimated_budget_range: str = "desconocido"
    urgency: str = "unknown"
    recommended_approach: str = ""
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)
    source: str = "fallback"


def _rule_based_project_fallback(cluster: ProjectCluster) -> AIProjectAnalysis:
    """Rule-based fallback when Ollama is unavailable."""
    city   = cluster.location_city or "ubicación desconocida"
    ptype  = cluster.project_type.replace("_", " ")
    status = cluster.status

    name = f"Proyecto {ptype} — {city}"

    summary_parts = [f"Cluster de {ptype}"]
    if city:
        summary_parts.append(f"en {city}")
    if cluster.timeline_hint:
        summary_parts.append(f"({cluster.timeline_hint})")
    summary_parts.append(f"con {cluster.actor_count} actor(es)")
    summary = " ".join(summary_parts)

    approach_map = {
        "active":    f"Contactar actores activos — proyecto en marcha en {city}",
        "emerging":  f"Entrar pronto — proyecto emergente en {city}",
        "completed": f"Buscar próximo proyecto — este ya está completado",
        "rumour":    f"Monitorear señales — proyecto en etapa conceptual",
    }

    flags = []
    if cluster.actor_count == 1:
        flags.append("cluster de actor único — baja corroboración")
    if cluster.budget_tier == "unknown":
        flags.append("presupuesto no determinado")
    if cluster.confidence < 0.6:
        flags.append("confianza baja — señales débiles")

    return AIProjectAnalysis(
        project_name=name,
        summary=summary,
        key_actors=cluster.actor_handles[:3],
        estimated_budget_range=_BUDGET_RANGE_MAP.get(cluster.budget_tier, "desconocido"),
        urgency=_STATUS_URGENCY_MAP.get(status, "unknown"),
        recommended_approach=approach_map.get(status, "Monitorear"),
        confidence=round(cluster.confidence * 0.8, 2),  # slight discount for fallback
        flags=flags,
        source="fallback",
    )


def _parse_ai_response(raw: dict, cluster: ProjectCluster) -> AIProjectAnalysis:
    urgency = str(raw.get("urgency", "unknown")).lower().strip()
    if urgency not in _VALID_URGENCY:
        urgency = _STATUS_URGENCY_MAP.get(cluster.status, "unknown")

    return AIProjectAnalysis(
        project_name=str(raw.get("project_name", ""))[:80],
        summary=str(raw.get("summary", ""))[:300],
        key_actors=[str(a) for a in raw.get("key_actors", []) if a][:5],
        estimated_budget_range=str(raw.get("estimated_budget_range", "desconocido"))[:50],
        urgency=urgency,
        recommended_approach=str(raw.get("recommended_approach", ""))[:200],
        confidence=max(0.0, min(1.0, float(raw.get("confidence", cluster.confidence)))),
        flags=[str(f) for f in raw.get("flags", []) if f][:5],
        source="ai",
    )


def analyse_project_cluster(cluster: ProjectCluster) -> AIProjectAnalysis:
    """
    Produce AI intelligence for a ProjectCluster.

    Parameters
    ----------
    cluster : ProjectCluster
        Should have opportunity_density and BI score averages populated
        by project_ranker.enrich_cluster_scores() before calling this.

    Returns
    -------
    AIProjectAnalysis
        Always returns a valid object — never raises.
    """
    if not is_ai_available():
        return _rule_based_project_fallback(cluster)

    prompt = build_project_prompt(
        project_type=cluster.project_type,
        status=cluster.status,
        city=cluster.location_city,
        country=cluster.location_country,
        timeline=cluster.timeline_hint,
        budget_tier=cluster.budget_tier,
        actor_count=cluster.actor_count,
        actor_handles=cluster.actor_handles,
        confidence=cluster.confidence,
        opportunity_density=cluster.opportunity_density,
        avg_specifier=cluster.avg_specifier_score,
        avg_buying_power=cluster.avg_buying_power_score,
        avg_event=cluster.avg_event_signal_score,
        max_opportunity=cluster.max_opportunity_score,
        evidence=cluster.evidence_texts,
    )

    raw = call_ollama(prompt, max_tokens=300, temperature=0.15)
    if raw:
        try:
            analysis = _parse_ai_response(raw, cluster)
            logger.debug(
                "AI project analysis: %s | urgency=%s | conf=%.2f",
                analysis.project_name, analysis.urgency, analysis.confidence,
            )
            return analysis
        except Exception as exc:
            logger.warning("AI project response parse error: %s", exc)

    return _rule_based_project_fallback(cluster)
