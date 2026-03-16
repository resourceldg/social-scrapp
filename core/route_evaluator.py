"""
RouteEvaluator — scores, validates and prioritizes scraping routes.

Responsibilities:
- Persist per-(platform, route_pattern) success/failure counters in SQLite.
- Compute a stability_score [0.0 – 1.0] per route.
- Sanitize Instagram hashtags for safe URL construction.
- Generate prioritized candidate routes for each platform/keyword combo.
- Identify penalized (consistently failing) routes so scrapers can skip them.

The stability score combines:
  raw_success_rate × confidence_factor
where confidence grows with sample count (reaches 1.0 at 20+ samples).
Unknown routes start at 0.65 (neutral — try them, but don't over-trust).
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unicodedata import normalize as unic_normalize

logger = logging.getLogger(__name__)

# Routes with stability_score below this are "penalized" (skip unless no alternative)
_PENALIZED_THRESHOLD = 0.25
# Minimum samples required before penalizing a route
_MIN_SAMPLES_TO_PENALIZE = 6
# Initial score for unknown routes
_UNKNOWN_SCORE = 0.65


@dataclass
class RouteCandidate:
    """A candidate URL to try for a given platform+keyword, with metadata."""

    url: str
    pattern: str          # abstract identifier for DB tracking, e.g. "instagram/hashtag"
    priority: int         # 1 = try first (lower = higher priority)
    stability_score: float
    reason: str           # human-readable why this route was selected

    def __lt__(self, other: "RouteCandidate") -> bool:
        # Sort ascending by priority, then descending by score
        return (self.priority, -self.stability_score) < (other.priority, -other.stability_score)


class RouteEvaluator:
    """
    Evaluates and prioritises scraping routes, learning from observed outcomes.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    # ── DB plumbing ───────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS route_stats (
                    pattern     TEXT NOT NULL,
                    platform    TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    updated_at  TEXT NOT NULL,
                    PRIMARY KEY (pattern, platform)
                )
                """
            )

    # ── Recording outcomes ────────────────────────────────────────────────────

    def record_success(self, platform: str, pattern: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO route_stats (pattern, platform, success_count, last_success_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(pattern, platform) DO UPDATE SET
                    success_count   = success_count + 1,
                    last_success_at = excluded.last_success_at,
                    updated_at      = excluded.updated_at
                """,
                (pattern, platform, now, now),
            )

    def record_failure(self, platform: str, pattern: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO route_stats (pattern, platform, failure_count, last_failure_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(pattern, platform) DO UPDATE SET
                    failure_count   = failure_count + 1,
                    last_failure_at = excluded.last_failure_at,
                    updated_at      = excluded.updated_at
                """,
                (pattern, platform, now, now),
            )

    # ── Scoring ───────────────────────────────────────────────────────────────

    def stability_score(self, platform: str, pattern: str) -> float:
        """
        Returns [0.0, 1.0]. Unknown routes → _UNKNOWN_SCORE.
        Formula: raw_success_rate × (0.4 + 0.6 × confidence)
        where confidence = min(total_samples / 20, 1.0)
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT success_count, failure_count FROM route_stats WHERE pattern=? AND platform=?",
                (pattern, platform),
            ).fetchone()

        if not row:
            return _UNKNOWN_SCORE

        total = row["success_count"] + row["failure_count"]
        if total == 0:
            return _UNKNOWN_SCORE

        raw_rate = row["success_count"] / total
        confidence = min(total / 20.0, 1.0)
        return raw_rate * (0.4 + 0.6 * confidence)

    def penalized_patterns(self, platform: str) -> frozenset[str]:
        """Return route patterns that are consistently failing (skip these)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT pattern, success_count, failure_count
                FROM route_stats
                WHERE platform = ?
                  AND (success_count + failure_count) >= ?
                """,
                (platform, _MIN_SAMPLES_TO_PENALIZE),
            ).fetchall()

        bad: set[str] = set()
        for row in rows:
            total = row["success_count"] + row["failure_count"]
            score = row["success_count"] / total if total > 0 else 0.0
            if score < _PENALIZED_THRESHOLD:
                bad.add(row["pattern"])
        return frozenset(bad)

    # ── Instagram-specific ────────────────────────────────────────────────────

    @staticmethod
    def sanitize_hashtag(raw: str) -> str | None:
        """
        Normalize and sanitize a hashtag for safe Instagram URL use.

        Steps:
          1. Strip leading '#' and whitespace.
          2. Unicode NFC normalization.
          3. Remove characters that break Instagram hashtag URLs.
          4. Validate length and structure.

        Returns the clean tag string, or None if the tag is unusable.
        """
        tag = raw.lstrip("#").strip()
        if not tag:
            return None

        # Unicode normalization: compose characters
        tag = unic_normalize("NFC", tag)

        # Remove anything that is not a letter (including accented), digit, or underscore.
        # Instagram allows unicode letters (é, ñ, 中文…) but not spaces, hyphens, dots, etc.
        tag = re.sub(r"[\s\-\.\'\"\(\)\[\]{},;:!?@#$%&*+=<>/\\|~^`]", "", tag)

        if not tag:
            return None

        # Must start with a letter or digit (not underscore)
        if not re.match(r"^[a-zA-Z0-9\u00C0-\u024F\u4e00-\u9fff]", tag):
            return None

        # Instagram hashtags: max 100 chars
        if len(tag) > 100:
            tag = tag[:100]

        return tag

    def instagram_route_candidates(self, keyword: str) -> list[RouteCandidate]:
        """
        Return prioritized candidate routes for an Instagram keyword, from most
        stable/public to least.

        Route priority ladder:
          1. Hashtag explore page (clean tag, public, stable when tag is valid)
          2. Hashtag explore page with original raw encoding (fallback if clean differs)
          3. Plain text search (less stable, but broadens coverage)

        Routes with penalized patterns are demoted to priority 99.
        """
        penalized = self.penalized_patterns("instagram")
        candidates: list[RouteCandidate] = []
        base = "https://www.instagram.com"

        # ── Candidate 1: clean sanitized hashtag ─────────────────────────────
        clean_tag = self.sanitize_hashtag(keyword)
        if clean_tag:
            pattern = f"instagram/hashtag/{clean_tag}"
            score = self.stability_score("instagram", pattern)
            priority = 99 if pattern in penalized else 1
            candidates.append(
                RouteCandidate(
                    url=f"{base}/explore/tags/{clean_tag}/",
                    pattern=pattern,
                    priority=priority,
                    stability_score=score,
                    reason=f"hashtag:{clean_tag}",
                )
            )

        # ── Candidate 2: URL-safe keyword without # (if different from clean_tag) ─
        raw_slug = re.sub(r"\s+", "", keyword.lstrip("#").lower())
        raw_slug = re.sub(r"[^a-z0-9_\u00C0-\u024F]", "", raw_slug)
        if raw_slug and raw_slug != clean_tag and len(raw_slug) >= 2:
            pattern = f"instagram/hashtag/{raw_slug}"
            score = self.stability_score("instagram", pattern)
            priority = 99 if pattern in penalized else 2
            candidates.append(
                RouteCandidate(
                    url=f"{base}/explore/tags/{raw_slug}/",
                    pattern=pattern,
                    priority=priority,
                    stability_score=score,
                    reason=f"hashtag_raw:{raw_slug}",
                )
            )

        # ── Candidate 3: plain-text web search (public, no auth required) ────
        from urllib.parse import quote as _quote

        search_kw = keyword.lstrip("#").strip()
        pattern = "instagram/web_search"
        score = self.stability_score("instagram", pattern)
        priority = 99 if pattern in penalized else 3
        # Instagram doesn't offer a real text search on the public web.
        # Best available: explore top content for the tag (if sanitized) or skip.
        # We record the pattern for tracking but only include if we have nothing else.
        if not candidates:
            candidates.append(
                RouteCandidate(
                    url=f"{base}/explore/tags/{_quote(search_kw)}/",
                    pattern=pattern,
                    priority=priority,
                    stability_score=score,
                    reason=f"explore_encoded:{search_kw}",
                )
            )

        # Remove duplicates by URL and sort
        seen_urls: set[str] = set()
        unique: list[RouteCandidate] = []
        for c in sorted(candidates):
            if c.url not in seen_urls:
                seen_urls.add(c.url)
                unique.append(c)

        return unique

    def platform_route_candidates(
        self, platform: str, keyword: str
    ) -> list[RouteCandidate]:
        """
        Generic candidate builder for non-Instagram platforms.
        Each platform has one primary route pattern; this records and scores it.
        """
        from urllib.parse import quote as _quote

        penalized = self.penalized_patterns(platform)
        base_routes: dict[str, str] = {
            "facebook": f"https://www.facebook.com/search/pages/?q={_quote(keyword)}",
            "linkedin": f"https://www.linkedin.com/search/results/all/?keywords={_quote(keyword)}",
            "pinterest": f"https://www.pinterest.com/search/users/?q={_quote(keyword)}",
            "reddit": f"https://www.reddit.com/search/?q={_quote(keyword)}&type=sr,user",
            "twitter": f"https://x.com/search?q={_quote(keyword)}&src=typed_query&f=user",
        }

        url = base_routes.get(platform, "")
        if not url:
            return []

        pattern = f"{platform}/search"
        score = self.stability_score(platform, pattern)
        priority = 99 if pattern in penalized else 1

        return [
            RouteCandidate(
                url=url,
                pattern=pattern,
                priority=priority,
                stability_score=score,
                reason=f"search:{keyword[:30]}",
            )
        ]

    # ── Reporting ─────────────────────────────────────────────────────────────

    def report(self, platform: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM route_stats WHERE platform=? ORDER BY updated_at DESC",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM route_stats ORDER BY platform, success_count DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def log_report(self, logger_: logging.Logger | None = None) -> None:
        _log = logger_ or logger
        rows = self.report()
        if not rows:
            _log.info("RouteEvaluator: no route data yet.")
            return
        _log.info("==== Route Stability Report (%d patterns) ====", len(rows))
        for r in rows:
            total = r["success_count"] + r["failure_count"]
            rate = r["success_count"] / total if total > 0 else 0.0
            score = self.stability_score(r["platform"], r["pattern"])
            _log.info(
                "  [%s] %-45s  ok=%d  fail=%d  rate=%.0f%%  score=%.2f",
                r["platform"],
                r["pattern"],
                r["success_count"],
                r["failure_count"],
                rate * 100,
                score,
            )
