from __future__ import annotations

from typing import List

LEAD_TYPE_RULES = {
    "coleccionista": ["collector", "coleccionista", "art collecting"],
    "arquitecto": ["architect", "arquitecto", "architecture"],
    "interiorista": ["interior", "interiorista", "interior design"],
    "galeria": ["gallery", "galería", "galeria"],
    "curador": ["curator", "curaduría", "curador"],
    "diseñador": ["designer", "diseñador", "design director"],
    "estudio": ["studio", "estudio"],
    "hospitality": ["hospitality", "hotel design", "boutique hotel"],
    "hotel": ["hotel", "resort"],
    "restaurante": ["restaurant", "restaurante"],
    "tienda decoracion": ["decor", "furniture", "showroom"],
    "artista": ["artist", "artista", "sculptor"],
    "maker": ["maker", "handcrafted", "woodworking", "metalworking"],
    "marca premium": ["luxury", "premium", "bespoke", "collectible design"],
}

SIGNALS = [
    "arte contemporáneo", "curaduría", "interiorismo", "arquitectura", "decoración",
    "hotel", "restaurante", "residencial premium", "luxury", "bespoke",
    "collectible design", "sculpture", "handcrafted", "wood", "metal", "gallery", "exhibition"
]


def classify_lead(text: str) -> str:
    lowered = (text or "").lower()
    for lead_type, keywords in LEAD_TYPE_RULES.items():
        if any(word in lowered for word in keywords):
            return lead_type
    return ""


def extract_interest_signals(text: str) -> List[str]:
    lowered = (text or "").lower()
    return [s for s in SIGNALS if s.lower() in lowered]
