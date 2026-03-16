from __future__ import annotations

from typing import List

LEAD_TYPE_RULES = {
    "coleccionista": [
        "collector", "coleccionista", "art collecting", "art collection",
        "colección privada", "private collection",
    ],
    "arquitecto": [
        "architect", "arquitecto", "arquitecta", "architecture", "arquitectura",
        "arq.", "despacho de arquitectura",
    ],
    "interiorista": [
        "interior", "interiorista", "interior design", "interiorismo",
        "diseño de interiores", "home staging", "interiordesign",
    ],
    "galeria": [
        "gallery", "galería", "galeria", "art gallery", "espacio de arte",
        "galerie", "contemporary gallery",
    ],
    "curador": [
        "curator", "curaduría", "curador", "curadora", "curatorial",
        "art direction", "dirección artística",
    ],
    "diseñador": [
        "designer", "diseñador", "diseñadora", "design director",
        "creative director", "director creativo", "art director",
    ],
    "estudio": [
        "studio", "estudio", "atelier", "taller", "design studio",
        "creative studio", "estudio de diseño",
    ],
    "hospitality": [
        "hospitality", "hotel design", "boutique hotel", "diseño hotelero",
        "hotel boutique", "resort design", "hospitality design",
    ],
    "hotel": ["hotel", "resort", "lodge", "posada", "hacienda"],
    "restaurante": [
        "restaurant", "restaurante", "gastronomy", "gastronomía",
        "chef", "food design", "bar design",
    ],
    "tienda decoracion": [
        "decor", "furniture", "showroom", "muebles", "decoración",
        "home decor", "tienda de diseño", "design shop",
    ],
    "artista": [
        "artist", "artista", "sculptor", "escultor", "escultora",
        "painter", "pintor", "pintora", "fine art", "bellas artes",
    ],
    "maker": [
        "maker", "handcrafted", "woodworking", "metalworking",
        "artesano", "artesana", "craft", "hecho a mano",
    ],
    "marca premium": [
        "luxury", "premium", "bespoke", "collectible design",
        "lujo", "alta gama", "exclusivo", "edición limitada",
    ],
    "desarrollador": [
        "real estate", "developer", "desarrollador inmobiliario",
        "promotor", "inmobiliaria", "proyecto residencial",
    ],
}

SIGNALS = [
    "arte contemporáneo", "contemporary art", "curaduría", "interiorismo",
    "arquitectura", "decoración", "hotel", "restaurante", "residencial premium",
    "luxury", "bespoke", "collectible design", "sculpture", "handcrafted",
    "wood", "metal", "gallery", "exhibition", "exposición", "instalación",
    "diseño de interiores", "proyecto de diseño", "reforma", "high-end",
    "boutique hotel", "hospitality", "real estate", "coleccionismo",
    "arte emergente", "emerging art", "obra única", "limited edition",
    "edición limitada", "exclusivo",
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
