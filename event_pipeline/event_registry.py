"""
Event Registry — canonical database of known industry events.

Each entry defines:
  - canonical name (lowercase, used for matching)
  - aliases (variant spellings / abbreviations)
  - event_type
  - prestige_tier: A (global flagship) | B (regional flagship) | C (local/emerging)
  - typical location(s) — city, country
  - typical month (0 = unknown)

Used by event_detector.py to resolve event mentions to structured EventEntry records.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventEntry:
    canonical_name: str
    event_type: str                     # design_week | art_fair | gallery_opening | …
    prestige_tier: str                  # A | B | C
    aliases: tuple[str, ...] = ()
    location_city: str = ""
    location_country: str = ""
    lat: float = 0.0
    lon: float = 0.0
    typical_month: int = 0             # 1–12, 0 = varies / unknown


# ── Tier A — Global Flagship Events ───────────────────────────────────────────

_TIER_A: list[EventEntry] = [
    EventEntry(
        canonical_name="art basel",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("art basel miami", "art basel miami beach", "art basel hong kong",
                 "art basel switzerland", "artbasel"),
        location_city="Basel / Miami / Hong Kong",
        location_country="CH / US / HK",
        typical_month=6,
    ),
    EventEntry(
        canonical_name="frieze",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("frieze london", "frieze new york", "frieze la", "frieze seoul",
                 "frieze masters", "frieze art fair"),
        location_city="London / New York",
        location_country="GB / US",
        typical_month=10,
    ),
    EventEntry(
        canonical_name="salone del mobile",
        event_type="design_week",
        prestige_tier="A",
        aliases=("salone internazionale del mobile", "milan design week",
                 "fuorisalone", "eurocucina", "isaloni", "i saloni",
                 "salone milano", "salon del mueble milan"),
        location_city="Milan",
        location_country="IT",
        lat=45.47, lon=9.10,
        typical_month=4,
    ),
    EventEntry(
        canonical_name="design miami",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("design miami/", "designmiami"),
        location_city="Miami",
        location_country="US",
        lat=25.79, lon=-80.13,
        typical_month=12,
    ),
    EventEntry(
        canonical_name="tefaf",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("tefaf maastricht", "tefaf new york", "the european fine art fair"),
        location_city="Maastricht / New York",
        location_country="NL / US",
        typical_month=3,
    ),
    EventEntry(
        canonical_name="fiac",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("foire internationale d'art contemporain",),
        location_city="Paris",
        location_country="FR",
        lat=48.86, lon=2.35,
        typical_month=10,
    ),
    EventEntry(
        canonical_name="venice biennale",
        event_type="exhibition",
        prestige_tier="A",
        aliases=("la biennale di venezia", "biennale venezia", "venice art biennale",
                 "venice architecture biennale", "biennale di architettura"),
        location_city="Venice",
        location_country="IT",
        lat=45.43, lon=12.34,
        typical_month=5,
    ),
    EventEntry(
        canonical_name="designart london",
        event_type="design_week",
        prestige_tier="A",
        aliases=("designart", "london design festival", "ldf"),
        location_city="London",
        location_country="GB",
        lat=51.51, lon=-0.13,
        typical_month=9,
    ),
    EventEntry(
        canonical_name="nomad",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("nomad circle", "nomad monaco", "nomad st moritz"),
        location_city="Monaco / St Moritz",
        location_country="MC / CH",
        typical_month=3,
    ),
    EventEntry(
        canonical_name="zona maco",
        event_type="art_fair",
        prestige_tier="A",
        aliases=("zona maco mexico", "zonamaco"),
        location_city="Mexico City",
        location_country="MX",
        lat=19.43, lon=-99.13,
        typical_month=2,
    ),
]


# ── Tier B — Regional Flagship Events ─────────────────────────────────────────

_TIER_B: list[EventEntry] = [
    EventEntry(
        canonical_name="design week",
        event_type="design_week",
        prestige_tier="B",
        aliases=("design week miami", "design week madrid", "design week barcelona",
                 "design week new york", "nydc", "nycxdesign", "designweek",
                 "semana del diseño", "semana de diseño"),
        typical_month=0,
    ),
    EventEntry(
        canonical_name="casa cor",
        event_type="exhibition",
        prestige_tier="B",
        aliases=("casacor",),
        location_city="São Paulo / Buenos Aires",
        location_country="BR / AR",
        typical_month=10,
    ),
    EventEntry(
        canonical_name="arco madrid",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("arco", "arco art fair", "arcomadrid"),
        location_city="Madrid",
        location_country="ES",
        lat=40.42, lon=-3.70,
        typical_month=2,
    ),
    EventEntry(
        canonical_name="art week",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("art week miami", "art week new york", "art week london",
                 "artweek", "semana del arte"),
        typical_month=0,
    ),
    EventEntry(
        canonical_name="3-1-3",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("313 art fair", "3-1-3 art fair"),
        location_city="Miami",
        location_country="US",
        typical_month=12,
    ),
    EventEntry(
        canonical_name="cersaie",
        event_type="trade_show",
        prestige_tier="B",
        aliases=(),
        location_city="Bologna",
        location_country="IT",
        lat=44.50, lon=11.34,
        typical_month=9,
    ),
    EventEntry(
        canonical_name="maison et objet",
        event_type="trade_show",
        prestige_tier="B",
        aliases=("maison objet", "m&o", "maison&objet"),
        location_city="Paris",
        location_country="FR",
        lat=48.86, lon=2.35,
        typical_month=9,
    ),
    EventEntry(
        canonical_name="imm cologne",
        event_type="trade_show",
        prestige_tier="B",
        aliases=("imm", "cologne furniture fair"),
        location_city="Cologne",
        location_country="DE",
        lat=50.94, lon=6.96,
        typical_month=1,
    ),
    EventEntry(
        canonical_name="hospitality design",
        event_type="trade_show",
        prestige_tier="B",
        aliases=("hd expo", "hospitality design expo", "hd conference"),
        location_city="Las Vegas",
        location_country="US",
        typical_month=5,
    ),
    EventEntry(
        canonical_name="ad design show",
        event_type="exhibition",
        prestige_tier="B",
        aliases=("architectural digest design show", "ad show"),
        location_city="New York",
        location_country="US",
        typical_month=3,
    ),
    EventEntry(
        canonical_name="casa decor",
        event_type="exhibition",
        prestige_tier="B",
        aliases=("casadecor",),
        location_city="Madrid",
        location_country="ES",
        lat=40.42, lon=-3.70,
        typical_month=4,
    ),
    EventEntry(
        canonical_name="salon art + design",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("salon art and design", "the salon art + design"),
        location_city="New York",
        location_country="US",
        typical_month=11,
    ),
    EventEntry(
        canonical_name="art rio",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("artrio",),
        location_city="Rio de Janeiro",
        location_country="BR",
        typical_month=9,
    ),
    EventEntry(
        canonical_name="arteBA",
        event_type="art_fair",
        prestige_tier="B",
        aliases=("arte ba", "arteba"),
        location_city="Buenos Aires",
        location_country="AR",
        lat=-34.60, lon=-58.38,
        typical_month=5,
    ),
]


# ── Tier C — Local / Emerging Events ──────────────────────────────────────────

_TIER_C_KEYWORDS: list[str] = [
    # generic event types — matched by keyword scan in detector
    "gallery opening", "apertura de galería", "inauguración",
    "vernissage", "pop-up", "pop up show", "open studio",
    "art show", "solo show", "group show", "collective show",
    "art exhibition", "design exhibition", "art walk",
    "launch event", "product launch", "collection launch",
    "preview night", "private view", "opening reception",
    "award ceremony", "design award", "art prize",
]


# ── Consolidated registry ──────────────────────────────────────────────────────

ALL_KNOWN_EVENTS: list[EventEntry] = _TIER_A + _TIER_B


def get_event_entry(name: str) -> EventEntry | None:
    """Look up a canonical event entry by name (case-insensitive)."""
    name_lower = name.lower().strip()
    for entry in ALL_KNOWN_EVENTS:
        if entry.canonical_name == name_lower:
            return entry
        if name_lower in entry.aliases:
            return entry
    return None


def is_tier_c_keyword(text: str) -> bool:
    """Return True if text contains a generic Tier-C event keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _TIER_C_KEYWORDS)
