"""
BuyingPowerScore — estimates economic capacity or budget authority.

High score means the lead likely controls or influences significant budgets
in art acquisition, interior specification, or hospitality procurement.

Signals
-------
- Luxury market positioning (luxury, bespoke, high-end)
- Hospitality sector presence (hotel, resort, boutique)
- Real estate / developer signals
- Premium market locations (Miami, Madrid, …)
- Established studio / firm language
- Contact info completeness (business legitimacy proxy)
"""
from __future__ import annotations

from models import Lead
from signal_pipeline.signal_types import SignalSet

_HOSPITALITY_TERMS: list[str] = [
    "hotel", "resort", "boutique hotel", "luxury hotel",
    "hotelier", "hotelero", "hotelera", "spa", "villa",
    "lodge", "hospitality", "hostelería", "hosteleria",
]

_DEVELOPER_TERMS: list[str] = [
    "developer", "desarrollo inmobiliario", "residential developer",
    "real estate", "bienes raíces", "bienes raices",
    "promotor", "promotora", "property developer",
    "real estate developer",
]

_STUDIO_TERMS: list[str] = [
    "studio", "estudio", "atelier", "maison", "firm",
    "despacho", "office", "oficina", "workshop", "taller",
]


def score_buying_power(
    lead: Lead,
    signal_set: SignalSet,
) -> tuple[float, list[str]]:
    """
    Estimate buying power score (0–100).

    Parameters
    ----------
    lead : Lead
        The lead being scored.
    signal_set : SignalSet
        Pre-extracted signals for this lead.

    Returns
    -------
    tuple[float, list[str]]
        (score_0_to_100, reasons)
    """
    score = 0.0
    reasons: list[str] = []

    bio_lower = (lead.bio or "").lower()
    cat_lower = (lead.category or "").lower()
    combined = f"{bio_lower} {cat_lower}"

    # ── Luxury signals (up to 30 pts) ─────────────────────────────────────────
    luxury_count = len(signal_set.luxury_signals)
    if luxury_count:
        pts = min(30.0, luxury_count * 8.0)
        score += pts
        reasons.append(f"{luxury_count} luxury signal(s) → +{round(pts)}pts")

    # ── Hospitality presence (up to 15 pts) ───────────────────────────────────
    hosp_hits = sum(1 for t in _HOSPITALITY_TERMS if t in combined)
    if hosp_hits:
        pts = min(15.0, hosp_hits * 6.0)
        score += pts
        reasons.append(f"hospitality sector presence → +{round(pts)}pts")

    # ── Real estate / developer signals (up to 10 pts) ────────────────────────
    dev_hits = sum(1 for t in _DEVELOPER_TERMS if t in combined)
    if dev_hits:
        pts = min(10.0, dev_hits * 5.0)
        score += pts
        reasons.append(f"real estate / developer signals → +{round(pts)}pts")

    # ── Premium market locations (up to 20 pts) ───────────────────────────────
    market_count = len(signal_set.market_signals)
    if market_count:
        pts = min(20.0, market_count * 7.0)
        score += pts
        reasons.append(
            f"operating in {market_count} premium market(s) "
            f"({', '.join(s.value for s in signal_set.market_signals[:3])}) "
            f"→ +{round(pts)}pts"
        )

    # ── Established studio / firm (up to 15 pts) ──────────────────────────────
    studio_hits = sum(1 for t in _STUDIO_TERMS if t in combined)
    if studio_hits:
        pts = min(15.0, studio_hits * 5.0)
        score += pts
        reasons.append(f"established studio/firm signals → +{round(pts)}pts")

    # ── Business contact completeness (+10) ───────────────────────────────────
    if lead.email or lead.website:
        score += 10.0
        reasons.append("contact info present (business legitimacy signal)")

    return min(100.0, score), reasons
