"""
ProjectDetector — extracts structured project data from a single lead.

For each lead it returns a ProjectDetection with:
  - project_type   (hospitality, residential, commercial, cultural, …)
  - status         (active, emerging, completed, rumour)
  - budget_tier    (micro, mid, high, ultra)
  - location hints (from bio + existing lead.city/country)
  - timeline hints (year, season, "Q3 2025", etc.)
  - confidence     (0.0–1.0)
  - evidence_texts (bio excerpts that triggered the detection)

A lead may produce 0 or 1 ProjectDetection.
Returns None if no meaningful project signal is found.

Usage
-----
    from project_engine.project_detector import detect_project
    detection = detect_project(lead, project_signal_score)
    if detection:
        print(detection.project_type, detection.budget_tier, detection.confidence)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import Lead


# ── Project type classifiers ───────────────────────────────────────────────────

_PROJECT_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("hospitality", [
        r"\b(hotel|boutique hotel|resort|lodge|spa|hostel|inn|motel"
        r"|restaurant|bar|rooftop|lounge|suites?|villa|retreat)\b",
    ]),
    ("residential", [
        r"\b(apartment|condo|penthouse|villa|residence|casa|piso|loft"
        r"|townhouse|townhome|private home|private residence|casa privada"
        r"|vivienda|residencial|mansión|mansion|duplex)\b",
    ]),
    ("cultural", [
        r"\b(museum|gallery|cultural center|centro cultural|arts center"
        r"|theatre|theater|concert hall|exhibition space|arts district"
        r"|cultural space|performance space|museo|galería)\b",
    ]),
    ("retail", [
        r"\b(flagship store|boutique|showroom|retail|pop.?up store"
        r"|concept store|tienda|local comercial|negocio|shop)\b",
    ]),
    ("commercial", [
        r"\b(office|headquarters|hq|corporate|workspace|coworking"
        r"|co.?working|oficinas|sede|edificio comercial)\b",
    ]),
    ("mixed_use", [
        r"\b(mixed.?use|mixed use development|usos mixtos|development"
        r"|tower|complex|proyecto mixto)\b",
    ]),
    ("public", [
        r"\b(public space|plaza|park|civic|infrastructure|library"
        r"|hospital|school|urban|espacio público|parque|biblioteca)\b",
    ]),
]

_PROJECT_TYPE_COMPILED = [
    (ptype, [re.compile(p, re.IGNORECASE) for p in patterns])
    for ptype, patterns in _PROJECT_TYPE_PATTERNS
]


# ── Status classifiers ─────────────────────────────────────────────────────────

_ACTIVE_PATTERNS = re.compile(
    r"\b(opening soon|under construction|fit.?out|fit out|in progress"
    r"|currently working on|new project|launching|coming soon|on site"
    r"|en obra|próxima apertura|en construcción|renovando|remodelando"
    r"|inaugura|pronto|próximamente|now building|breaking ground"
    r"|project reveal|installation|instalación|works in progress"
    r"|wip|currently designing)\b",
    re.IGNORECASE,
)

_COMPLETED_PATTERNS = re.compile(
    r"\b(just opened|now open|recently completed|completed project"
    r"|finished|delivered|handover|project complete|gran apertura"
    r"|recién inaugurado|ya abierto|opened last|open since)\b",
    re.IGNORECASE,
)

_RUMOUR_PATTERNS = re.compile(
    r"\b(planning|exploring|concept|early stages|feasibility|idea stage"
    r"|thinking about|considering|en estudio|anteproyecto|en diseño"
    r"|in design|in concept|early design)\b",
    re.IGNORECASE,
)


# ── Budget tier classifiers ────────────────────────────────────────────────────

_ULTRA_PATTERNS = re.compile(
    r"\b(ultra.?luxury|ultra luxury|5.?star|five.?star|super.?prime"
    r"|trophy property|flagship|private island|mega.?project"
    r"|billion.?dollar|100m\+|€\d{2,}m|landmark project)\b",
    re.IGNORECASE,
)

_HIGH_PATTERNS = re.compile(
    r"\b(luxury|high.?end|premium|bespoke|custom|exclusive|prestige"
    r"|upscale|4.?star|design hotel|boutique hotel|private club"
    r"|lujo|lujo contemporáneo|alta gama|exclusivo|premium)\b",
    re.IGNORECASE,
)

_MID_PATTERNS = re.compile(
    r"\b(mid.?market|mid market|lifestyle brand|lifestyle hotel"
    r"|boutique|design.?forward|contemporary|modern|mercado medio)\b",
    re.IGNORECASE,
)


# ── Timeline extraction ────────────────────────────────────────────────────────

_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")
_QUARTER_RE = re.compile(r"\bQ([1-4])\s*(20[2-9]\d)?\b", re.IGNORECASE)
_SEASON_RE = re.compile(
    r"\b(spring|summer|autumn|fall|winter|primavera|verano|otoño|invierno)"
    r"\s*(20[2-9]\d)?\b",
    re.IGNORECASE,
)


def _extract_timeline(text: str) -> str:
    """Return the most specific timeline hint found in text."""
    q = _QUARTER_RE.search(text)
    if q:
        year_part = f" {q.group(2)}" if q.group(2) else ""
        return f"Q{q.group(1)}{year_part}"
    s = _SEASON_RE.search(text)
    if s:
        year_part = f" {s.group(2)}" if s.group(2) else ""
        return f"{s.group(1).capitalize()}{year_part}"
    y = _YEAR_RE.search(text)
    if y:
        return y.group(1)
    return ""


# ── Location extraction ────────────────────────────────────────────────────────
# Supplement lead.city/country with mentions in the bio text itself.

_KNOWN_CITIES = [
    "miami", "new york", "los angeles", "london", "paris", "milan",
    "barcelona", "madrid", "dubai", "singapore", "hong kong", "tokyo",
    "sydney", "toronto", "mexico city", "ciudad de mexico", "buenos aires",
    "são paulo", "sao paulo", "rio de janeiro", "bogotá", "bogota",
    "santiago", "lima", "amsterdam", "berlin", "vienna", "geneva",
    "zurich", "monaco", "cannes", "rome", "florence", "venice",
    "lisbon", "porto", "istanbul", "athens", "tel aviv", "beirut",
    "cape town", "nairobi", "dubai", "abu dhabi", "doha", "riyadh",
    "miami beach", "palm beach", "the hamptons", "aspen", "st moritz",
    "ibiza", "mykonos", "santorini", "tulum", "punta del este",
]

_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _KNOWN_CITIES) + r")\b",
    re.IGNORECASE,
)


def _extract_city_from_text(text: str) -> str:
    m = _CITY_RE.search(text)
    return m.group(1).title() if m else ""


@dataclass
class ProjectDetection:
    """Structured project data extracted from a single lead."""

    project_type: str                        # hospitality | residential | …
    status: str                              # active | emerging | completed | rumour
    budget_tier: str                         # micro | mid | high | ultra
    timeline_hint: str                       # "Q3 2025", "2024", "Spring 2025", ""
    location_city: str                       # from lead or bio text
    location_country: str                    # from lead
    confidence: float                        # 0.0–1.0
    evidence_texts: list[str] = field(default_factory=list)
    lead_id_hint: str = ""                   # social_handle for traceability


def detect_project(lead: Lead, project_signal_score: float = 0.0) -> ProjectDetection | None:
    """
    Extract structured project data from a lead.

    Returns None if project_signal_score < 20 AND no active/status patterns
    are found — meaning there is no meaningful project signal worth extracting.

    Parameters
    ----------
    lead : Lead
    project_signal_score : float
        Pre-computed ProjectSignalScore from ScoreEngine (0–100).
        Used to gate whether we bother detecting at all.
    """
    text_parts = [lead.bio or "", lead.category or ""]
    if isinstance(lead.raw_data, dict):
        for k in ("caption", "captions", "post_text", "description"):
            v = lead.raw_data.get(k)
            if isinstance(v, str):
                text_parts.append(v)
            elif isinstance(v, list):
                text_parts.extend(str(x) for x in v)
    full_text = " ".join(t for t in text_parts if t)

    if not full_text:
        return None

    # ── Status detection ─────────────────────────────────────────────────────
    if _ACTIVE_PATTERNS.search(full_text):
        status = "active"
    elif _COMPLETED_PATTERNS.search(full_text):
        status = "completed"
    elif _RUMOUR_PATTERNS.search(full_text):
        status = "emerging"
    else:
        status = "emerging"

    # Gate: skip if no active signal and score too low
    has_active_signal = status == "active"
    if not has_active_signal and project_signal_score < 20:
        return None

    # ── Project type ─────────────────────────────────────────────────────────
    project_type = "unknown"
    for ptype, compiled_patterns in _PROJECT_TYPE_COMPILED:
        if any(p.search(full_text) for p in compiled_patterns):
            project_type = ptype
            break

    # Fallback from lead_type
    if project_type == "unknown" and lead.lead_type:
        lt = lead.lead_type.lower()
        if any(k in lt for k in ("hotel", "hospit", "restaur")):
            project_type = "hospitality"
        elif any(k in lt for k in ("resid", "apart", "casa")):
            project_type = "residential"
        elif any(k in lt for k in ("galería", "gallery", "museum")):
            project_type = "cultural"

    # ── Budget tier ──────────────────────────────────────────────────────────
    if _ULTRA_PATTERNS.search(full_text):
        budget_tier = "ultra"
    elif _HIGH_PATTERNS.search(full_text):
        budget_tier = "high"
    elif _MID_PATTERNS.search(full_text):
        budget_tier = "mid"
    else:
        budget_tier = "unknown"

    # ── Location ─────────────────────────────────────────────────────────────
    location_city = lead.city or _extract_city_from_text(full_text)
    location_country = lead.country or ""

    # ── Timeline ─────────────────────────────────────────────────────────────
    timeline_hint = _extract_timeline(full_text)

    # ── Evidence ─────────────────────────────────────────────────────────────
    evidence_texts: list[str] = []
    for pattern in [_ACTIVE_PATTERNS, _COMPLETED_PATTERNS, _RUMOUR_PATTERNS]:
        m = pattern.search(full_text)
        if m:
            start = max(0, m.start() - 60)
            end = min(len(full_text), m.end() + 60)
            evidence_texts.append(full_text[start:end].strip())

    # ── Confidence ───────────────────────────────────────────────────────────
    confidence = 0.3
    if has_active_signal:
        confidence += 0.3
    if project_type != "unknown":
        confidence += 0.15
    if budget_tier != "unknown":
        confidence += 0.10
    if location_city:
        confidence += 0.10
    if timeline_hint:
        confidence += 0.05
    if project_signal_score >= 50:
        confidence += 0.10
    confidence = min(1.0, round(confidence, 2))

    return ProjectDetection(
        project_type=project_type,
        status=status,
        budget_tier=budget_tier,
        timeline_hint=timeline_hint,
        location_city=location_city,
        location_country=location_country,
        confidence=confidence,
        evidence_texts=evidence_texts,
        lead_id_hint=lead.social_handle or lead.name,
    )
