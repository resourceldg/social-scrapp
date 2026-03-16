"""
R16 — Multilingual semantic relevance scoring.

Computes cosine similarity between the lead's bio/category text and a set of
reference sentences that describe the ideal customer profile (ICP). Works
across Spanish, English, and Portuguese without language-specific tuning.

Requires the optional ``sentence-transformers`` package.  When the package is
absent the module degrades gracefully: ``semantic_boost()`` returns 0.0 and a
warning is logged on first call (not on every call, to avoid log spam).

Install
-------
    pip install sentence-transformers

The recommended model is ``paraphrase-multilingual-MiniLM-L12-v2`` (~120 MB).
On first use the model is downloaded to the HuggingFace cache (~/.cache/huggingface).

Architecture
------------
``SemanticRelevanceScorer`` is a singleton that initialises the model once and
caches lead-text embeddings to avoid redundant forward passes.

The scorer is consumed by ``score_relevance()`` in ``base_scoring.py`` — it
adds up to +20 pts on top of the keyword score when the lead bio is semantically
close to the ICP reference set (threshold configurable, default cosine ≥ 0.55).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── ICP reference sentences ─────────────────────────────────────────────────────
# These describe the ideal lead for a high-end art/design/furniture brand.
# Multilingual (ES / EN / PT-BR) to maximise recall on regional markets.
_ICP_REFERENCES: list[str] = [
    # English
    "luxury interior design studio specializing in high-end residential projects",
    "architect working on boutique hotel and hospitality design projects",
    "art consultant and curator for private collectors and galleries",
    "furniture designer creating bespoke handcrafted collectible pieces",
    "interior architecture firm sourcing exclusive furniture and art",
    "gallery director representing contemporary and collectible design",
    "real estate developer focused on premium residential developments",
    "hospitality designer specifying FF&E for luxury hotel projects",
    # Spanish
    "estudio de interiorismo especializado en proyectos residenciales de alto nivel",
    "arquitecto trabajando en proyectos hoteleros y de hospitalidad boutique",
    "asesor de arte y curador para coleccionistas privados y galerías",
    "diseñador de muebles bespoke artesanales y piezas de colección",
    "despacho de arquitectura de interiores buscando mobiliario exclusivo",
    "director de galería de arte contemporáneo y diseño coleccionable",
    "promotor inmobiliario de proyectos residenciales premium",
    "diseñador de hospitalidad especificando FF&E para proyectos hoteleros de lujo",
    # Portuguese (PT-BR)
    "estúdio de design de interiores especializado em projetos residenciais de alto padrão",
    "arquiteto trabalhando em projetos de hotel boutique e hospitalidade",
    "consultor e curador de arte para colecionadores particulares e galerias",
    "designer de móveis bespoke artesanais e peças colecionáveis",
    "galeria de arte contemporânea e design colecionável",
    "incorporadora imobiliária focada em empreendimentos residenciais premium",
]

# Minimum cosine similarity to qualify for a semantic boost
_SIMILARITY_THRESHOLD = 0.55

# Maximum bonus points added to relevance score
_MAX_BOOST = 20.0

# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: "SemanticRelevanceScorer | None" = None
_warned_unavailable = False


def get_scorer() -> "SemanticRelevanceScorer | None":
    """Return the singleton scorer, or None if sentence-transformers is unavailable."""
    global _instance, _warned_unavailable
    if _instance is not None:
        return _instance
    try:
        _instance = SemanticRelevanceScorer()
        return _instance
    except ImportError:
        if not _warned_unavailable:
            logger.info(
                "sentence-transformers not installed — semantic relevance boost disabled. "
                "Install with: pip install sentence-transformers"
            )
            _warned_unavailable = True
        return None
    except Exception as exc:
        if not _warned_unavailable:
            logger.warning("SemanticRelevanceScorer init failed: %s", exc)
            _warned_unavailable = True
        return None


def semantic_boost(text: str) -> tuple[float, str]:
    """
    Return a relevance boost (0 – _MAX_BOOST) based on semantic similarity
    to the ICP reference set.

    Parameters
    ----------
    text : bio + category + other lead text (lower-cased recommended)

    Returns
    -------
    (boost, reason)
        boost  : 0.0 if model unavailable or below threshold
        reason : human-readable string for ``reasons`` list (empty if boost == 0)
    """
    if not text or not text.strip():
        return 0.0, ""
    scorer = get_scorer()
    if scorer is None:
        return 0.0, ""
    return scorer.compute_boost(text)


# ── Core class ────────────────────────────────────────────────────────────────

class SemanticRelevanceScorer:
    """
    Wraps a SentenceTransformer model and computes ICP similarity boosts.

    Parameters
    ----------
    model_name : HuggingFace model ID.
                 ``paraphrase-multilingual-MiniLM-L12-v2`` is recommended:
                 fast (12-layer MiniLM), supports 50+ languages, 120 MB download.
    threshold  : minimum cosine similarity to return a non-zero boost
    max_boost  : maximum additional points (linearly scaled by similarity)
    """

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        threshold: float = _SIMILARITY_THRESHOLD,
        max_boost: float = _MAX_BOOST,
    ) -> None:
        # ImportError propagates to get_scorer() which catches it gracefully
        from sentence_transformers import SentenceTransformer, util as st_util  # type: ignore[import]
        self._model = SentenceTransformer(model_name)
        self._util = st_util
        self.threshold = threshold
        self.max_boost = max_boost

        # Pre-compute ICP reference embeddings once at init
        self._ref_embeddings = self._model.encode(
            _ICP_REFERENCES, convert_to_tensor=True, show_progress_bar=False
        )
        logger.info(
            "SemanticRelevanceScorer ready — model=%s, references=%d",
            model_name,
            len(_ICP_REFERENCES),
        )

    def compute_boost(self, text: str) -> tuple[float, str]:
        """
        Compute the semantic boost for a single lead text string.

        Uses LRU-cached embedding to avoid re-encoding identical texts
        (e.g. the same lead enriched multiple times within a session).
        """
        embedding = self._encode_cached(text[:1000])  # cap input length
        similarities = self._util.cos_sim(embedding, self._ref_embeddings)[0]
        best_sim = float(similarities.max())

        if best_sim < self.threshold:
            return 0.0, ""

        # Linear scale: threshold → 0 pts, 1.0 → max_boost pts
        boost = self.max_boost * (best_sim - self.threshold) / (1.0 - self.threshold)
        boost = round(min(boost, self.max_boost), 1)
        return boost, f"semantic similarity: {best_sim:.2f}"

    @lru_cache(maxsize=512)
    def _encode_cached(self, text: str):
        return self._model.encode(text, convert_to_tensor=True, show_progress_bar=False)
