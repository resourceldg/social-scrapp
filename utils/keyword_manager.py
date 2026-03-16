"""
KeywordManager — structured, multi-language keyword library.

Organized by:
  - vertical (art, interiors, hospitality, materiality, buyers)
  - language (es / en / pt)
  - type (keyword / hashtag / bio_term / transactional)
  - platform affinity (which platforms a keyword works best on)
  - priority (1=highest)

Usage:
    km = KeywordManager()
    instagram_kws = km.for_platform("instagram", max_keywords=20)
    linkedin_kws  = km.for_platform("linkedin",  max_keywords=15)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Platform = Literal["instagram", "facebook", "linkedin", "pinterest", "reddit", "twitter", "all"]
Language = Literal["es", "en", "pt", "hybrid"]
KwType = Literal["keyword", "hashtag", "bio_term", "transactional", "aspirational"]


@dataclass
class Keyword:
    text: str
    lang: Language
    kw_type: KwType
    verticals: list[str]
    platforms: list[Platform]     # "all" or specific platforms
    priority: int = 2             # 1=highest, 3=lowest
    notes: str = ""


# ── Master keyword table ──────────────────────────────────────────────────────

_KEYWORDS: list[Keyword] = [

    # ══ ARTE / GALERÍAS / CURADURÍA ══════════════════════════════════════════

    Keyword("#artecontemporaneo",   "es", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#galeriadearte",       "es", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#curaduria",           "es", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#coleccionistadearte", "es", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#esculturacontemporanea","es","hashtag",     ["art"],        ["instagram", "twitter"],           1),
    Keyword("#esculturaenmadera",   "es", "hashtag",      ["art","material"],["instagram"],                   1),
    Keyword("#esculturaenhierro",   "es", "hashtag",      ["art","material"],["instagram"],                   1),
    Keyword("#artcollector",        "en", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#contemporaryart",     "en", "hashtag",      ["art"],        ["instagram", "twitter"],           1),
    Keyword("#contemporarysculpture","en","hashtag",      ["art"],        ["instagram", "pinterest"],         1),
    Keyword("#collectibledesign",   "en", "hashtag",      ["art","design"],["instagram","pinterest"],         1),
    Keyword("#artadvisory",         "en", "hashtag",      ["art"],        ["instagram", "linkedin"],          1),
    Keyword("#fineartconsultant",   "en", "hashtag",      ["art"],        ["instagram", "linkedin"],          1),
    Keyword("#artforinteriors",     "en", "hashtag",      ["art","interiors"],["instagram","pinterest"],      1),
    Keyword("#sculpturaldesign",    "en", "hashtag",      ["art","design"],["instagram","pinterest"],         1),

    Keyword("arte contemporáneo",   "es", "keyword",      ["art"],        ["facebook","linkedin","reddit"],   1),
    Keyword("galería de arte",      "es", "keyword",      ["art"],        ["facebook","linkedin"],            1),
    Keyword("galerista",            "es", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("curador de arte",      "es", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("curaduría",            "es", "keyword",      ["art"],        ["facebook","linkedin"],            1),
    Keyword("colección privada",    "es", "keyword",      ["art"],        ["linkedin","facebook"],            1),
    Keyword("coleccionista de arte","es", "keyword",      ["art"],        ["linkedin","facebook"],            1),
    Keyword("arte para interiores", "es", "keyword",      ["art","interiors"],["facebook","linkedin"],        1),
    Keyword("arte para hotel",      "es", "keyword",      ["art","hospitality"],["facebook","linkedin"],      2),
    Keyword("arte para restaurant", "es", "keyword",      ["art","hospitality"],["facebook","linkedin"],      2),
    Keyword("escultura en madera",  "es", "keyword",      ["art","material"],["facebook","reddit"],           1),
    Keyword("escultura en hierro",  "es", "keyword",      ["art","material"],["facebook","reddit"],           1),
    Keyword("arte de autor",        "es", "keyword",      ["art"],        ["facebook","twitter"],             2),
    Keyword("arte escultórico",     "es", "keyword",      ["art"],        ["facebook","linkedin"],            1),

    Keyword("art consultant",       "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("art advisory",         "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("art advisor",          "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("art curation",         "en", "keyword",      ["art"],        ["linkedin","reddit"],              1),
    Keyword("private art collection","en","keyword",      ["art"],        ["linkedin","reddit"],              1),
    Keyword("fine art consultant",  "en", "keyword",      ["art"],        ["linkedin"],                       1),
    Keyword("gallery director",     "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("contemporary sculpture","en","keyword",      ["art"],        ["reddit","pinterest","linkedin"],  1),
    Keyword("collectible art",      "en", "keyword",      ["art"],        ["reddit","pinterest"],             1),
    Keyword("art buyer",            "en", "keyword",      ["art"],        ["linkedin"],                       1),
    Keyword("art patron",           "en", "keyword",      ["art"],        ["linkedin","twitter"],             2),
    Keyword("art procurement",      "en", "keyword",      ["art"],        ["linkedin"],                       1),
    Keyword("exhibition curator",   "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("site specific art",    "en", "keyword",      ["art"],        ["reddit","linkedin"],              2),
    Keyword("commissioned art",     "en", "keyword",      ["art"],        ["reddit","linkedin"],              2),
    Keyword("custom commission",    "en", "keyword",      ["art"],        ["reddit","linkedin"],              2),

    Keyword("arte contemporâneo",   "pt", "keyword",      ["art"],        ["facebook","linkedin"],            2),
    Keyword("galeria de arte",      "pt", "keyword",      ["art"],        ["facebook","linkedin"],            2),
    Keyword("colecionador de arte", "pt", "keyword",      ["art"],        ["linkedin","facebook"],            2),
    Keyword("curador de arte",      "pt", "keyword",      ["art"],        ["linkedin"],                       2),

    # ══ INTERIORISMO / ARQUITECTURA / DISEÑO ═════════════════════════════════

    Keyword("#interiordesign",      "en", "hashtag",      ["interiors"],  ["instagram","twitter","pinterest"],1),
    Keyword("#luxuryinteriors",     "en", "hashtag",      ["interiors"],  ["instagram","pinterest"],          1),
    Keyword("#interiorstyling",     "en", "hashtag",      ["interiors"],  ["instagram","pinterest"],          1),
    Keyword("#architecturestudio",  "en", "hashtag",      ["architecture"],["instagram","pinterest"],         1),
    Keyword("#bespokeinteriors",    "en", "hashtag",      ["interiors"],  ["instagram","pinterest"],          1),
    Keyword("#premiuminteriors",    "en", "hashtag",      ["interiors"],  ["instagram","pinterest"],          1),
    Keyword("#curatedspaces",       "en", "hashtag",      ["interiors"],  ["instagram","pinterest"],          1),
    Keyword("#designobjects",       "en", "hashtag",      ["design"],     ["instagram","pinterest"],          1),
    Keyword("#functionalart",       "en", "hashtag",      ["art","design"],["instagram","pinterest"],         1),
    Keyword("#interioresargentina", "es", "hashtag",      ["interiors"],  ["instagram"],                     1),
    Keyword("#diseñodeinteriores",  "es", "hashtag",      ["interiors"],  ["instagram","twitter"],            1),
    Keyword("#arquitectura",        "es", "hashtag",      ["architecture"],["instagram","twitter"],           1),

    Keyword("diseño de interiores", "es", "keyword",      ["interiors"],  ["facebook","linkedin"],            1),
    Keyword("interiorismo",         "es", "keyword",      ["interiors"],  ["facebook","linkedin","twitter"],  1),
    Keyword("interiorista",         "es", "keyword",      ["interiors"],  ["linkedin","twitter"],             1),
    Keyword("estudio de interiorismo","es","keyword",     ["interiors"],  ["linkedin","facebook"],            1),
    Keyword("estudio de arquitectura","es","keyword",     ["architecture"],["linkedin","facebook"],           1),
    Keyword("arquitecto",           "es", "keyword",      ["architecture"],["linkedin","twitter"],            1),
    Keyword("arquitectura interior","es", "keyword",      ["architecture","interiors"],["linkedin","facebook"],1),
    Keyword("decorador de interiores","es","keyword",     ["interiors"],  ["facebook","linkedin"],            1),
    Keyword("dirección creativa",   "es", "keyword",      ["design"],     ["linkedin","twitter"],             1),
    Keyword("proyecto residencial premium","es","keyword",["interiors","real_estate"],["linkedin"],           1),
    Keyword("diseño premium",       "es", "keyword",      ["design"],     ["linkedin","facebook"],            2),
    Keyword("FF&E consultant",      "en", "keyword",      ["interiors"],  ["linkedin"],                       1),

    Keyword("interior design studio","en","keyword",      ["interiors"],  ["linkedin","reddit","pinterest"],  1),
    Keyword("interior designer",    "en", "keyword",      ["interiors"],  ["linkedin","twitter"],             1),
    Keyword("architecture studio",  "en", "keyword",      ["architecture"],["linkedin","reddit"],             1),
    Keyword("design studio",        "en", "keyword",      ["design"],     ["linkedin","reddit"],              1),
    Keyword("design director",      "en", "keyword",      ["design"],     ["linkedin","twitter"],             1),
    Keyword("creative director",    "en", "keyword",      ["design"],     ["linkedin","twitter"],             1),
    Keyword("spatial design",       "en", "keyword",      ["design"],     ["linkedin","reddit"],              2),
    Keyword("luxury interiors",     "en", "keyword",      ["interiors"],  ["linkedin","reddit","pinterest"],  1),
    Keyword("bespoke interiors",    "en", "keyword",      ["interiors"],  ["linkedin","pinterest"],           1),
    Keyword("residential interiors","en", "keyword",      ["interiors"],  ["linkedin","reddit"],              1),
    Keyword("curated interiors",    "en", "keyword",      ["interiors"],  ["linkedin","pinterest"],           1),
    Keyword("hospitality interiors","en", "keyword",      ["interiors","hospitality"],["linkedin","reddit"],  1),
    Keyword("high-end interiors",   "en", "keyword",      ["interiors"],  ["linkedin","reddit"],              1),
    Keyword("interior styling",     "en", "keyword",      ["interiors"],  ["reddit","pinterest"],             2),
    Keyword("material curator",     "en", "keyword",      ["design"],     ["linkedin"],                       2),
    Keyword("design specification", "en", "keyword",      ["design"],     ["linkedin"],                       2),
    Keyword("architecture studio buenos aires","en","keyword",["architecture"],["linkedin"],                  1),
    Keyword("interior designer argentina","en","keyword", ["interiors"],  ["linkedin"],                       1),

    Keyword("estúdio de arquitetura","pt","keyword",      ["architecture"],["linkedin","facebook"],           2),
    Keyword("designer de interiores","pt","keyword",      ["interiors"],  ["linkedin","facebook"],            2),

    # ══ HOSPITALITY / REAL ESTATE / COMERCIAL ════════════════════════════════

    Keyword("#hospitalitydesign",   "en", "hashtag",      ["hospitality"],["instagram","pinterest","twitter"],1),
    Keyword("#boutiquehotel",       "en", "hashtag",      ["hospitality"],["instagram","pinterest"],          1),
    Keyword("#restaurantdesign",    "en", "hashtag",      ["hospitality"],["instagram","pinterest"],          1),
    Keyword("#hoteldesign",         "en", "hashtag",      ["hospitality"],["instagram","pinterest"],          1),

    Keyword("hospitality design",   "en", "keyword",      ["hospitality"],["linkedin","reddit"],              1),
    Keyword("hotel design",         "en", "keyword",      ["hospitality"],["linkedin","reddit"],              1),
    Keyword("boutique hotel",       "en", "keyword",      ["hospitality"],["linkedin","reddit","facebook"],   1),
    Keyword("luxury hotel",         "en", "keyword",      ["hospitality"],["linkedin","reddit"],              1),
    Keyword("boutique hotel design","en", "keyword",      ["hospitality"],["linkedin","pinterest"],           1),
    Keyword("premium restaurant design","en","keyword",   ["hospitality"],["linkedin"],                       1),
    Keyword("restaurant interiors", "en", "keyword",      ["hospitality"],["linkedin","reddit"],              1),
    Keyword("real estate developer","en", "keyword",      ["real_estate"],["linkedin"],                       1),
    Keyword("luxury real estate",   "en", "keyword",      ["real_estate"],["linkedin","facebook"],            1),
    Keyword("premium developments", "en", "keyword",      ["real_estate"],["linkedin"],                       1),
    Keyword("branded residences",   "en", "keyword",      ["real_estate","hospitality"],["linkedin"],         1),
    Keyword("commercial interiors", "en", "keyword",      ["interiors"],  ["linkedin","reddit"],              2),
    Keyword("lobby design",         "en", "keyword",      ["hospitality","interiors"],["linkedin","pinterest"],1),
    Keyword("curated hospitality",  "en", "keyword",      ["hospitality"],["linkedin","twitter"],             1),
    Keyword("hotel curator",        "en", "keyword",      ["hospitality","art"],["linkedin","twitter"],       1),
    Keyword("procurement design",   "en", "keyword",      ["design"],     ["linkedin"],                       1),
    Keyword("contract design",      "en", "keyword",      ["design"],     ["linkedin"],                       2),
    Keyword("guest experience design","en","keyword",     ["hospitality"],["linkedin"],                       2),
    Keyword("experiential spaces",  "en", "keyword",      ["hospitality","design"],["linkedin","reddit"],     2),

    Keyword("diseño hotelero",      "es", "keyword",      ["hospitality"],["linkedin","facebook"],            1),
    Keyword("hotel boutique",       "es", "keyword",      ["hospitality"],["linkedin","facebook"],            1),
    Keyword("desarrollador inmobiliario","es","keyword",  ["real_estate"],["linkedin"],                       1),
    Keyword("proyecto residencial", "es", "keyword",      ["real_estate"],["linkedin","facebook"],            1),
    Keyword("diseño de restaurantes","es","keyword",      ["hospitality"],["linkedin","facebook"],            1),

    # ══ MATERIALIDAD / OFICIO / HANDMADE ═════════════════════════════════════

    Keyword("#woodart",             "en", "hashtag",      ["material"],   ["instagram","pinterest"],          1),
    Keyword("#metalart",            "en", "hashtag",      ["material"],   ["instagram","pinterest"],          1),
    Keyword("#handcrafteddesign",   "en", "hashtag",      ["material"],   ["instagram","pinterest"],          1),
    Keyword("#bespokedesign",       "en", "hashtag",      ["design","material"],["instagram","pinterest"],    1),
    Keyword("#designerfurniture",   "en", "hashtag",      ["design"],     ["instagram","pinterest"],          1),
    Keyword("#sculptureart",        "en", "hashtag",      ["art","material"],["instagram","twitter"],         1),
    Keyword("#handcraftedart",      "en", "hashtag",      ["art","material"],["instagram"],                   1),

    Keyword("madera artesanal",     "es", "keyword",      ["material"],   ["facebook","reddit"],              1),
    Keyword("hierro artesanal",     "es", "keyword",      ["material"],   ["facebook","reddit"],              1),
    Keyword("metal art",            "en", "keyword",      ["material","art"],["reddit","facebook"],           1),
    Keyword("wood art",             "en", "keyword",      ["material","art"],["reddit","facebook","pinterest"],1),
    Keyword("handcrafted sculpture","en", "keyword",      ["material","art"],["reddit","pinterest"],          1),
    Keyword("artisan furniture",    "en", "keyword",      ["material","design"],["reddit","pinterest"],       1),
    Keyword("bespoke furniture",    "en", "keyword",      ["material","design"],["linkedin","reddit"],        1),
    Keyword("collectible design",   "en", "keyword",      ["design","art"],["reddit","linkedin","pinterest"], 1),
    Keyword("functional art",       "en", "keyword",      ["art","design"],["reddit","pinterest"],            1),
    Keyword("artisanal decor",      "en", "keyword",      ["material","design"],["reddit","pinterest"],       2),
    Keyword("metal sculpture",      "en", "keyword",      ["material","art"],["reddit","pinterest"],          1),
    Keyword("wood sculpture",       "en", "keyword",      ["material","art"],["reddit","pinterest"],          1),
    Keyword("artisanal objects",    "en", "keyword",      ["material"],   ["reddit","pinterest"],             2),
    Keyword("custom made decor",    "en", "keyword",      ["material","design"],["reddit","facebook"],        2),
    Keyword("sculptural furniture", "en", "keyword",      ["design","art"],["linkedin","pinterest","reddit"], 1),
    Keyword("statement piece",      "en", "keyword",      ["design","art"],["reddit","pinterest"],            2),
    Keyword("signature piece",      "en", "keyword",      ["design","art"],["reddit","pinterest"],            2),
    Keyword("design object",        "en", "keyword",      ["design"],     ["reddit","linkedin"],              2),
    Keyword("luxury decor",         "en", "keyword",      ["design"],     ["reddit","pinterest"],             1),
    Keyword("woodworking",          "en", "keyword",      ["material"],   ["reddit"],                         1),
    Keyword("metalworking",         "en", "keyword",      ["material"],   ["reddit"],                         1),
    Keyword("sculpture",            "en", "keyword",      ["art","material"],["reddit","pinterest"],          1),
    Keyword("art collecting",       "en", "keyword",      ["art"],        ["reddit"],                         1),
    Keyword("luxury homes",         "en", "keyword",      ["real_estate","interiors"],["reddit"],             1),

    # ══ PERFIL COMPRADOR / INTENCIÓN COMERCIAL ════════════════════════════════

    Keyword("art sourcing",         "en", "transactional",["art"],        ["linkedin","twitter"],             1),
    Keyword("sourcing for interiors","en","transactional",["interiors","art"],["linkedin"],                   1),
    Keyword("art selection",        "en", "transactional",["art"],        ["linkedin","twitter"],             1),
    Keyword("specify art",          "en", "transactional",["art","design"],["linkedin"],                      1),
    Keyword("design procurement",   "en", "transactional",["design"],     ["linkedin"],                       1),
    Keyword("curating spaces",      "en", "transactional",["interiors","art"],["linkedin","twitter"],         1),
    Keyword("project sourcing",     "en", "transactional",["design"],     ["linkedin"],                       1),
    Keyword("art for projects",     "en", "transactional",["art"],        ["linkedin","twitter"],             1),
    Keyword("collector services",   "en", "transactional",["art"],        ["linkedin"],                       1),
    Keyword("acquisition advisory", "en", "transactional",["art"],        ["linkedin"],                       1),
    Keyword("procurement manager",  "en", "transactional",["design"],     ["linkedin"],                       1),
    Keyword("project director",     "en", "transactional",["design"],     ["linkedin"],                       1),
    Keyword("boutique developer",   "en", "transactional",["real_estate"],["linkedin"],                       1),
    Keyword("luxury homeowner",     "en", "aspirational", ["real_estate"],["linkedin","reddit"],              2),
    Keyword("private client design","en", "transactional",["design"],     ["linkedin"],                       1),
    Keyword("residential project manager","en","transactional",["real_estate"],["linkedin"],                  1),
    Keyword("compra arte",          "es", "transactional",["art"],        ["twitter","linkedin"],             1),
    Keyword("adquisición de arte",  "es", "transactional",["art"],        ["linkedin","twitter"],             1),
    Keyword("curadur arte espacios","es", "transactional",["art","interiors"],["linkedin"],                   1),

    # ══ ASPIRACIONALES / BIO TERMS ════════════════════════════════════════════

    Keyword("art lover",            "en", "bio_term",     ["art"],        ["instagram","twitter"],            2),
    Keyword("design enthusiast",    "en", "bio_term",     ["design"],     ["instagram","twitter"],            2),
    Keyword("collector",            "en", "bio_term",     ["art"],        ["instagram","linkedin","twitter"], 1),
    Keyword("curator",              "en", "bio_term",     ["art"],        ["instagram","linkedin","twitter"], 1),
    Keyword("architect",            "en", "bio_term",     ["architecture"],["instagram","linkedin","twitter"],1),
    Keyword("interior designer",    "en", "bio_term",     ["interiors"],  ["instagram","linkedin","twitter"], 1),
    Keyword("art director",         "en", "bio_term",     ["design","art"],["instagram","linkedin","twitter"],1),
    Keyword("art consultant",       "en", "bio_term",     ["art"],        ["instagram","linkedin"],           1),
    Keyword("decoradora",           "es", "bio_term",     ["interiors"],  ["instagram","twitter"],            1),
    Keyword("arquitecto",           "es", "bio_term",     ["architecture"],["instagram","linkedin","twitter"],1),
    Keyword("galerista",            "es", "bio_term",     ["art"],        ["instagram","twitter"],            1),
    Keyword("arte contemporaneo interiores","es","keyword",["art","interiors"],["twitter"],                   1),
    Keyword("diseño de interiores arte","es","keyword",   ["art","interiors"],["twitter"],                    1),
    Keyword("interior designer art","en", "keyword",      ["art","interiors"],["twitter"],                    1),
    Keyword("architecture art",     "en", "keyword",      ["architecture","art"],["twitter"],                 1),
    Keyword("sculpture wood metal", "en", "keyword",      ["art","material"],["twitter"],                     1),
    Keyword("art collector",        "en", "keyword",      ["art"],        ["twitter","linkedin"],             1),
    Keyword("curador de arte",      "es", "keyword",      ["art"],        ["twitter","linkedin"],             1),

    # ══ UBICACIONES / MERCADOS PRIORITARIOS ══════════════════════════════════

    Keyword("Buenos Aires interior design","en","keyword",["interiors"],  ["linkedin"],                       1),
    Keyword("art gallery Buenos Aires","en","keyword",    ["art"],        ["linkedin","facebook"],             1),
    Keyword("architecture Buenos Aires","en","keyword",  ["architecture"],["linkedin"],                       1),
    Keyword("Miami art collector",  "en", "keyword",      ["art"],        ["linkedin","twitter"],             1),
    Keyword("Madrid galería de arte","es","keyword",      ["art"],        ["linkedin","facebook"],             1),
    Keyword("Barcelona diseño interior","es","keyword",   ["interiors"],  ["linkedin","facebook"],            1),
    Keyword("CDMX interiorismo",    "es", "keyword",      ["interiors"],  ["linkedin","facebook"],            1),
    Keyword("Bogotá arte contemporáneo","es","keyword",   ["art"],        ["linkedin","facebook"],            2),
    Keyword("Santiago interior design","en","keyword",    ["interiors"],  ["linkedin"],                       2),
    Keyword("São Paulo design",     "pt", "keyword",      ["design"],     ["linkedin","facebook"],            2),
    Keyword("Punta del Este arte",  "es", "keyword",      ["art"],        ["linkedin","facebook"],            2),
]


class KeywordManager:
    """
    Provides filtered, de-duplicated keyword lists per platform and context.
    """

    def __init__(self) -> None:
        self._kws = _KEYWORDS

    def for_platform(
        self,
        platform: str,
        *,
        max_keywords: int = 50,
        types: list[KwType] | None = None,
        verticals: list[str] | None = None,
        min_priority: int = 3,
    ) -> list[str]:
        """
        Return keyword text strings for a given platform, sorted by priority.

        Args:
            platform:     Target platform name.
            max_keywords: Cap on number of keywords returned.
            types:        Filter by keyword type(s); None = all.
            verticals:    Filter by vertical(s); None = all.
            min_priority: Include keywords with priority ≤ this value.
        """
        seen: set[str] = set()
        results: list[Keyword] = []

        for kw in sorted(self._kws, key=lambda k: k.priority):
            if kw.priority > min_priority:
                continue
            if types and kw.kw_type not in types:
                continue
            if verticals and not any(v in kw.verticals for v in verticals):
                continue
            if "all" not in kw.platforms and platform not in kw.platforms:
                continue
            if kw.text in seen:
                continue
            seen.add(kw.text)
            results.append(kw)
            if len(results) >= max_keywords:
                break

        return [k.text for k in results]

    def hashtags_for(self, platform: str, max_keywords: int = 30) -> list[str]:
        return self.for_platform(platform, max_keywords=max_keywords, types=["hashtag"])

    def keywords_for(self, platform: str, max_keywords: int = 30) -> list[str]:
        return self.for_platform(
            platform, max_keywords=max_keywords,
            types=["keyword", "transactional", "aspirational", "bio_term"],
        )

    def all_for_platform(self, platform: str, max_keywords: int = 50) -> list[str]:
        """Combined hashtags + keywords, hashtags first for Instagram-like platforms."""
        if platform in ("instagram", "twitter"):
            tags = self.hashtags_for(platform, max_keywords=max_keywords // 2)
            kws = self.keywords_for(platform, max_keywords=max_keywords // 2)
            combined = tags + [k for k in kws if k not in set(tags)]
        else:
            kws = self.keywords_for(platform, max_keywords=max_keywords)
            tags = self.hashtags_for(platform, max_keywords=10)
            combined = kws + [t for t in tags if t not in set(kws)]
        return combined[:max_keywords]

    def summary(self) -> dict:
        by_platform: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for kw in self._kws:
            for p in kw.platforms:
                by_platform[p] = by_platform.get(p, 0) + 1
            by_lang[kw.lang] = by_lang.get(kw.lang, 0) + 1
            by_type[kw.kw_type] = by_type.get(kw.kw_type, 0) + 1
        return {
            "total": len(self._kws),
            "by_platform": by_platform,
            "by_language": by_lang,
            "by_type": by_type,
        }
