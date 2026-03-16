"""
Universal (platform-agnostic) dimension scorers.

Each function accepts a Lead and returns:
    (score: float, reasons: list[str])

where score is in the range 0–100 and reasons are human-readable strings
explaining what contributed to the score (or warnings for data quality).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from models import Lead

# Professional TLDs and domain keywords that indicate a studio / firm website
_PROFESSIONAL_TLDS = (".studio", ".design", ".arq", ".arch", ".art", ".gallery")
_PROFESSIONAL_DOMAIN_KW = frozenset(
    {"studio", "design", "arch", "arq", "art", "gallery", "interiors", "atelier"}
)


def _has_professional_domain(website: str) -> bool:
    """Return True if the website domain signals a professional creative/design entity."""
    if not website:
        return False
    try:
        netloc = urlparse(website).netloc.lower().lstrip("www.")
        if any(netloc.endswith(tld) for tld in _PROFESSIONAL_TLDS):
            return True
        # Check the domain name segment (before first dot)
        domain_name = netloc.split(".")[0]
        return any(kw in domain_name for kw in _PROFESSIONAL_DOMAIN_KW)
    except Exception:
        return False

# ── Keyword banks ──────────────────────────────────────────────────────────────

# Core business niche — strongest signal, 20 pts each
_RELEVANCE_CORE: list[str] = [
    "collectible design",
    "arte contemporáneo", "contemporary art",
    "escultura", "sculpture", "sculptor", "escultor",
    "madera artesanal", "handcrafted wood", "woodworking",
    "hierro artesanal", "ironwork", "metalwork", "wrought iron", "forja",
    "interiorismo", "interior design", "diseño de interiores",
    "arquitectura", "architecture",
    "hospitality design", "boutique hotel", "hotel design",
    "art consultant", "art advisory",
    # PT-BR
    "arquitetura", "design de interiores", "galeria de arte",
]

# Adjacent industries — medium signal, 12 pts each
_RELEVANCE_ADJACENT: list[str] = [
    "interior", "hospitality",
    "gallery", "galería", "galeria",
    "curator", "curador", "curadur",
    "coleccionista", "collector",
    "residential premium", "residencia premium",
    "real estate", "desarrollador inmobiliario",
    "design studio", "estudio de diseño",
    "art director", "dirección artística",
]

# Weak supporting signals — 6 pts each (word-boundary matched)
_RELEVANCE_SUPPORTING: list[str] = [
    "luxury", "premium", "bespoke", "high-end", "exclusivo",
    "arte", "art", "artista", "artist",   # \b matching prevents "artisan" false positive
    "decor", "decorac",
    "restaurante", "restaurant", "hotel", "resort",
    "atelier", "estudio", "studio", "taller",
    "architect", "diseño", "design",
]
# Pre-compiled word-boundary patterns for supporting keywords
_RELEVANCE_SUPPORTING_RE: list[re.Pattern] = [
    re.compile(r"\b" + re.escape(kw), re.IGNORECASE | re.UNICODE)
    for kw in _RELEVANCE_SUPPORTING
]

# Commercial intent — (keyword, points) pairs
_COMMERCIAL_INTENT: list[tuple[str, int]] = [
    ("art advisory", 25),
    ("gallery sales", 25),
    ("hospitality project", 25),
    ("interior design project", 25),
    ("commission", 20),
    ("encargo", 20),
    ("obra nueva", 20),
    ("sourcing", 18),
    ("procurement", 18),
    ("project", 15),
    ("proyecto", 15),
    ("compra", 15),
    ("buy", 12),
    ("reforma", 12),
    ("instalación", 12),
    ("installation", 12),
    ("residencial", 10),
]

# Premium/luxury fit — (keyword, points) pairs
_PREMIUM_FIT: list[tuple[str, int]] = [
    ("obra única", 25),
    ("private collection", 25),
    ("colección privada", 25),
    ("collectible design", 22),
    ("boutique hotel", 22),
    ("bespoke", 20),
    ("luxury", 18),
    ("lujo", 18),
    ("high-end", 18),
    ("premium interiors", 18),
    ("edición limitada", 15),
    ("limited edition", 15),
    ("exclusivo", 8),      # generic — reduced from 15
    ("exclusiva", 8),
    ("curated", 5),        # marketing buzzword — reduced from 12
    ("premium", 5),        # too common — reduced from 12
]

_TARGET_COUNTRIES: frozenset[str] = frozenset({
    "argentina", "españa", "spain", "méxico", "mexico", "chile",
    "uruguay", "colombia", "perú", "peru", "brasil", "brazil",
    "usa", "united states", "france", "francia",
    "italy", "italia", "uk", "united kingdom",
})


# ── Dimension functions ────────────────────────────────────────────────────────

def score_contactability(lead: Lead) -> tuple[float, list[str]]:
    """
    Measure how reachable this lead is (0–100).

    Direct signals
    --------------
    email                   +40
    website                 +25
    phone                   +20

    Inferred signals (when direct contact unavailable)
    ---------------------------------------------------
    LinkedIn URL in bio     +15  (cross-platform reference)
    Professional domain     +10  (.studio, .design, domain with studio/arch/art)
    """
    score = 0.0
    reasons: list[str] = []

    if lead.email:
        score += 40
        reasons.append("email available")
    if lead.website:
        score += 25
        reasons.append("website available")
    if lead.phone:
        score += 20
        reasons.append("phone available")

    text_lower = f"{lead.bio} {lead.profile_url}".lower()
    if "linkedin.com" in text_lower and lead.source_platform != "linkedin":
        score += 15
        reasons.append("linkedin profile referenced")

    if _has_professional_domain(lead.website):
        score += 10
        reasons.append("professional domain detected")

    return min(100.0, score), reasons


def score_relevance(lead: Lead) -> tuple[float, list[str]]:
    """
    Measure alignment with the business niche (0–100).

    Uses a three-tier keyword bank:
      core (20 pts, max 4) > adjacent (12 pts, max 4) > supporting (6 pts, max 5)
    Per-tier caps prevent keyword-stuffed bios from crowding out more relevant leads.
    Supporting tier uses word-boundary matching (compiled regex).
    Plus bonuses for classified lead_type and target country.
    """
    text = " ".join([
        lead.name,
        lead.bio,
        lead.category,
        lead.engagement_hint,
        lead.lead_type,
        " ".join(lead.interest_signals),
    ]).lower()

    score = 0.0
    reasons: list[str] = []

    core_count = 0
    for kw in _RELEVANCE_CORE:
        if core_count >= 4:
            break
        if kw in text:
            score += 20
            reasons.append(f"core: {kw}")
            core_count += 1

    adj_count = 0
    for kw in _RELEVANCE_ADJACENT:
        if adj_count >= 4:
            break
        if kw in text:
            score += 12
            reasons.append(f"adjacent: {kw}")
            adj_count += 1

    sup_count = 0
    for compiled_re in _RELEVANCE_SUPPORTING_RE:
        if sup_count >= 5:
            break
        if compiled_re.search(text):
            score += 6
            sup_count += 1
            # supporting keywords are not individually listed in reasons

    if lead.lead_type:
        score += 10
        reasons.append(f"classified as: {lead.lead_type}")

    if lead.country.lower() in _TARGET_COUNTRIES:
        score += 8
        reasons.append(f"target country: {lead.country}")

    # R16: optional semantic boost (requires sentence-transformers; degrades gracefully)
    from scoring.semantic_relevance import semantic_boost
    sem_boost, sem_reason = semantic_boost(text)
    if sem_boost > 0:
        score += sem_boost
        reasons.append(sem_reason)

    return min(100.0, score), reasons


def score_authority(
    lead: Lead,
    buckets: list[tuple[int, int]] | None = None,
) -> tuple[float, list[str]]:
    """
    Measure influence or audience reach (0–100).

    Uses GENERIC_FOLLOWER_BUCKETS by default. Pass a custom bucket list for
    platform-specific calibration (the platform scorers do this internally).
    """
    from scoring.thresholds import GENERIC_FOLLOWER_BUCKETS, follower_score

    used_buckets = buckets if buckets is not None else GENERIC_FOLLOWER_BUCKETS
    score = float(follower_score(lead.followers, used_buckets))
    reasons: list[str] = []

    if score > 0:
        reasons.append(f"followers: {lead.followers}")

    if lead.engagement_hint:
        score = min(100.0, score + 10)
        reasons.append("engagement data present")

    bio_lower = (lead.bio or "").lower()
    if any(w in bio_lower for w in ("✓", "✔", "verified")):
        score = min(100.0, score + 10)
        reasons.append("verified indicator in bio")

    return min(100.0, score), reasons


def score_commercial_intent(lead: Lead) -> tuple[float, list[str]]:
    """
    Measure proximity to purchase or project intent (0–100).

    Scans bio, category, and engagement_hint for buying/commissioning signals.
    """
    text = " ".join([lead.bio, lead.category, lead.engagement_hint]).lower()
    score = 0.0
    reasons: list[str] = []

    for keyword, points in _COMMERCIAL_INTENT:
        if keyword in text:
            score += points
            reasons.append(f"intent: {keyword}")

    return min(100.0, score), reasons


def score_premium_fit(lead: Lead) -> tuple[float, list[str]]:
    """
    Measure affinity with the high-end / luxury market segment (0–100).
    """
    text = " ".join([
        lead.bio, lead.category, lead.name, lead.engagement_hint,
    ]).lower()
    score = 0.0
    reasons: list[str] = []

    for keyword, points in _PREMIUM_FIT:
        if keyword in text:
            score += points
            reasons.append(f"premium: {keyword}")

    return min(100.0, score), reasons


def score_data_quality(lead: Lead) -> tuple[float, list[str]]:
    """
    Measure completeness and reliability of the lead record (0–100).

    Starts at 100 and subtracts penalties for missing or suspicious fields.

    Returns
    -------
    score : float
        Quality score (0–100).
    warnings : list[str]
        Issues found (returned as the second element so callers can surface
        them separately from positive reasons).
    """
    score = 100.0
    warnings: list[str] = []

    if not lead.bio or len(lead.bio.strip()) == 0:
        score -= 30
        warnings.append("missing bio")
    elif len(lead.bio.strip()) < 20:
        score -= 20
        warnings.append("bio too short")

    if not lead.name:
        score -= 15
        warnings.append("missing name")
    elif lead.name == lead.social_handle and lead.source_platform not in (
        "instagram", "twitter", "pinterest", "reddit"
    ):
        # On LinkedIn/Facebook the real name is available — flag when missing.
        # On Instagram/Twitter/Pinterest/Reddit the handle IS the identity; no penalty.
        score -= 10
        warnings.append("name equals handle (not enriched)")

    if not lead.lead_type:
        score -= 10
        warnings.append("no lead type classified")

    if not lead.followers:
        score -= 10
        warnings.append("no follower data")

    if not lead.country:
        score -= 5
        warnings.append("no country detected")

    return max(0.0, score), warnings


def compute_confidence(lead: Lead) -> float:
    """
    Estimate how reliable the overall score is (0.0–1.0).

    Based on data completeness: bio, followers, contact, name, lead_type, country.
    """
    score = 0.0

    if lead.bio and len(lead.bio.strip()) > 20:
        score += 0.25
    if lead.followers:
        score += 0.20
    if lead.email or lead.website:
        score += 0.25
    if lead.name and lead.name != lead.social_handle:
        score += 0.15
    if lead.lead_type:
        score += 0.10
    if lead.country:
        score += 0.05

    return min(1.0, score)


# ── Spam / authenticity risk ───────────────────────────────────────────────────

# Call-to-action patterns that indicate a commercial/influencer account rather
# than a genuine professional
_SPAM_CTA_RE = re.compile(
    r"\b(dm\s*(me|us|for)|link\s*in\s*bio|collab(oration)?s?\s*(open|welcome)|"
    r"promo\s*code|affiliate|sponsored|gifted|ad\b|#ad\b|"
    r"follow\s*for\s*follow|f4f|l4l|like\s*for\s*like|"
    r"giveaway|sorteo|concurso\s*gratis|"
    r"only\s*fans|onlyfans|subscribe\s*to\s*my)",
    re.IGNORECASE | re.UNICODE,
)
# Excessive hashtag use in bio (more than 4 hashtags → spam signal)
_HASHTAG_RE = re.compile(r"#\w+")


def score_spam_risk(lead: Lead) -> tuple[float, list[str]]:
    """
    Estimate the probability that the lead is a spam / inauthentic account (0–100).

    Scoring
    -------
    CTA patterns (DM me, link in bio, promo code, etc.)  +20 each, max +40
    Excessive hashtags in bio (>4)                        +20
    Bio is only hashtags / emojis (no real words)         +25
    Emoji density > 30% of bio chars                      +15

    Leads scoring >= 60 should be flagged for manual review.
    Leads scoring >= 80 are very likely noise.
    """
    bio = lead.bio or ""
    score = 0.0
    flags: list[str] = []

    # CTA keyword count
    cta_matches = _SPAM_CTA_RE.findall(bio)
    if cta_matches:
        cta_pts = min(40.0, len(cta_matches) * 20.0)
        score += cta_pts
        flags.append(f"CTA patterns detected ({len(cta_matches)})")

    # Hashtag density
    hashtags = _HASHTAG_RE.findall(bio)
    if len(hashtags) > 4:
        score += 20
        flags.append(f"excessive hashtags ({len(hashtags)})")

    # Bio composed almost entirely of hashtags and emojis (no real prose)
    if bio:
        bio_no_hashtags = _HASHTAG_RE.sub("", bio).strip()
        words = bio_no_hashtags.split()
        real_words = [w for w in words if w.isalpha() and len(w) > 1]
        if len(words) > 2 and len(real_words) / max(len(words), 1) < 0.25:
            score += 25
            flags.append("bio lacks real prose (mostly hashtags/emojis)")

    # Emoji density — count chars with Unicode category "So" or "Sm" (symbols)
    if bio:
        import unicodedata
        emoji_chars = sum(
            1 for c in bio
            if unicodedata.category(c) in ("So", "Sm", "Sk")
        )
        if len(bio) > 10 and emoji_chars / len(bio) > 0.30:
            score += 15
            flags.append(f"high emoji density ({emoji_chars}/{len(bio)} chars)")

    return min(100.0, score), flags
