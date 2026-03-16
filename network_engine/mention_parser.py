"""
MentionParser — extracts relationship signals from lead bio and raw_data text.

For each lead it detects:
  - @handle mentions → possible MENTIONED_WITH or COLLABORATES_WITH relationships
  - "designed by X" / "in collaboration with X" → DESIGNED_BY / COLLABORATES_WITH
  - "for @hotel / @brand" → WORKS_ON project signal
  - "presented by / curated by X" → FEATURES / DESIGNED_BY

Each raw mention becomes a RawMention with:
  - target_handle  (the referenced person/brand)
  - relation_type  (MENTIONED_WITH | COLLABORATES_WITH | DESIGNED_BY | WORKS_ON | FEATURES)
  - confidence     (0.0–1.0)
  - evidence_text  (bio excerpt)

Usage
-----
    from network_engine.mention_parser import parse_mentions
    results = parse_mentions(lead)
    for m in results:
        print(m.target_handle, m.relation_type, m.confidence)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import Lead


# ── Relation patterns ──────────────────────────────────────────────────────────

# Direct @handle extraction
_AT_HANDLE_RE = re.compile(r"@([\w.]+)", re.UNICODE)

# Email/domain blocklist — these are not social handles
_EMAIL_DOMAINS: frozenset = frozenset({
    "gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "icloud.com",
    "live.com", "me.com", "mac.com", "protonmail.com", "aol.com",
    "msn.com", "googlemail.com", "ymail.com", "inbox.com",
})
# Handles that are clearly not social accounts (contain a dot + known TLD)
_TLD_RE = re.compile(r"\.(com|net|org|io|co|ly|me|tv|co\.uk|es|fr|de|it)$", re.IGNORECASE)


def _is_invalid_handle(handle: str) -> bool:
    """Return True if the handle looks like an email domain or URL fragment."""
    if handle in _EMAIL_DOMAINS:
        return True
    if _TLD_RE.search(handle):
        return True
    if len(handle) < 2 or len(handle) > 40:
        return True
    return False

# Collaboration signal — strong evidence of COLLABORATES_WITH
_COLLAB_PATTERNS = re.compile(
    r"\b(in collaboration with|collaboration with|collab with|partnering with"
    r"|in partnership with|working with|team with|junto a|colaboración con"
    r"|en colaboración con|con el equipo de|con @|junto con @)\b",
    re.IGNORECASE,
)

# Design / authorship signal — strong evidence of DESIGNED_BY
_DESIGNED_BY_PATTERNS = re.compile(
    r"\b(designed by|interior by|architecture by|curated by|art direction by"
    r"|directed by|created by|conceived by|spaces by|interiors by"
    r"|diseño de|arquitectura de|interiorismo de|curado por|diseñado por"
    r"|dirigido por|realizado por|proyecto de|obra de)\b",
    re.IGNORECASE,
)

# Project / client reference — WORKS_ON
_WORKS_ON_PATTERNS = re.compile(
    r"\b(for @|working for|project for|client:|cliente:|for the|para el|para la"
    r"|commissioned by|encargo de|para @)\b",
    re.IGNORECASE,
)

# Feature / exhibition — FEATURES
_FEATURES_PATTERNS = re.compile(
    r"\b(presented by|featured by|represented by|showing with|exhibited with"
    r"|published in|as seen in|press in|featured in @|presentado por)\b",
    re.IGNORECASE,
)


def _get_context(text: str, match_start: int, match_end: int, window: int = 80) -> str:
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    return text[start:end].strip()


@dataclass
class MentionResult:
    """A single detected relationship mention in a lead's profile data."""
    source_handle: str            # the lead's own handle
    target_handle: str            # the mentioned handle (without @)
    relation_type: str            # COLLABORATES_WITH | DESIGNED_BY | WORKS_ON | MENTIONED_WITH | FEATURES
    confidence: float             # 0.0–1.0
    evidence_text: str
    source_platform: str = ""


def parse_mentions(lead: Lead) -> list[MentionResult]:
    """
    Extract all relationship mentions from a lead's bio and raw_data.

    Parameters
    ----------
    lead : Lead

    Returns
    -------
    list[MentionResult]
        Empty if no mentions found. Deduplicated by (target_handle, relation_type).
    """
    text_parts = [lead.bio or "", lead.category or ""]
    if isinstance(lead.raw_data, dict):
        for k in ("caption", "captions", "post_text", "description", "about"):
            v = lead.raw_data.get(k)
            if isinstance(v, str):
                text_parts.append(v)
            elif isinstance(v, list):
                text_parts.extend(str(x) for x in v)

    full_text = " ".join(t for t in text_parts if t)
    if not full_text:
        return []

    source_handle = lead.social_handle or lead.name or ""
    platform = lead.source_platform or ""
    results: list[MentionResult] = []
    seen: set[tuple[str, str]] = set()   # (target, relation_type)

    # ── Pass 1: scan for strong relation patterns first ────────────────────────
    # For each strong pattern, find @handles in the vicinity (±60 chars)
    def _extract_near_handles(text: str, pos: int, window: int = 80) -> list[str]:
        start = max(0, pos - 20)
        end = min(len(text), pos + window)
        return _AT_HANDLE_RE.findall(text[start:end])

    for pattern, rel_type, conf in [
        (_COLLAB_PATTERNS,    "COLLABORATES_WITH", 0.80),
        (_DESIGNED_BY_PATTERNS, "DESIGNED_BY",     0.85),
        (_WORKS_ON_PATTERNS,  "WORKS_ON",          0.70),
        (_FEATURES_PATTERNS,  "FEATURES",          0.65),
    ]:
        for m in pattern.finditer(full_text):
            handles = _extract_near_handles(full_text, m.start())
            for handle in handles:
                handle_clean = handle.lower().strip("._")
                if not handle_clean or handle_clean == source_handle.lower():
                    continue
                if _is_invalid_handle(handle_clean):
                    continue
                key = (handle_clean, rel_type)
                if key in seen:
                    continue
                seen.add(key)
                results.append(MentionResult(
                    source_handle=source_handle,
                    target_handle=handle_clean,
                    relation_type=rel_type,
                    confidence=conf,
                    evidence_text=_get_context(full_text, m.start(), m.end()),
                    source_platform=platform,
                ))

    # ── Pass 2: bare @mentions not already captured ────────────────────────────
    for m in _AT_HANDLE_RE.finditer(full_text):
        handle_clean = m.group(1).lower().strip("._")
        if not handle_clean or handle_clean == source_handle.lower():
            continue
        if _is_invalid_handle(handle_clean):
            continue
        # Skip if already captured with a stronger relation type
        if any(handle_clean == r.target_handle for r in results):
            continue
        key = (handle_clean, "MENTIONED_WITH")
        if key in seen:
            continue
        seen.add(key)
        results.append(MentionResult(
            source_handle=source_handle,
            target_handle=handle_clean,
            relation_type="MENTIONED_WITH",
            confidence=0.45,    # lower — bare mention, no relational context
            evidence_text=_get_context(full_text, m.start(), m.end()),
            source_platform=platform,
        ))

    return results
