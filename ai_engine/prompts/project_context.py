"""Prompt template for AIProjectAnalysis (cluster-level reasoning)."""

PROJECT_ANALYSIS_PROMPT = """\
Eres un especialista en inteligencia de proyectos para el mercado de arte, diseño de lujo \
y arquitectura de hospitality premium.

Analiza este cluster de proyecto inferido y responde ÚNICAMENTE con JSON válido, sin texto adicional.

--- DATOS DEL CLUSTER ---
Tipo de proyecto: {project_type}
Estado: {status}
Ubicación: {city}, {country}
Timeline estimado: {timeline}
Presupuesto estimado: {budget_tier}
Número de actores detectados: {actor_count}
Actores (handles): {actor_handles}
Confianza del cluster: {confidence}
Oportunidad density score: {opportunity_density}
Avg Specifier Score: {avg_specifier}/100
Avg Buying Power: {avg_buying_power}/100
Avg Event Signal: {avg_event}/100
Max Opportunity Score: {max_opportunity}/100
Evidencias de señales: {evidence}

--- INSTRUCCIÓN ---
Responde con este JSON exacto:

{{
  "project_name": "<nombre inferido del proyecto, máximo 6 palabras>",
  "summary": "<descripción del proyecto en máximo 25 palabras>",
  "key_actors": ["<handle o nombre del actor más relevante>"],
  "estimated_budget_range": "<ej: $500K-2M USD, desconocido>",
  "urgency": "<una de: immediate, near_term, long_term, unknown>",
  "recommended_approach": "<máximo 20 palabras: cómo aproximarse comercialmente a este cluster>",
  "confidence": <número 0.0-1.0>,
  "flags": ["<señal importante o advertencia si existe>"]
}}
"""


def build_project_prompt(
    project_type: str,
    status: str,
    city: str,
    country: str,
    timeline: str,
    budget_tier: str,
    actor_count: int,
    actor_handles: list[str],
    confidence: float,
    opportunity_density: float,
    avg_specifier: float,
    avg_buying_power: float,
    avg_event: float,
    max_opportunity: int,
    evidence: list[str],
) -> str:
    return PROJECT_ANALYSIS_PROMPT.format(
        project_type=project_type,
        status=status,
        city=city or "desconocida",
        country=country or "desconocido",
        timeline=timeline or "desconocido",
        budget_tier=budget_tier,
        actor_count=actor_count,
        actor_handles=", ".join(f"@{h}" for h in actor_handles[:8]),
        confidence=round(confidence, 2),
        opportunity_density=round(opportunity_density, 3),
        avg_specifier=round(avg_specifier, 1),
        avg_buying_power=round(avg_buying_power, 1),
        avg_event=round(avg_event, 1),
        max_opportunity=max_opportunity,
        evidence=" | ".join(e[:80] for e in evidence[:3]) if evidence else "ninguna",
    )
