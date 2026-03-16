"""
Threshold tables and the follower-string parser.

All bucket lists are sorted descending by threshold so the first matching
entry wins (highest applicable tier).
"""
from __future__ import annotations

import re

# ── Follower / subscriber buckets ─────────────────────────────────────────────
# Each entry: (minimum_count, points_awarded)

# Used by instagram_scoring for the platform_specific dimension
INSTAGRAM_FOLLOWER_BUCKETS: list[tuple[int, int]] = [
    (100_000, 25),
    (50_000, 20),
    (10_000, 15),
    (5_000, 10),
    (1_000, 5),
    (0, 2),
]

# Used by base authority scoring and generic platforms
GENERIC_FOLLOWER_BUCKETS: list[tuple[int, int]] = [
    (1_000_000, 100),
    (500_000, 90),
    (100_000, 75),
    (50_000, 60),
    (10_000, 40),
    (5_000, 25),
    (1_000, 15),
    (500, 10),
    (100, 5),
    (0, 0),
]

# Used by reddit_scoring for subreddit subscribers
REDDIT_SUBSCRIBER_BUCKETS: list[tuple[int, int]] = [
    (100_000, 25),
    (50_000, 15),
    (10_000, 10),
    (1_000, 5),
    (0, 0),
]

# ── LinkedIn seniority tiers ───────────────────────────────────────────────────
# Each entry: (list_of_keywords_to_match, points)
# Evaluated top-to-bottom; only the first matching tier is applied.
LINKEDIN_SENIORITY: list[tuple[list[str], int]] = [
    (["ceo", "chief executive", "founder", "co-founder", "cofunder"], 22),
    (["partner", "managing director", "managing partner"], 20),
    (["head of", "vp ", "vice president", "chief "], 18),
    (["director"], 15),
    (["manager", "gerente"], 8),
    (["senior", "lead "], 5),
]

# ── Follower-string parser ─────────────────────────────────────────────────────

# Suffix must not be followed by another word character so "karma"/"million"/etc.
# are not mistaken for the K/M/B multiplier suffix.
_PARSE_RE = re.compile(r"([\d][,\d\.]*[\d]?)\s*([KkMmBb](?!\w))?", re.IGNORECASE)
_SUFFIX_MAP = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_followers(followers_str: str) -> int:
    """
    Convert a human-readable follower string to an integer count.

    Examples
    --------
    >>> parse_followers("2.5K")
    2500
    >>> parse_followers("45M")
    45000000
    >>> parse_followers("1,234")
    1234
    >>> parse_followers("12500 karma")
    12500
    >>> parse_followers("")
    0
    """
    if not followers_str:
        return 0
    m = _PARSE_RE.search(followers_str.strip())
    if not m:
        return 0
    num_str = m.group(1).replace(",", "")
    suffix = (m.group(2) or "").upper()
    try:
        num = float(num_str)
    except ValueError:
        return 0
    return int(num * _SUFFIX_MAP.get(suffix, 1))


def follower_score(followers_str: str, buckets: list[tuple[int, int]]) -> int:
    # Empty/unknown follower data means "no information", not "zero followers".
    # Return 0 so leads without follower data don't accidentally match the
    # lowest bucket (which may award points for 0 followers).
    if not followers_str or not followers_str.strip():
        return 0
    """
    Map a follower string to a point value using a bucket table.

    Parameters
    ----------
    followers_str : str
        Raw followers field value (e.g. "2.5K", "45M").
    buckets : list of (threshold, points)
        Sorted descending. First matching threshold wins.

    Returns
    -------
    int
        Points from the first matching bucket, or 0 if below all thresholds.
    """
    count = parse_followers(followers_str)
    for threshold, points in buckets:
        if count >= threshold:
            return points
    return 0
