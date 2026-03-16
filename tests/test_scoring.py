"""
Tests for the multi-layer scoring engine.

Coverage
--------
- Follower string parser (thresholds.parse_followers)
- Follower bucket mapping (thresholds.follower_score)
- Universal dimension scorers (base_scoring)
- Platform-specific scorers (instagram, linkedin, reddit)
- Ranking modes (all five, weight correctness, relative ordering)
- Penalty/warning propagation (data_quality)
- Full pipeline (ScoreEngine.score)
"""
from __future__ import annotations

import pytest

from models import Lead
from scoring import LeadScoreResult, RankingMode
from scoring.score_engine import ScoreEngine
from scoring.base_scoring import (
    score_authority,
    score_commercial_intent,
    score_contactability,
    score_data_quality,
    score_premium_fit,
    score_relevance,
)
from scoring.platform_scoring import instagram_scoring, linkedin_scoring, reddit_scoring
from scoring.thresholds import (
    GENERIC_FOLLOWER_BUCKETS,
    INSTAGRAM_FOLLOWER_BUCKETS,
    REDDIT_SUBSCRIBER_BUCKETS,
    follower_score,
    parse_followers,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _lead(**kwargs) -> Lead:
    defaults: dict = {"source_platform": "instagram", "search_term": "test"}
    defaults.update(kwargs)
    return Lead(**defaults)


def _rich_lead(platform: str = "instagram") -> Lead:
    return Lead(
        source_platform=platform,
        search_term="test",
        name="Design Studio XYZ",
        social_handle="dsxyz",
        email="contact@dsxyz.com",
        website="https://dsxyz.com",
        bio=(
            "Luxury bespoke collectible design studio. "
            "Interior design and art advisory. Commission projects welcome."
        ),
        category="interior design",
        lead_type="estudio",
        followers="50K",
        engagement_hint="high",
        country="Argentina",
    )


# ── parse_followers ────────────────────────────────────────────────────────────

class TestParseFollowers:
    def test_k_suffix(self):
        assert parse_followers("2.5K") == 2500

    def test_m_suffix(self):
        assert parse_followers("45M") == 45_000_000

    def test_plain_integer(self):
        assert parse_followers("1234") == 1234

    def test_comma_separated(self):
        assert parse_followers("1,234") == 1234

    def test_with_trailing_text(self):
        assert parse_followers("12500 karma") == 12500

    def test_100k(self):
        assert parse_followers("100K") == 100_000

    def test_empty_string(self):
        assert parse_followers("") == 0

    def test_none_like_empty(self):
        # Should not raise, returns 0
        assert parse_followers("   ") == 0


# ── follower_score buckets ─────────────────────────────────────────────────────

class TestFollowerScore:
    def test_instagram_above_100k(self):
        assert follower_score("150K", INSTAGRAM_FOLLOWER_BUCKETS) == 25

    def test_instagram_50k_tier(self):
        assert follower_score("60K", INSTAGRAM_FOLLOWER_BUCKETS) == 20

    def test_instagram_10k_tier(self):
        assert follower_score("15K", INSTAGRAM_FOLLOWER_BUCKETS) == 15

    def test_instagram_5k_tier(self):
        assert follower_score("7K", INSTAGRAM_FOLLOWER_BUCKETS) == 10

    def test_instagram_1k_tier(self):
        assert follower_score("2K", INSTAGRAM_FOLLOWER_BUCKETS) == 5

    def test_instagram_under_1k(self):
        assert follower_score("500", INSTAGRAM_FOLLOWER_BUCKETS) == 2

    def test_reddit_100k_tier(self):
        assert follower_score("120K", REDDIT_SUBSCRIBER_BUCKETS) == 25

    def test_reddit_50k_tier(self):
        assert follower_score("75K", REDDIT_SUBSCRIBER_BUCKETS) == 15

    def test_reddit_10k_tier(self):
        assert follower_score("20K", REDDIT_SUBSCRIBER_BUCKETS) == 10

    def test_reddit_1k_tier(self):
        assert follower_score("2K", REDDIT_SUBSCRIBER_BUCKETS) == 5

    def test_reddit_under_1k(self):
        assert follower_score("500", REDDIT_SUBSCRIBER_BUCKETS) == 0

    def test_generic_1m(self):
        assert follower_score("1M", GENERIC_FOLLOWER_BUCKETS) == 100

    def test_empty_followers_returns_0(self):
        assert follower_score("", INSTAGRAM_FOLLOWER_BUCKETS) == 0


# ── ContactabilityScore ────────────────────────────────────────────────────────

class TestContactabilityScore:
    def test_email_only(self):
        score, reasons = score_contactability(_lead(email="x@y.com"))
        assert score == 40.0
        assert "email available" in reasons

    def test_website_only(self):
        score, _ = score_contactability(_lead(website="https://x.com"))
        assert score == 25.0

    def test_phone_only(self):
        score, _ = score_contactability(_lead(phone="+1234567890"))
        assert score == 20.0

    def test_email_and_website(self):
        score, _ = score_contactability(_lead(email="a@b.com", website="https://x.com"))
        assert score == 65.0

    def test_all_three(self):
        score, _ = score_contactability(
            _lead(email="a@b.com", website="https://x.com", phone="+1")
        )
        assert score == 85.0

    def test_no_contact(self):
        score, reasons = score_contactability(_lead())
        assert score == 0.0
        assert reasons == []

    def test_linkedin_in_bio_for_non_linkedin(self):
        score, reasons = score_contactability(
            _lead(source_platform="instagram", bio="See my work on linkedin.com/in/test")
        )
        assert score == 15.0
        assert "linkedin profile referenced" in reasons

    def test_linkedin_url_not_double_counted_on_linkedin(self):
        score, reasons = score_contactability(
            _lead(
                source_platform="linkedin",
                profile_url="https://linkedin.com/in/test",
            )
        )
        assert score == 0.0  # No email/phone/website, linkedin URL not extra-rewarded


# ── RelevanceScore ─────────────────────────────────────────────────────────────

class TestRelevanceScore:
    def test_core_keyword_gives_20pts(self):
        score, reasons = score_relevance(_lead(bio="collectible design furniture"))
        assert score >= 20
        assert any("collectible design" in r for r in reasons)

    def test_lead_type_bonus(self):
        score, reasons = score_relevance(_lead(lead_type="galeria"))
        assert score >= 10
        assert any("classified as" in r for r in reasons)

    def test_target_country_bonus(self):
        score, _ = score_relevance(_lead(country="Argentina"))
        assert score >= 8

    def test_irrelevant_bio_low_score(self):
        score, _ = score_relevance(_lead(bio="fitness gym daily workout tips"))
        assert score < 15

    def test_multiple_core_keywords_cumulate(self):
        score, _ = score_relevance(
            _lead(bio="architecture studio and contemporary art gallery")
        )
        # "architecture" + "contemporary art" + "gallery" = 20+20+12
        assert score >= 40


# ── AuthorityScore ─────────────────────────────────────────────────────────────

class TestAuthorityScore:
    def test_1m_followers(self):
        score, _ = score_authority(_lead(followers="1M"))
        assert score == 100.0

    def test_100k_followers(self):
        score, _ = score_authority(_lead(followers="100K"))
        assert score == 75.0

    def test_no_followers(self):
        score, _ = score_authority(_lead())
        assert score == 0.0

    def test_engagement_hint_bonus(self):
        base, _ = score_authority(_lead(followers="1K"))
        with_hint, _ = score_authority(_lead(followers="1K", engagement_hint="high"))
        assert with_hint > base

    def test_capped_at_100(self):
        # Even with engagement + verified, should not exceed 100
        score, _ = score_authority(
            _lead(followers="1M", engagement_hint="high", bio="✓ verified creator")
        )
        assert score == 100.0


# ── CommercialIntentScore ─────────────────────────────────────────────────────

class TestCommercialIntentScore:
    def test_commission_signal(self):
        score, reasons = score_commercial_intent(
            _lead(bio="We accept commissions for custom sculptures")
        )
        assert score >= 20
        assert any("commission" in r for r in reasons)

    def test_art_advisory_high_signal(self):
        score, reasons = score_commercial_intent(_lead(bio="art advisory services"))
        assert score >= 25
        assert any("art advisory" in r for r in reasons)

    def test_no_intent_signals(self):
        score, _ = score_commercial_intent(_lead(bio="Beautiful nature photography"))
        assert score == 0.0

    def test_multiple_signals_cumulate(self):
        score, _ = score_commercial_intent(
            _lead(bio="project sourcing and procurement for hospitality")
        )
        assert score >= 30


# ── PremiumFitScore ────────────────────────────────────────────────────────────

class TestPremiumFitScore:
    def test_bespoke_luxury(self):
        score, reasons = score_premium_fit(
            _lead(bio="Bespoke luxury furniture for private collections")
        )
        assert score >= 40
        assert any("bespoke" in r for r in reasons)

    def test_obra_unica_high_score(self):
        score, reasons = score_premium_fit(_lead(bio="obra única escultura"))
        assert score >= 25
        assert any("obra única" in r for r in reasons)

    def test_no_premium_signals(self):
        score, _ = score_premium_fit(_lead(bio="affordable student apartment decor"))
        assert score == 0.0


# ── DataQualityScore ──────────────────────────────────────────────────────────

class TestDataQualityScore:
    def test_perfect_lead_no_warnings(self):
        lead = _lead(
            bio="An interior design studio specializing in luxury residential projects",
            name="Studio XYZ",
            social_handle="studioXYZ",
            lead_type="estudio",
            followers="10K",
            country="Argentina",
        )
        score, warnings = score_data_quality(lead)
        assert score == 100.0
        assert warnings == []

    def test_missing_bio_penalty(self):
        lead = _lead(name="Test", lead_type="estudio", followers="5K", country="Argentina")
        score, warnings = score_data_quality(lead)
        assert score <= 70.0
        assert "missing bio" in warnings

    def test_short_bio_penalty(self):
        lead = _lead(
            bio="hi", name="Test", lead_type="estudio", followers="5K", country="Argentina"
        )
        score, warnings = score_data_quality(lead)
        assert score <= 80.0
        assert "bio too short" in warnings

    def test_name_equals_handle_penalty(self):
        # Penalty applies on platforms where the real name is expected (linkedin/facebook)
        lead = _lead(
            source_platform="linkedin",
            bio="long enough bio text to pass the short check",
            name="myhandle",
            social_handle="myhandle",
            lead_type="estudio",
            followers="5K",
            country="Argentina",
        )
        _, warnings = score_data_quality(lead)
        assert "name equals handle (not enriched)" in warnings

    def test_name_equals_handle_no_penalty_on_instagram(self):
        # On Instagram/Twitter/Pinterest/Reddit the handle is the identity — no penalty
        lead = _lead(
            source_platform="instagram",
            bio="long enough bio text to pass the short check",
            name="myhandle",
            social_handle="myhandle",
            lead_type="estudio",
            followers="5K",
            country="Argentina",
        )
        _, warnings = score_data_quality(lead)
        assert "name equals handle (not enriched)" not in warnings

    def test_no_lead_type_penalty(self):
        lead = _lead(
            bio="long enough bio text to pass the short check",
            name="Studio",
            social_handle="handle",
            followers="5K",
            country="Argentina",
        )
        score, warnings = score_data_quality(lead)
        assert score <= 90.0
        assert "no lead type classified" in warnings

    def test_score_minimum_zero(self):
        # Lead with all fields empty should not go below 0
        score, _ = score_data_quality(_lead())
        assert score >= 0.0


# ── Instagram platform scoring ────────────────────────────────────────────────

class TestInstagramScoring:
    def test_high_follower_tier(self):
        lead = _lead(source_platform="instagram", followers="150K")
        score, reasons = instagram_scoring.score_platform_specific(lead)
        assert score >= 25
        assert any("instagram follower tier" in r for r in reasons)

    def test_niche_keywords_in_bio(self):
        lead = _lead(
            source_platform="instagram",
            bio="interior design studio specializing in luxury collectible pieces",
        )
        score, reasons = instagram_scoring.score_platform_specific(lead)
        assert score > 0
        assert any("niche bio keyword" in r for r in reasons)

    def test_hashtag_signals(self):
        lead = _lead(
            source_platform="instagram",
            bio="Curator #interiordesign #artgallery #luxuryinteriors",
        )
        score, reasons = instagram_scoring.score_platform_specific(lead)
        assert any("hashtag" in r for r in reasons)

    def test_engagement_hint_bonus(self):
        no_hint = instagram_scoring.score_platform_specific(
            _lead(source_platform="instagram", followers="5K")
        )[0]
        with_hint = instagram_scoring.score_platform_specific(
            _lead(source_platform="instagram", followers="5K", engagement_hint="high")
        )[0]
        assert with_hint > no_hint

    def test_score_bounded(self):
        lead = _lead(
            source_platform="instagram",
            followers="1M",
            bio=" ".join(["luxury interior design gallery curator collectible"] * 5),
            engagement_hint="very high",
        )
        score, _ = instagram_scoring.score_platform_specific(lead)
        assert 0 <= score <= 100


# ── LinkedIn platform scoring ─────────────────────────────────────────────────

class TestLinkedInScoring:
    def test_ceo_founder_tier(self):
        lead = _lead(source_platform="linkedin", bio="Founder & CEO of a bespoke design studio")
        score, reasons = linkedin_scoring.score_platform_specific(lead)
        assert score >= 22
        assert any("seniority" in r for r in reasons)

    def test_director_tier(self):
        lead = _lead(source_platform="linkedin", bio="Art Director at Gallery Nacional")
        score, reasons = linkedin_scoring.score_platform_specific(lead)
        assert score >= 15

    def test_manager_tier(self):
        lead = _lead(source_platform="linkedin", bio="Project Manager at interior design firm")
        score, reasons = linkedin_scoring.score_platform_specific(lead)
        assert score >= 8

    def test_relevant_title_adds_points(self):
        lead = _lead(source_platform="linkedin", bio="Interior design consultant specializing in luxury")
        score, _ = linkedin_scoring.score_platform_specific(lead)
        assert score > 0

    def test_linkedin_url_bonus(self):
        with_url = linkedin_scoring.score_platform_specific(
            _lead(
                source_platform="linkedin",
                bio="Designer",
                profile_url="https://linkedin.com/in/testuser",
            )
        )[0]
        without_url = linkedin_scoring.score_platform_specific(
            _lead(source_platform="linkedin", bio="Designer")
        )[0]
        assert with_url > without_url


# ── Reddit platform scoring ───────────────────────────────────────────────────

class TestRedditScoring:
    def test_subreddit_large(self):
        lead = _lead(
            source_platform="reddit",
            profile_url="https://reddit.com/r/interiordesign",
            followers="75K",
        )
        score, reasons = reddit_scoring.score_platform_specific(lead)
        assert score >= 15
        assert any("subreddit subscriber" in r for r in reasons)

    def test_subreddit_small(self):
        lead = _lead(
            source_platform="reddit",
            profile_url="https://reddit.com/r/tinyniche",
            followers="200",
        )
        score, _ = reddit_scoring.score_platform_specific(lead)
        assert score == 0

    def test_user_high_karma(self):
        lead = _lead(
            source_platform="reddit",
            profile_url="https://reddit.com/user/artlover",
            followers="15000 karma",
        )
        score, reasons = reddit_scoring.score_platform_specific(lead)
        assert score >= 20
        assert any("high karma" in r for r in reasons)

    def test_user_low_karma(self):
        lead = _lead(
            source_platform="reddit",
            profile_url="https://reddit.com/user/newbie",
            followers="50 karma",
        )
        score, _ = reddit_scoring.score_platform_specific(lead)
        assert score < 10

    def test_community_keywords(self):
        lead = _lead(
            source_platform="reddit",
            profile_url="https://reddit.com/r/art",
            followers="5K",
            bio="Discussion about contemporary art and sculpture",
        )
        score, reasons = reddit_scoring.score_platform_specific(lead)
        assert any("community relevance" in r for r in reasons)


# ── Ranking modes ─────────────────────────────────────────────────────────────

class TestRankingModes:
    def test_all_modes_return_valid_result(self):
        lead = _rich_lead()
        for mode in RankingMode:
            engine = ScoreEngine(mode=mode)
            result = engine.score(lead)
            assert isinstance(result, LeadScoreResult)
            assert 0 <= result.final_score <= 100
            assert 0.0 <= result.confidence <= 1.0
            assert result.ranking_mode == mode.value

    def test_contactability_first_favours_lead_with_email(self):
        """A lead with email should rank higher under contactability_first."""
        lead_with_email = _rich_lead()
        lead_no_email = Lead(
            source_platform="instagram",
            search_term="test",
            name="Studio B",
            social_handle="studiob",
            bio="Luxury interior design studio with high-end bespoke pieces",
            category="interior design",
            lead_type="estudio",
            followers="500K",
            country="Argentina",
        )
        c_engine = ScoreEngine(mode=RankingMode.CONTACTABILITY_FIRST)
        a_engine = ScoreEngine(mode=RankingMode.AUTHORITY_FIRST)

        c_email = c_engine.score(lead_with_email).final_score
        c_no_email = c_engine.score(lead_no_email).final_score
        a_email = a_engine.score(lead_with_email).final_score
        a_no_email = a_engine.score(lead_no_email).final_score

        # Under contactability_first, the gap between email/no-email should be bigger
        contactability_gap = c_email - c_no_email
        authority_gap = a_email - a_no_email
        assert contactability_gap > authority_gap

    def test_authority_first_favours_high_follower_lead(self):
        """High-follower lead should rank relatively higher under authority_first."""
        low_followers = _lead(
            source_platform="instagram",
            bio="Interior design luxury studio",
            email="a@b.com",
            website="https://x.com",
            lead_type="estudio",
            followers="1K",
            country="Argentina",
        )
        high_followers = _lead(
            source_platform="instagram",
            bio="Interior design luxury studio",
            lead_type="estudio",
            followers="500K",
            country="Argentina",
        )
        auth_engine = ScoreEngine(mode=RankingMode.AUTHORITY_FIRST)
        reach_engine = ScoreEngine(mode=RankingMode.CONTACTABILITY_FIRST)

        auth_high = auth_engine.score(high_followers).final_score
        auth_low = auth_engine.score(low_followers).final_score
        reach_high = reach_engine.score(high_followers).final_score
        reach_low = reach_engine.score(low_followers).final_score

        assert auth_high > auth_low
        assert (auth_high - auth_low) >= (reach_high - reach_low)

    def test_ranking_mode_stored_in_result(self):
        for mode in RankingMode:
            result = ScoreEngine(mode=mode).score(_lead())
            assert result.ranking_mode == mode.value


# ── Full pipeline ─────────────────────────────────────────────────────────────

class TestScoreEngine:
    def test_result_has_all_fields(self):
        result = ScoreEngine().score(_lead(bio="gallery design", email="x@y.com"))
        for field in (
            "final_score", "contactability_score", "relevance_score",
            "authority_score", "commercial_intent_score", "premium_fit_score",
            "platform_specific_score", "data_quality_score",
            "ranking_mode", "reasons", "warnings", "confidence",
        ):
            assert hasattr(result, field)

    def test_score_bounded_0_100(self):
        # Maximally good lead should still be ≤ 100
        lead = Lead(
            source_platform="instagram",
            search_term="test",
            name="Ultra Premium Studio",
            social_handle="ups",
            email="contact@ups.com",
            website="https://ups.com",
            phone="+549111",
            bio=(
                "Luxury bespoke collectible design studio. "
                "Art advisory. Hospitality projects. Commission & encargo. "
                "obra única. private collection. #interiordesign #artgallery"
            ),
            category="collectible design luxury",
            lead_type="estudio",
            followers="1M",
            engagement_hint="very high",
            country="Argentina",
        )
        result = ScoreEngine().score(lead)
        assert 0 <= result.final_score <= 100

    def test_empty_lead_low_score_and_confidence(self):
        result = ScoreEngine().score(Lead(source_platform="instagram", search_term="test"))
        assert result.final_score < 30
        assert result.confidence < 0.3

    def test_warnings_surface_data_quality_issues(self):
        result = ScoreEngine().score(_lead())  # empty lead
        assert len(result.warnings) > 0

    def test_reasons_list_populated_for_good_lead(self):
        result = ScoreEngine().score(_rich_lead())
        assert len(result.reasons) > 0

    def test_unknown_platform_does_not_crash(self):
        lead = _lead(source_platform="tiktok", bio="design studio")
        result = ScoreEngine().score(lead)
        assert isinstance(result, LeadScoreResult)
        assert 0 <= result.final_score <= 100

    def test_backward_compat_score_lead(self):
        """utils.scoring.score_lead must still return an int."""
        from utils.scoring import score_lead

        lead = _rich_lead()
        score = score_lead(lead)
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_linkedin_multipliers_amplify_authority(self):
        """LinkedIn authority multiplier (1.5) should produce higher authority score
        than the same profile on a platform with lower authority multiplier."""
        base_lead_kwargs = dict(
            search_term="test",
            name="Director Fernandez",
            social_handle="dfernandez",
            bio="Art Director at a luxury design studio. Interior architecture.",
            lead_type="diseñador",
            followers="10K",
            country="Argentina",
        )
        linkedin_lead = Lead(source_platform="linkedin", **base_lead_kwargs)
        pinterest_lead = Lead(source_platform="pinterest", **base_lead_kwargs)

        engine = ScoreEngine(mode=RankingMode.AUTHORITY_FIRST)
        li_result = engine.score(linkedin_lead)
        pi_result = engine.score(pinterest_lead)

        # LinkedIn authority multiplier 1.5 vs Pinterest 1.0
        assert li_result.final_score >= pi_result.final_score
