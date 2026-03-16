"""
Lead and Opportunity Classification.

Classifies leads into typed categories (architect, collector, gallery, …)
and maps them to actionable opportunity types (specifier_network, active_project, …).

Classification feeds into the dashboard, filtering logic, and CRM exports.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline.signal_types import SignalSet

# ── Lead Classification ────────────────────────────────────────────────────────
# (type_key, keyword_patterns, priority)
# Higher priority wins when multiple types match
_LEAD_TYPE_RULES: list[tuple[str, list[str], int]] = [
    ("gallery", [
        "gallery", "galería", "galeria", "gallerist", "galerista",
        "art space", "espacio de arte", "exhibition space",
    ], 10),
    ("art_consultant", [
        "art advisor", "art consultant", "asesor de arte", "asesora de arte",
        "curator", "curadora", "curador",
    ], 10),
    ("architect", [
        "architect", "arquitecto", "arquitecta", "architecture firm",
        "despacho de arquitectura", "architecture studio",
    ], 9),
    ("interior_designer", [
        "interior designer", "interiorista", "interior design studio",
        "estudio de interiorismo", "diseño de interiores",
        "interior architecture",
    ], 9),
    ("hospitality", [
        "hotel", "resort", "boutique hotel", "luxury hotel",
        "hotelier", "hotelero", "hotelera", "spa", "hospitality",
    ], 8),
    ("collector", [
        "collector", "coleccionista", "private collection",
        "colección privada", "art collector",
    ], 8),
    ("developer", [
        "developer", "promotor", "promotora", "real estate developer",
        "desarrollo inmobiliario", "residential developer",
    ], 7),
    ("design_studio", [
        "design studio", "estudio de diseño", "estudio creativo",
        "creative studio", "atelier", "maison",
    ], 7),
    ("brand", [
        "luxury brand", "marca premium", "lifestyle brand",
        "retail", "showroom", "fashion",
    ], 6),
    ("artist", [
        "artist", "artista", "sculptor", "escultor", "escultora",
        "painter", "pintor", "pintora",
    ], 5),
]

# Map existing lead_type values (from utils/classifiers.py) to our schema
_EXISTING_TYPE_MAP: dict[str, str] = {
    "arquitecto": "architect",
    "interiorista": "interior_designer",
    "galeria": "gallery",
    "curador": "art_consultant",
    "coleccionista": "collector",
    "desarrollador": "developer",
    "estudio": "design_studio",
    "hospitality": "hospitality",
    "hotel": "hospitality",
    "artista": "artist",
    "marca premium": "brand",
    "diseñador": "design_studio",
    "diseniador": "design_studio",
}


def classify_lead(lead: Lead, signal_set: SignalSet) -> str:
    """
    Classify a lead into one of the predefined lead types.

    Precedence order:
    1. Map existing lead_type if already classified
    2. Pattern matching on combined text fields
    3. Fallback to dominant role signal from signal_set

    Returns "unknown" if no match.
    """
    # Use existing classification if it maps cleanly
    lt_lower = (lead.lead_type or "").lower().strip()
    if lt_lower and lt_lower in _EXISTING_TYPE_MAP:
        return _EXISTING_TYPE_MAP[lt_lower]

    bio_lower = (lead.bio or "").lower()
    cat_lower = (lead.category or "").lower()
    combined = f"{bio_lower} {cat_lower} {lt_lower}"

    best_type = "unknown"
    best_priority = -1

    for type_key, patterns, priority in _LEAD_TYPE_RULES:
        if any(p in combined for p in patterns):
            if priority > best_priority:
                best_type = type_key
                best_priority = priority

    # Fallback to signal_set role signals
    if best_type == "unknown" and signal_set.role_signals:
        top_role = max(signal_set.role_signals, key=lambda s: s.weight)
        role_map = {
            "architect": "architect",
            "arquitecto": "architect",
            "arquitecta": "architect",
            "interior designer": "interior_designer",
            "interiorista": "interior_designer",
            "curator": "art_consultant",
            "curador": "art_consultant",
            "gallery director": "gallery",
            "gallerist": "gallery",
            "collector": "collector",
            "coleccionista": "collector",
            "developer": "developer",
            "promotor": "developer",
            "hospitality designer": "hospitality",
            "hotel designer": "hospitality",
        }
        best_type = role_map.get(top_role.value, "unknown")

    return best_type


# ── Opportunity Classification ─────────────────────────────────────────────────

def classify_opportunity(
    lead_classification: str,
    buying_power_score: float,
    specifier_score: float,
    project_signal_score: float,
    opportunity_score: float,
) -> str:
    """
    Map scores and lead type to an actionable opportunity classification.

    Classifications
    ---------------
    active_project      — Hot: imminent project with purchase window
    specifier_network   — High-influence professional (architect, designer, curator)
    direct_buyer        — High buying power (collector, hotelier, developer)
    strategic_partner   — Long-term relationship value (gallery, consultant)
    low_signal          — Insufficient data or weak scores

    Priority order: active_project > specifier_network > direct_buyer >
                    strategic_partner > low_signal
    """
    # Active project is highest urgency regardless of type
    # Threshold 60→40: post-enrichment bios score realistically in the 35–55 range
    if project_signal_score >= 40:
        return "active_project"

    # Specifier network: key roles with strong specifier score
    if specifier_score >= 40 and lead_classification in (
        "architect", "interior_designer", "art_consultant", "gallery"
    ):
        return "specifier_network"

    # Direct buyer: economic power + buyer-type lead
    if buying_power_score >= 40 and lead_classification in (
        "collector", "hospitality", "developer", "brand"
    ):
        return "direct_buyer"

    # Strategic partner: gallery or consultant with medium opportunity signal
    if lead_classification in ("gallery", "art_consultant") and opportunity_score >= 30:
        return "strategic_partner"

    # Low signal fallback
    if opportunity_score < 20:
        return "low_signal"

    # Default for medium-signal leads with no clear category
    return "direct_buyer"
