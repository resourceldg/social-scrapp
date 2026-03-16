"""
Fase 3 tests — URL reachability check + conversion feedback loop.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from feedback.feedback_store import FeedbackStore
from feedback.feedback_analyzer import analyze_conversions
from utils.helpers import check_url_reachable


# ── check_url_reachable ────────────────────────────────────────────────────────

class TestCheckUrlReachable:
    def test_empty_url_returns_false(self):
        assert check_url_reachable("") is False

    def test_none_like_empty_returns_false(self):
        assert check_url_reachable("   ") is False

    def test_social_domain_always_true(self):
        # Social domains skip the HTTP check and return True unconditionally
        for url in [
            "https://www.instagram.com/studiodesign",
            "https://linkedin.com/company/acme",
            "https://twitter.com/handle",
            "https://pinterest.com/user",
            "https://reddit.com/r/art",
            "https://facebook.com/page",
        ]:
            assert check_url_reachable(url) is True, f"Expected True for {url}"

    def test_reachable_non_social_url(self):
        # Mock urlopen to return a 200 response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("utils.helpers.urllib.request.urlopen", return_value=mock_resp):
            assert check_url_reachable("https://example.com/portfolio") is True

    def test_404_non_social_url_returns_false(self):
        import urllib.error
        with patch(
            "utils.helpers.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None),
        ):
            assert check_url_reachable("https://example.com/gone") is False

    def test_500_returns_false(self):
        import urllib.error
        with patch(
            "utils.helpers.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(None, 500, "Server Error", {}, None),
        ):
            assert check_url_reachable("https://example.com/broken") is False

    def test_connection_error_returns_false(self):
        with patch(
            "utils.helpers.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            assert check_url_reachable("https://dead.example.com/") is False

    def test_301_redirect_treated_as_reachable(self):
        """3xx HTTPError (rare) treated as reachable since < 400."""
        import urllib.error
        with patch(
            "utils.helpers.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(None, 301, "Moved", {}, None),
        ):
            assert check_url_reachable("https://example.com/old") is True


# ── FeedbackStore ──────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_leads.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY,
            profile_url TEXT UNIQUE,
            score INTEGER,
            lead_type TEXT,
            source_platform TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    # Initialize FeedbackStore to create the conversions table
    FeedbackStore(db)
    return db


@pytest.fixture()
def store(tmp_db: Path) -> FeedbackStore:
    return FeedbackStore(tmp_db)


class TestFeedbackStore:
    def test_mark_converted(self, store: FeedbackStore):
        store.mark_converted("https://instagram.com/studioA")
        outcomes = store.get_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == "converted"

    def test_mark_disqualified(self, store: FeedbackStore):
        store.mark_disqualified("https://instagram.com/spammer")
        assert store.get_disqualified() == ["https://instagram.com/spammer"]

    def test_update_outcome(self, store: FeedbackStore):
        store.mark_converted("https://instagram.com/studioA")
        store.mark_disqualified("https://instagram.com/studioA")
        outcomes = store.get_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == "disqualified"

    def test_invalid_outcome_raises(self, store: FeedbackStore):
        with pytest.raises(ValueError):
            store.mark_outcome("https://example.com", "maybe")

    def test_delete_outcome(self, store: FeedbackStore):
        store.mark_converted("https://instagram.com/del")
        store.delete_outcome("https://instagram.com/del")
        assert store.get_outcomes() == []

    def test_outcome_counts(self, store: FeedbackStore):
        store.mark_converted("https://a.com")
        store.mark_converted("https://b.com")
        store.mark_disqualified("https://c.com")
        counts = store.outcome_counts()
        assert counts["converted"] == 2
        assert counts["disqualified"] == 1
        assert counts["total"] == 3

    def test_get_converted(self, store: FeedbackStore):
        store.mark_converted("https://a.com")
        store.mark_disqualified("https://b.com")
        assert store.get_converted() == ["https://a.com"]

    def test_notes_persisted(self, store: FeedbackStore):
        store.mark_converted("https://a.com", notes="Closed deal")
        outcome = store.get_outcomes()[0]
        assert outcome["notes"] == "Closed deal"


# ── FeedbackAnalyzer ───────────────────────────────────────────────────────────

class TestFeedbackAnalyzer:
    def test_empty_db_returns_insufficient(self, tmp_db: Path):
        result = analyze_conversions(tmp_db)
        assert result["insufficient_data"] is True
        assert result["sample_size"] == 0

    def _seed(self, tmp_db: Path, entries: list[dict]) -> None:
        """Seed the leads and conversions tables."""
        conn = sqlite3.connect(tmp_db)
        for e in entries:
            conn.execute(
                "INSERT OR IGNORE INTO leads (profile_url, score, lead_type, source_platform) VALUES (?, ?, ?, ?)",
                (e["url"], e["score"], e.get("lead_type", "architect"), e.get("platform", "instagram")),
            )
            conn.execute(
                "INSERT OR REPLACE INTO conversions (profile_url, outcome, marked_at, notes) VALUES (?, ?, ?, ?)",
                (e["url"], e["outcome"], "2026-01-01T00:00:00", ""),
            )
        conn.commit()
        conn.close()

    def test_insufficient_data_below_threshold(self, tmp_db: Path):
        self._seed(tmp_db, [
            {"url": "https://a.com", "score": 70, "outcome": "converted"},
            {"url": "https://b.com", "score": 30, "outcome": "disqualified"},
        ])
        result = analyze_conversions(tmp_db)
        # 2 total < _MIN_SAMPLE (3) → insufficient
        assert result["insufficient_data"] is True

    def test_calibration_analysis_sufficient_data(self, tmp_db: Path):
        self._seed(tmp_db, [
            {"url": "https://a.com", "score": 80, "outcome": "converted"},
            {"url": "https://b.com", "score": 70, "outcome": "converted"},
            {"url": "https://c.com", "score": 20, "outcome": "disqualified"},
            {"url": "https://d.com", "score": 25, "outcome": "disqualified"},
        ])
        result = analyze_conversions(tmp_db)
        assert not result.get("insufficient_data")
        assert result["converted_count"] == 2
        assert result["disqualified_count"] == 2
        assert result["avg_score_converted"] == 75.0
        assert result["avg_score_disqualified"] == 22.5
        assert result["score_separation"] == 52.5

    def test_precision_by_band(self, tmp_db: Path):
        # Scores 82 and 90 → 81–100 band (converted only → precision 1.0)
        # Score 75 → 61–80 band (disqualified only → precision 0.0)
        # Score 10 → 0–20 band (disqualified only → precision 0.0)
        self._seed(tmp_db, [
            {"url": "https://a.com", "score": 82, "outcome": "converted"},
            {"url": "https://b.com", "score": 90, "outcome": "converted"},
            {"url": "https://c.com", "score": 75, "outcome": "disqualified"},
            {"url": "https://d.com", "score": 10, "outcome": "disqualified"},
        ])
        result = analyze_conversions(tmp_db)
        bands = result["precision_by_score_band"]
        # 81–100 band: 2 converted / 2 total → 1.0
        assert bands["81–100"] == 1.0
        # 61–80 band: 0 converted, 1 disqualified → 0.0
        assert bands["61–80"] == 0.0

    def test_calibration_hints_generated(self, tmp_db: Path):
        self._seed(tmp_db, [
            {"url": "https://a.com", "score": 80, "outcome": "converted"},
            {"url": "https://b.com", "score": 75, "outcome": "converted"},
            {"url": "https://c.com", "score": 15, "outcome": "disqualified"},
        ])
        result = analyze_conversions(tmp_db)
        assert isinstance(result["calibration_hints"], list)
        assert len(result["calibration_hints"]) > 0

    def test_high_score_disqualified_triggers_warning(self, tmp_db: Path):
        self._seed(tmp_db, [
            {"url": "https://a.com", "score": 80, "outcome": "converted"},
            {"url": "https://b.com", "score": 70, "outcome": "converted"},
            {"url": "https://c.com", "score": 75, "outcome": "disqualified"},  # high score but bad
        ])
        result = analyze_conversions(tmp_db)
        hints = " ".join(result["calibration_hints"])
        assert "false positives" in hints.lower() or "disqualified" in hints.lower()
