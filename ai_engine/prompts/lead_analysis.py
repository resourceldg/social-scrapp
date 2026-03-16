"""
Prompt template for AILeadAnalysis.

Designed for qwen2.5 (1.5b–7b) in Spanish — the target market is
Latin America / Spain / international luxury sector.

The prompt passes a structured summary of the lead's scoring breakdown
so the LLM reasons over structured data (not just raw bio text).
"""

LEAD_ANALYSIS_PROMPT = """\
Eres un especialista en inteligencia comercial para el ecosistema de arte contemporáneo, \
diseño de colección, arquitectura de lujo e interiorismo premium.

Analiza este perfil de lead y responde ÚNICAMENTE con un JSON válido, sin texto adicional.

--- DATOS DEL LEAD ---
Nombre: {name}
Plataforma: {platform}
Bio: {bio}
Tipo detectado: {lead_type}
Seguidores: {followers}
Ciudad: {city}
País: {country}
Señales de proyecto: {project_signals}
Señales de evento: {event_signals}
Score base: {base_score}/100
Buying Power Score: {buying_power}/100
Specifier Score: {specifier}/100
Project Signal Score: {project_signal}/100
Event Signal Score: {event_signal}/100
Clasificación oportunidad: {opportunity_classification}

--- INSTRUCCIÓN ---
Basándote en los datos anteriores, responde con este JSON exacto:

{{
  "ai_priority_score": <número 0-100, prioridad comercial real de este lead>,
  "lead_type": "<uno de: collector, interior_designer, architect, curator, art_advisor, \
developer, gallery_director, hospitality_designer, hotel_group, brand_director, none>",
  "buying_intent": <número 0-10>,
  "specifier_strength": <número 0-10>,
  "project_context": "<máximo 20 palabras describiendo el proyecto o contexto activo, vacío si no hay>",
  "recommended_action": "<uno de: contact_now, nurture, monitor, skip>",
  "contact_angle": "<máximo 15 palabras: qué ofrecerle y por qué ahora>",
  "confidence": <número 0.0-1.0>,
  "reasons": ["<razón 1>", "<razón 2>"],
  "uncertainties": ["<incertidumbre 1>"]
}}

Criterios:
- contact_now: señal activa de proyecto + presupuesto alto + accesible
- nurture: especificador o comprador potencial sin urgencia inmediata
- monitor: señal débil, vale la pena seguir
- skip: sin relación con el nicho o calidad muy baja
"""


def build_lead_prompt(
    name: str,
    platform: str,
    bio: str,
    lead_type: str,
    followers: str,
    city: str,
    country: str,
    project_signals: list[str],
    event_signals: list[str],
    base_score: int,
    buying_power: float,
    specifier: float,
    project_signal: float,
    event_signal: float,
    opportunity_classification: str,
) -> str:
    return LEAD_ANALYSIS_PROMPT.format(
        name=name or "Desconocido",
        platform=platform,
        bio=(bio or "")[:500],
        lead_type=lead_type or "desconocido",
        followers=followers or "desconocido",
        city=city or "desconocida",
        country=country or "desconocido",
        project_signals=", ".join(project_signals[:5]) if project_signals else "ninguna",
        event_signals=", ".join(event_signals[:5]) if event_signals else "ninguna",
        base_score=base_score,
        buying_power=round(buying_power, 1),
        specifier=round(specifier, 1),
        project_signal=round(project_signal, 1),
        event_signal=round(event_signal, 1),
        opportunity_classification=opportunity_classification,
    )
