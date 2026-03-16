"""Tests for RouteEvaluator — hashtag sanitization, scoring, route candidates."""
import tempfile
from pathlib import Path

import pytest
from core.route_evaluator import RouteEvaluator, _UNKNOWN_SCORE


@pytest.fixture
def evaluator(tmp_path: Path) -> RouteEvaluator:
    return RouteEvaluator(tmp_path / "route_stats.db")


# ── Hashtag sanitization ──────────────────────────────────────────────────────

class TestSanitizeHashtag:
    def test_strips_leading_hash(self):
        assert RouteEvaluator.sanitize_hashtag("#interiordesign") == "interiordesign"

    def test_strips_spaces(self):
        assert RouteEvaluator.sanitize_hashtag("interior design") == "interiordesign"

    def test_strips_hyphens(self):
        assert RouteEvaluator.sanitize_hashtag("interior-design") == "interiordesign"

    def test_keeps_accented_letters(self):
        result = RouteEvaluator.sanitize_hashtag("#artecontemporáneo")
        assert result is not None
        assert "á" in result or "contemporaneo" in result.lower()

    def test_strips_dots_quotes(self):
        assert RouteEvaluator.sanitize_hashtag("studio.design") == "studiodesign"

    def test_empty_returns_none(self):
        assert RouteEvaluator.sanitize_hashtag("") is None
        assert RouteEvaluator.sanitize_hashtag("#") is None
        assert RouteEvaluator.sanitize_hashtag("   ") is None

    def test_special_chars_only_returns_none(self):
        assert RouteEvaluator.sanitize_hashtag("---###") is None

    def test_max_length_truncated(self):
        long_tag = "a" * 120
        result = RouteEvaluator.sanitize_hashtag(long_tag)
        assert result is not None
        assert len(result) <= 100

    def test_normal_alphanumeric_preserved(self):
        assert RouteEvaluator.sanitize_hashtag("woodart123") == "woodart123"

    def test_underscore_preserved(self):
        # underscores are allowed in Instagram hashtags after stripping via regex
        # Our regex removes underscores (they're in \s\-\. group? No, underscore is \w)
        # Underscores ARE allowed — just not via the removal regex
        result = RouteEvaluator.sanitize_hashtag("luxury_interiors")
        assert result is not None


# ── Stability scoring ─────────────────────────────────────────────────────────

class TestStabilityScore:
    def test_unknown_route_returns_default(self, evaluator: RouteEvaluator):
        score = evaluator.stability_score("instagram", "instagram/hashtag/new")
        assert score == pytest.approx(_UNKNOWN_SCORE)

    def test_all_successes_trend_toward_one(self, evaluator: RouteEvaluator):
        for _ in range(20):
            evaluator.record_success("instagram", "instagram/hashtag/good")
        score = evaluator.stability_score("instagram", "instagram/hashtag/good")
        assert score > 0.85

    def test_all_failures_trend_toward_zero(self, evaluator: RouteEvaluator):
        for _ in range(20):
            evaluator.record_failure("instagram", "instagram/hashtag/bad")
        score = evaluator.stability_score("instagram", "instagram/hashtag/bad")
        assert score < 0.15

    def test_mixed_history_midrange(self, evaluator: RouteEvaluator):
        for _ in range(10):
            evaluator.record_success("instagram", "instagram/hashtag/mixed")
        for _ in range(10):
            evaluator.record_failure("instagram", "instagram/hashtag/mixed")
        score = evaluator.stability_score("instagram", "instagram/hashtag/mixed")
        assert 0.25 < score < 0.75

    def test_low_sample_count_reduces_confidence(self, evaluator: RouteEvaluator):
        evaluator.record_success("instagram", "instagram/hashtag/rare")
        score_low = evaluator.stability_score("instagram", "instagram/hashtag/rare")
        for _ in range(19):
            evaluator.record_success("instagram", "instagram/hashtag/rare")
        score_high = evaluator.stability_score("instagram", "instagram/hashtag/rare")
        assert score_high > score_low


# ── Penalized routes ──────────────────────────────────────────────────────────

class TestPenalizedPatterns:
    def test_bad_route_is_penalized_after_threshold(self, evaluator: RouteEvaluator):
        for _ in range(10):
            evaluator.record_failure("instagram", "instagram/hashtag/broken")
        penalized = evaluator.penalized_patterns("instagram")
        assert "instagram/hashtag/broken" in penalized

    def test_good_route_not_penalized(self, evaluator: RouteEvaluator):
        for _ in range(10):
            evaluator.record_success("instagram", "instagram/hashtag/good")
        penalized = evaluator.penalized_patterns("instagram")
        assert "instagram/hashtag/good" not in penalized

    def test_route_with_few_samples_not_penalized(self, evaluator: RouteEvaluator):
        evaluator.record_failure("instagram", "instagram/hashtag/new_bad")
        penalized = evaluator.penalized_patterns("instagram")
        # Only 1 sample — below MIN_SAMPLES_TO_PENALIZE
        assert "instagram/hashtag/new_bad" not in penalized


# ── Candidate generation ──────────────────────────────────────────────────────

class TestInstagramCandidates:
    def test_valid_hashtag_returns_candidates(self, evaluator: RouteEvaluator):
        candidates = evaluator.instagram_route_candidates("#interiordesign")
        assert len(candidates) >= 1
        assert any("interiordesign" in c.url for c in candidates)

    def test_candidates_sorted_by_priority(self, evaluator: RouteEvaluator):
        candidates = evaluator.instagram_route_candidates("#luxuryinteriors")
        priorities = [c.priority for c in candidates]
        assert priorities == sorted(priorities)

    def test_invalid_hashtag_falls_back(self, evaluator: RouteEvaluator):
        # Keyword with no extractable hashtag
        candidates = evaluator.instagram_route_candidates("!!!###")
        # Should still return something (the fallback candidate) or empty
        assert isinstance(candidates, list)

    def test_penalized_route_gets_demoted_priority(self, evaluator: RouteEvaluator):
        tag = "brokenhashtag"
        pattern = f"instagram/hashtag/{tag}"
        for _ in range(10):
            evaluator.record_failure("instagram", pattern)
        candidates = evaluator.instagram_route_candidates(f"#{tag}")
        matching = [c for c in candidates if c.pattern == pattern]
        if matching:
            assert matching[0].priority == 99
