"""
SpecifierScore — detects professionals who define what gets bought.

A specifier is someone who influences purchasing decisions without necessarily
paying themselves: architects specify furniture/objects, interior designers
select art, curators influence gallery acquisitions, procurement directors
control budgets.

High SpecifierScore means the lead is a gateway to multiple purchases
across multiple projects over time — high lifetime value.

Especially important for: architecture, interior design, hospitality.
"""
from __future__ import annotations

from models import Lead
from signal_pipeline.signal_types import SignalSet

# (role_term, base_points)
# Points reflect influence over purchasing decisions in the art/design sector
_SPECIFIER_ROLES: list[tuple[str, float]] = [
    ("architect", 25.0),
    ("arquitecto", 25.0),
    ("arquitecta", 25.0),
    ("interior designer", 25.0),
    ("interiorista", 25.0),
    ("curator", 22.0),
    ("curadora", 22.0),
    ("curador", 22.0),
    ("art advisor", 22.0),
    ("art consultant", 22.0),
    ("asesor de arte", 22.0),
    ("asesora de arte", 22.0),
    ("design director", 20.0),
    ("director de diseño", 20.0),
    ("directora de diseño", 20.0),
    ("gallery director", 20.0),
    ("gallerist", 18.0),
    ("galerista", 18.0),
    ("procurement", 18.0),
    ("purchasing", 15.0),
    ("creative director", 15.0),
    ("director creativo", 15.0),
    ("directora creativa", 15.0),
    ("hospitality designer", 22.0),
    ("hotel designer", 22.0),
    ("art director", 15.0),
    ("design consultant", 16.0),
    ("consultor de diseño", 16.0),
]

# Industry contexts that confirm the specifier role is active
_SPECIFIER_CONTEXTS: list[str] = [
    "architecture", "arquitectura",
    "interior design", "interiorismo",
    "hospitality design", "hotel design",
    "art gallery", "galería de arte",
    "design studio", "estudio de diseño",
    "atelier",
]

_STUDIO_TERMS: list[str] = [
    "studio", "estudio", "atelier", "firm", "despacho", "office", "oficina",
]


def score_specifier(
    lead: Lead,
    signal_set: SignalSet,
) -> tuple[float, list[str]]:
    """
    Score the specifier potential of a lead (0–100).

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
    lt_lower = (lead.lead_type or "").lower()
    combined = f"{bio_lower} {cat_lower} {lt_lower}"

    # ── Primary role detection (up to 50 pts) ─────────────────────────────────
    matched: list[tuple[str, float]] = [
        (role, pts) for role, pts in _SPECIFIER_ROLES if role in combined
    ]
    if matched:
        matched.sort(key=lambda x: x[1], reverse=True)
        primary_pts = matched[0][1]
        # Additional matched roles contribute 30% of their value
        additional_pts = sum(r[1] * 0.30 for r in matched[1:])
        pts = min(50.0, primary_pts + additional_pts)
        score += pts
        role_names = ", ".join(r[0] for r in matched[:3])
        reasons.append(f"specifier role(s) detected: {role_names} → +{round(pts)}pts")

    # ── Industry context confirms the role (up to 20 pts) ─────────────────────
    context_hits = sum(1 for ctx in _SPECIFIER_CONTEXTS if ctx in combined)
    if context_hits and matched:
        pts = min(20.0, context_hits * 6.0)
        score += pts
        reasons.append(f"industry context confirms specifier role → +{round(pts)}pts")

    # ── Extracted role signals (up to 20 pts, only if no direct match) ────────
    if not matched and signal_set.role_signals:
        pts = min(20.0, len(signal_set.role_signals) * 4.0)
        score += pts
        reasons.append(f"role signals from profile analysis → +{round(pts)}pts")

    # ── LinkedIn platform amplification (+20%) ────────────────────────────────
    # LinkedIn profiles provide verified professional context
    if lead.source_platform.lower() == "linkedin" and matched:
        pre = score
        score = min(100.0, score * 1.20)
        reasons.append(f"LinkedIn verified professional context → +{round(score - pre)}pts")

    # ── Studio / firm affiliation (+10) ───────────────────────────────────────
    if any(t in combined for t in _STUDIO_TERMS) and matched:
        score = min(100.0, score + 10.0)
        reasons.append("affiliated with studio or firm → +10pts")

    return min(100.0, score), reasons
