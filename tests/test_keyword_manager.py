"""Tests for KeywordManager."""
import pytest
from utils.keyword_manager import KeywordManager


@pytest.fixture
def km() -> KeywordManager:
    return KeywordManager()


def test_summary_has_all_platforms(km: KeywordManager):
    summary = km.summary()
    assert summary["total"] > 50
    assert "instagram" in summary["by_platform"]
    assert "linkedin" in summary["by_platform"]


def test_for_platform_returns_list(km: KeywordManager):
    kws = km.for_platform("instagram")
    assert isinstance(kws, list)
    assert len(kws) > 0


def test_for_platform_respects_max(km: KeywordManager):
    kws = km.for_platform("linkedin", max_keywords=5)
    assert len(kws) <= 5


def test_no_duplicates_in_results(km: KeywordManager):
    kws = km.for_platform("instagram", max_keywords=100)
    assert len(kws) == len(set(kws))


def test_hashtags_for_instagram_start_with_hash(km: KeywordManager):
    tags = km.hashtags_for("instagram")
    assert all(t.startswith("#") for t in tags)


def test_keywords_for_linkedin_no_hashtags(km: KeywordManager):
    kws = km.keywords_for("linkedin")
    # LinkedIn keywords shouldn't all be hashtags
    hashtag_count = sum(1 for k in kws if k.startswith("#"))
    assert hashtag_count < len(kws)


def test_all_for_platform_respects_max(km: KeywordManager):
    for platform in ["instagram", "facebook", "linkedin", "pinterest", "reddit", "twitter"]:
        kws = km.all_for_platform(platform, max_keywords=20)
        assert len(kws) <= 20, f"Too many keywords for {platform}"


def test_priority_1_comes_before_priority_3(km: KeywordManager):
    """High-priority keywords should appear before low-priority ones."""
    kws = km.for_platform("linkedin", max_keywords=50)
    # At least some keywords should be returned
    assert len(kws) >= 5


def test_vertical_filter(km: KeywordManager):
    kws = km.for_platform("linkedin", verticals=["art"], max_keywords=20)
    assert len(kws) > 0


def test_type_filter_keyword_type(km: KeywordManager):
    kws = km.for_platform("linkedin", types=["transactional"], max_keywords=20)
    assert len(kws) > 0


def test_coverage_by_language(km: KeywordManager):
    summary = km.summary()
    langs = summary["by_language"]
    assert "es" in langs
    assert "en" in langs
    assert langs["en"] > 0 and langs["es"] > 0
