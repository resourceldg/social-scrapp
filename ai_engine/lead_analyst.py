"""
LeadAnalyst — produces AILeadAnalysis from a scored Lead.

Accepts a Lead + its LeadScoreResult and calls the local Ollama model
via a structured prompt.  Returns a typed AILeadAnalysis dataclass.

If Ollama is unavailable or the model returns invalid JSON, falls back
to a rule-based analysis derived from the existing scoring data so the
pipeline is never blocked.

Usage
-----
    from ai_engine.lead_analyst import analyse_lead, AILeadAnalysis
    from scoring.score_result import LeadScoreResult

    analysis = analyse_lead(lead, score_result)
    print(analysis.recommended_action, analysis.contact_angle)
    print(analysis.ai_priority_score, analysis.confidence)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from models import Lead
from scoring.score_result import LeadScoreResult
from ai_engine.ollama_client import call_ollama, is_ai_available
from ai_engine.prompts.lead_analysis import build_lead_prompt

logger = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"contact_now", "nurture", "monitor", "skip"})
_VALID_LEAD_TYPES = frozenset({
    "collector", "interior_designer", "architect", "curator", "art_advisor",
    "developer", "gallery_director", "hospitality_designer", "hotel_group",
    "brand_director", "none",
})


@dataclass
class AILeadAnalysis:
    """
    Full AI reasoning output for a single lead.

    All fields have safe defaults — the dataclass is always returned,
    never None.  Check source == "fallback" to know if AI ran.
    """
    ai_priority_score: int = 0           # 0–100: AI's commercial priority
    lead_type: str = "none"              # refined classification
    buying_intent: int = 0               # 0–10
    specifier_strength: int = 0          # 0–10
    project_context: str = ""            # inferred project description
    recommended_action: str = "monitor"  # contact_now | nurture | monitor | skip
    contact_angle: str = ""              # what to offer and why now
    confidence: float = 0.0             # 0.0–1.0
    reasons: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    source: str = "fallback"            # "ai" or "fallback"


def _rule_based_fallback(lead: Lead, result: LeadScoreResult) -> AILeadAnalysis:
    """Derive a best-effort analysis from scoring data when AI is unavailable."""
    score = result.final_score
    opp = result.opportunity_score
    proj = result.project_signal_score
    spec = result.specifier_score
    bp   = result.buying_power_score
    ev   = result.event_signal_score

    # Priority score: weighted blend
    priority = min(100, round(
        score * 0.35 + opp * 0.25 + proj * 0.15 + spec * 0.15 + bp * 0.10
    ))

    # Action
    if proj >= 50 and (bp >= 40 or spec >= 40) and score >= 40:
        action = "contact_now"
    elif spec >= 50 or bp >= 50 or opp >= 45:
        action = "nurture"
    elif score >= 25:
        action = "monitor"
    else:
        action = "skip"

    # Contact angle
    opp_class = result.opportunity_classification
    if opp_class == "active_project":
        angle = "Proyecto activo detectado — ofrecer piezas para especificación"
    elif opp_class == "specifier_network":
        angle = "Especificador clave — construcción de relación a largo plazo"
    elif opp_class == "direct_buyer":
        angle = "Comprador directo — presentar colección premium"
    elif opp_class == "strategic_partner":
        angle = "Socio estratégico — colaboración o representación"
    else:
        angle = "Sin señal clara de acción inmediata"

    reasons = []
    if proj >= 40:
        reasons.append(f"señal de proyecto activo ({round(proj)})")
    if spec >= 40:
        reasons.append(f"rol especificador ({round(spec)})")
    if bp >= 40:
        reasons.append(f"capacidad de compra ({round(bp)})")
    if ev >= 30:
        reasons.append(f"circuito de eventos ({round(ev)})")

    return AILeadAnalysis(
        ai_priority_score=priority,
        lead_type=lead.lead_type or "none",
        buying_intent=min(10, round(bp / 10)),
        specifier_strength=min(10, round(spec / 10)),
        project_context="",
        recommended_action=action,
        contact_angle=angle,
        confidence=round(result.confidence, 2),
        reasons=reasons,
        uncertainties=["análisis basado en reglas — Ollama no disponible"],
        source="fallback",
    )


def _parse_ai_response(raw: dict, lead: Lead, result: LeadScoreResult) -> AILeadAnalysis:
    """Parse and validate the JSON dict returned by Ollama."""
    def _clamp_int(val, lo, hi, default):
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return default

    def _clamp_float(val, lo, hi, default):
        try:
            return max(lo, min(hi, float(val)))
        except (TypeError, ValueError):
            return default

    action = str(raw.get("recommended_action", "monitor")).lower().strip()
    if action not in _VALID_ACTIONS:
        action = "monitor"

    lt = str(raw.get("lead_type", lead.lead_type or "none")).lower().strip()
    if lt not in _VALID_LEAD_TYPES:
        lt = lead.lead_type or "none"

    return AILeadAnalysis(
        ai_priority_score=_clamp_int(raw.get("ai_priority_score"), 0, 100, result.opportunity_score),
        lead_type=lt,
        buying_intent=_clamp_int(raw.get("buying_intent"), 0, 10, 0),
        specifier_strength=_clamp_int(raw.get("specifier_strength"), 0, 10, 0),
        project_context=str(raw.get("project_context", ""))[:200],
        recommended_action=action,
        contact_angle=str(raw.get("contact_angle", ""))[:200],
        confidence=_clamp_float(raw.get("confidence"), 0.0, 1.0, result.confidence),
        reasons=[str(r) for r in raw.get("reasons", []) if r][:5],
        uncertainties=[str(u) for u in raw.get("uncertainties", []) if u][:3],
        source="ai",
    )


def analyse_lead(lead: Lead, result: LeadScoreResult) -> AILeadAnalysis:
    """
    Produce a full AILeadAnalysis for a lead.

    Tries Ollama first; falls back to rule-based analysis on any failure.

    Parameters
    ----------
    lead : Lead
    result : LeadScoreResult
        Output from ScoreEngine.score(lead).

    Returns
    -------
    AILeadAnalysis
        Always returns a valid object — never raises.
    """
    if not is_ai_available():
        return _rule_based_fallback(lead, result)

    # Extract readable signal lists from reasons
    proj_signals = [r for r in result.reasons if "project" in r.lower() or "obra" in r.lower()]
    ev_signals   = [r for r in result.reasons if "event" in r.lower() or "feria" in r.lower()]

    prompt = build_lead_prompt(
        name=lead.name,
        platform=lead.source_platform,
        bio=lead.bio or "",
        lead_type=lead.lead_type or "",
        followers=lead.followers or "",
        city=lead.city or "",
        country=lead.country or "",
        project_signals=proj_signals,
        event_signals=ev_signals,
        base_score=result.final_score,
        buying_power=result.buying_power_score,
        specifier=result.specifier_score,
        project_signal=result.project_signal_score,
        event_signal=result.event_signal_score,
        opportunity_classification=result.opportunity_classification,
    )

    raw = call_ollama(prompt, max_tokens=350, temperature=0.1)
    if raw:
        try:
            analysis = _parse_ai_response(raw, lead, result)
            logger.debug(
                "AI analysed %s/%s: action=%s priority=%d conf=%.2f",
                lead.source_platform, lead.social_handle or lead.name,
                analysis.recommended_action, analysis.ai_priority_score, analysis.confidence,
            )
            return analysis
        except Exception as exc:
            logger.warning("AI response parse error for %s: %s", lead.social_handle, exc)

    return _rule_based_fallback(lead, result)
