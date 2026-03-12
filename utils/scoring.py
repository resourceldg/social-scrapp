from __future__ import annotations

from models import Lead


def score_lead(lead: Lead) -> int:
    text = f"{lead.name} {lead.bio} {lead.category} {lead.engagement_hint}".lower()
    score = 0

    if lead.website:
        score += 25
    if lead.email:
        score += 25
    if lead.phone:
        score += 10
    if any(k in text for k in ["arquitect", "interior", "galer", "curad", "arte", "hospitality", "design"]):
        score += 15
    if lead.country.lower() in {"argentina", "españa", "méxico", "chile", "uruguay", "usa"}:
        score += 10
    if any(k in text for k in ["studio", "estudio", "gallery", "company", "director", "firm"]):
        score += 10
    if any(k in text for k in ["compra", "buy", "project", "curadur", "hospitality", "residential premium", "boutique hotel", "real estate", "espacios"]):
        score += 15
    if any(k in text for k in ["luxury", "premium", "bespoke", "collector", "investment"]):
        score += 10

    return min(score, 100)
