"""
Clasificador de perfil de lead — primer paso del pipeline de scoring.

Detecta a cuál de los 6 perfiles de negocio pertenece un lead y devuelve
el RankingMode correspondiente. El score resultante es comparable entre
perfiles (0–100 unificado); el perfil es metadata para segmentar outreach.

Jerarquía de detección (en orden de prioridad):
  1. project_actor  — timing: señal de proyecto activo override todo
  2. buyer          — comprador directo con presupuesto propio
  3. specifier      — prescriptor profesional con clientes
  4. influencer     — autoridad en el ecosistema (alto reach + curaduría)
  5. gallery_node   — galería / plataforma / nodo de distribución
  6. aspirational   — ecosistema afín, sin señal de compra clara (default)

Referencias:
  weights_config.py — RankingMode enum y pesos por dimensión
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from scoring.weights_config import RankingMode


# ── Definición de perfiles ────────────────────────────────────────────────────

@dataclass(frozen=True)
class LeadProfile:
    key: str                # identificador interno
    label: str              # nombre corto para UI
    description: str        # descripción para el dashboard
    mode: RankingMode       # modo de scoring a aplicar
    priority: int           # orden de outreach (1 = máxima prioridad)


PROFILES: dict[str, LeadProfile] = {
    "project_actor": LeadProfile(
        key="project_actor",
        label="Proyecto activo",
        description="Involucrado en un proyecto en curso — hay timing real, oportunidad inmediata",
        mode=RankingMode.HOT_PROJECT_DETECTION,
        priority=1,
    ),
    "buyer": LeadProfile(
        key="buyer",
        label="Comprador directo",
        description="Puede comprar piezas para sí mismo o su espacio — venta directa potencial",
        mode=RankingMode.OUTREACH_PRIORITY,
        priority=2,
    ),
    "specifier": LeadProfile(
        key="specifier",
        label="Prescriptor",
        description="Decide qué arte/diseño se usa en proyectos de clientes — ventas recurrentes indirectas",
        mode=RankingMode.SPECIFIER_NETWORK,
        priority=3,
    ),
    "influencer": LeadProfile(
        key="influencer",
        label="Autoridad / Influencer",
        description="Amplifica visibilidad y abre puertas en el ecosistema — no compra directo",
        mode=RankingMode.AUTHORITY_FIRST,
        priority=4,
    ),
    "gallery_node": LeadProfile(
        key="gallery_node",
        label="Nodo del ecosistema",
        description="Galería, plataforma o actor de distribución — referencia, no comprador",
        mode=RankingMode.BRAND_RELEVANCE,
        priority=5,
    ),
    "aspirational": LeadProfile(
        key="aspirational",
        label="Ecosistema afín",
        description="Habita el mundo del arte/diseño sin señal de compra o prescripción clara",
        mode=RankingMode.PREMIUM_FIT_FIRST,
        priority=6,
    ),
}

DEFAULT_PROFILE = PROFILES["aspirational"]


# ── Señales por perfil ────────────────────────────────────────────────────────

# Señales de PROYECTO ACTIVO — override de cualquier otro perfil
_PROJECT_SIGNALS = re.compile(
    r"\bopening soon\b|\bnew project\b|\bunder construction\b|\brenovation\b"
    r"|\bfit.?out\b|\bunveiling\b|\ben obra\b|\bpr[oó]ximamente\b"
    r"|\bworking on\b|\bcurrently developing\b|\bin progress\b"
    r"|\bapertura\b|\bpróxima apertura\b|\bnuevo proyecto\b"
    r"|\binstallation in progress\b|\bmontaje\b|\brecien inaugurad\b",
    re.IGNORECASE,
)

# Señales de COMPRADOR DIRECTO
_BUYER_SIGNALS = re.compile(
    r"\bcollector\b|\bcoleccionista\b|\bprivate collection\b|\bcolecci[oó]n privada\b"
    r"|\bboutique hotel\b|\bhotel owner\b|\bdeveloper\b|\breal estate\b"
    r"|\binmobiliaria\b|\bdesarrollador\b|\bart acquisition\b"
    r"|\bhospitality owner\b|\brestaurant owner\b|\bprivate client\b"
    r"|\bluxury residential\b|\bpremium real estate\b|\bpatron\b"
    r"|\bdueño\b|\bpropietario\b|\bfundador\b|\bfounder\b",
    re.IGNORECASE,
)
_BUYER_LEAD_TYPES = frozenset(["coleccionista", "desarrollador", "hotel", "restaurante"])

# Señales de PRESCRIPTOR
_SPECIFIER_SIGNALS = re.compile(
    r"\binterior design(er|ers|ing|ismo)?\b|\barchitect(ure|ural)?\b"
    r"|\bart (consultant|advisor|consulting)\b"
    r"|\bhospitality design(er|ers|ing)?\b|\bproject sourcing\b"
    r"|\bart curation\b|\bspatial design\b|\binteriorista\b|\barquitecta?\b"
    r"|\bdise[ñn]o de interiores\b|\bdesign director\b|\bprocurement\b"
    r"|\bart director\b|\bcurador(a)?\b|\bcreative director\b"
    r"|\bdesign studio\b|\barchitecture studio\b|\bestudio de diseño\b",
    re.IGNORECASE,
)
_SPECIFIER_LEAD_TYPES = frozenset([
    "interiorista", "arquitecto", "curador", "diseñador", "estudio", "hospitality",
    "interior_designer", "architect", "curator", "art_advisor",
])

# Señales de INFLUENCER / AUTORIDAD
# Se activa cuando hay alto reach Y lenguaje curatorial/editorial
_INFLUENCER_SIGNALS = re.compile(
    r"\beditor(ial)?\b|\bcurated by\b|\bdesign media\b|\bdesign press\b"
    r"|\bcritic\b|\bauthor\b|\bwriter\b|\bpublicist\b|\bpublication\b"
    r"|\bpodcast\b|\binfluen(cer|cia)\b|\bthought leader\b|\bspeaker\b",
    re.IGNORECASE,
)
_INFLUENCER_MIN_FOLLOWERS = 30_000  # umbral de reach para ser "autoridad"

# Señales de GALERÍA / NODO DEL ECOSISTEMA
_GALLERY_SIGNALS = re.compile(
    r"\bgaller(y|ies|ie)\b|\bgaler[ií]a\b|\bgalerie\b"
    r"|\bart fair\b|\bdesign fair\b|\bferia de arte\b"
    r"|\bartist representation\b|\bart program\b|\bart space\b"
    r"|\bexhibition space\b|\bculture (center|centre)\b|\bmuseo\b|\bmuseum\b"
    r"|\binstitut(e|ion|o)\b|\bfoundation\b|\bfundaci[oó]n\b"
    r"|\bdesign week\b|\bart week\b|\bbiennale\b|\bbiennial\b",
    re.IGNORECASE,
)
_GALLERY_LEAD_TYPES = frozenset(["galeria", "gallery_director"])


# ── Lógica de detección ───────────────────────────────────────────────────────

def _follower_count(followers_str: str) -> int:
    """Convierte el string de followers (ej. '22K', '1.2M', '45000') a int."""
    if not followers_str:
        return 0
    s = str(followers_str).strip().upper().replace(",", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except (ValueError, AttributeError):
        return 0


def detect_profile(
    bio: str = "",
    name: str = "",
    category: str = "",
    lead_type: str = "",
    followers: str = "",
    interest_signals: list[str] | None = None,
) -> LeadProfile:
    """Detecta el perfil de negocio de un lead a partir de sus señales de texto.

    La detección sigue la jerarquía: project_actor > buyer > specifier >
    influencer > gallery_node > aspirational.

    Parámetros
    ----------
    bio, name, category : texto del perfil (se concatenan para análisis)
    lead_type           : clasificación existente del clasificador de tipos
    followers           : string con conteo de seguidores ("22K", "1.2M", etc.)
    interest_signals    : lista de señales detectadas previamente

    Retorna
    -------
    LeadProfile del perfil detectado.
    """
    # Texto unificado para detección de señales
    text = f"{bio} {name} {category}".strip()
    signals_text = " ".join(interest_signals or [])
    full_text = f"{text} {signals_text}"

    # ── 1. Proyecto activo (override) ─────────────────────────────────────────
    if _PROJECT_SIGNALS.search(full_text):
        return PROFILES["project_actor"]

    # ── 2. Comprador directo ──────────────────────────────────────────────────
    if lead_type in _BUYER_LEAD_TYPES or _BUYER_SIGNALS.search(full_text):
        return PROFILES["buyer"]

    # ── 3. Prescriptor ────────────────────────────────────────────────────────
    if lead_type in _SPECIFIER_LEAD_TYPES or _SPECIFIER_SIGNALS.search(full_text):
        return PROFILES["specifier"]

    # ── 4. Influencer / Autoridad ─────────────────────────────────────────────
    # Requiere reach alto + señal editorial/curatorial
    n_followers = _follower_count(followers)
    if n_followers >= _INFLUENCER_MIN_FOLLOWERS and _INFLUENCER_SIGNALS.search(full_text):
        return PROFILES["influencer"]
    # Solo reach muy alto sin señal editorial también cuenta (medios/referentes)
    if n_followers >= 100_000:
        return PROFILES["influencer"]

    # ── 5. Galería / Nodo del ecosistema ──────────────────────────────────────
    if lead_type in _GALLERY_LEAD_TYPES or _GALLERY_SIGNALS.search(full_text):
        return PROFILES["gallery_node"]

    # ── 6. Aspirational (default) ─────────────────────────────────────────────
    return PROFILES["aspirational"]


def detect_profile_from_lead(lead) -> LeadProfile:
    """Wrapper que acepta un objeto Lead directamente."""
    return detect_profile(
        bio=getattr(lead, "bio", "") or "",
        name=getattr(lead, "name", "") or "",
        category=getattr(lead, "category", "") or "",
        lead_type=getattr(lead, "lead_type", "") or "",
        followers=str(getattr(lead, "followers", "") or ""),
        interest_signals=getattr(lead, "interest_signals", None) or [],
    )
