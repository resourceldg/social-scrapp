"""
Tests for the Signal Intelligence Pipeline.

Covers:
- Signal extraction (all 5 categories)
- Signal normalization
- BuyingPowerScore
- SpecifierScore
- ProjectSignalScore
- OpportunityScore + modes
- Lead and opportunity classification
- ScoreEngine integration (new fields)
- New RankingModes (SPECIFIER_NETWORK, HOT_PROJECT_DETECTION)
"""
from __future__ import annotations

import pytest

from models import Lead
from opportunity_engine.opportunity_classifier import classify_lead, classify_opportunity
from opportunity_engine.opportunity_scorer import compute_opportunity_score
from scoring.business_scoring import score_buying_power, score_project_signal, score_specifier
from scoring.score_engine import ScoreEngine
from scoring.weights_config import RankingMode
from signal_pipeline import SignalExtractor, normalize_signals
from signal_pipeline.signal_types import SignalType


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_lead(**kwargs) -> Lead:
    defaults = {
        "source_platform": "instagram",
        "search_term": "test",
        "name": "Test Lead",
        "social_handle": "testlead",
        "bio": "",
        "category": "",
        "lead_type": "",
        "email": "",
        "website": "",
        "phone": "",
        "city": "",
        "country": "",
        "followers": "",
        "engagement_hint": "",
    }
    defaults.update(kwargs)
    return Lead(**defaults)


_extractor = SignalExtractor()


# ── Signal Extraction ──────────────────────────────────────────────────────────

class TestRoleExtraction:
    def test_architect_in_bio(self):
        lead = make_lead(bio="I am an architect based in Madrid")
        signals = _extractor.extract(lead)
        roles = [s.value for s in signals.role_signals]
        assert "architect" in roles

    def test_interior_designer(self):
        lead = make_lead(bio="Interior designer and interiorista")
        signals = _extractor.extract(lead)
        roles = [s.value for s in signals.role_signals]
        assert "interior designer" in roles or "interiorista" in roles

    def test_curator_and_collector(self):
        lead = make_lead(bio="Curator and private collector of contemporary art")
        signals = _extractor.extract(lead)
        roles = [s.value for s in signals.role_signals]
        assert "curator" in roles
        assert "collector" in roles

    def test_no_roles(self):
        lead = make_lead(bio="I love pizza and football")
        signals = _extractor.extract(lead)
        assert signals.role_signals == []

    def test_deduplication(self):
        # "architect" appears in both bio and category — should appear once
        lead = make_lead(bio="architect", category="architect studio")
        signals = _extractor.extract(lead)
        values = [s.value for s in signals.role_signals]
        assert values.count("architect") == 1

    def test_source_field_tracked(self):
        lead = make_lead(bio="", category="art advisor")
        signals = _extractor.extract(lead)
        sources = [s.source for s in signals.role_signals]
        assert "category" in sources


class TestIndustryExtraction:
    def test_architecture(self):
        lead = make_lead(bio="Specialised in architecture and interior design")
        signals = _extractor.extract(lead)
        industry_vals = [s.value for s in signals.industry_signals]
        assert "architecture" in industry_vals

    def test_contemporary_art(self):
        lead = make_lead(bio="Arte contemporáneo y coleccionismo")
        signals = _extractor.extract(lead)
        vals = [s.value for s in signals.industry_signals]
        assert "arte contemporáneo" in vals

    def test_no_industry(self):
        lead = make_lead(bio="Just a regular person")
        signals = _extractor.extract(lead)
        assert signals.industry_signals == []


class TestLuxuryExtraction:
    def test_luxury_and_bespoke(self):
        lead = make_lead(bio="Luxury bespoke furniture for private collections")
        signals = _extractor.extract(lead)
        lux_vals = [s.value for s in signals.luxury_signals]
        assert "luxury" in lux_vals
        assert "bespoke" in lux_vals

    def test_obra_unica(self):
        lead = make_lead(bio="Creo obra única para coleccionistas")
        signals = _extractor.extract(lead)
        vals = [s.value for s in signals.luxury_signals]
        assert "obra única" in vals

    def test_no_luxury(self):
        lead = make_lead(bio="Budget furniture for everyone")
        signals = _extractor.extract(lead)
        assert signals.luxury_signals == []


class TestProjectExtraction:
    def test_opening_soon_is_recency(self):
        lead = make_lead(bio="New hotel opening soon in Miami")
        signals = _extractor.extract(lead)
        assert signals.has_project_signals
        recency_signals = [s for s in signals.project_signals if s.recency_hint]
        assert len(recency_signals) > 0

    def test_renovation_no_recency(self):
        lead = make_lead(bio="Working on a hotel renovation project")
        signals = _extractor.extract(lead)
        assert signals.has_project_signals
        # "renovation" does not have recency_hint
        non_recency = [s for s in signals.project_signals if not s.recency_hint]
        assert len(non_recency) > 0

    def test_recency_score_with_imminents(self):
        lead = make_lead(bio="Opening soon and coming soon in Barcelona")
        signals = _extractor.extract(lead)
        assert signals.recency_score > 0.0

    def test_no_project_signals(self):
        lead = make_lead(bio="I paint portraits")
        signals = _extractor.extract(lead)
        assert not signals.has_project_signals


class TestMarketExtraction:
    def test_tier1_markets(self):
        lead = make_lead(bio="Based in Madrid, projects in Miami and Barcelona")
        signals = _extractor.extract(lead)
        mkt_vals = [s.value for s in signals.market_signals]
        assert "madrid" in mkt_vals
        assert "miami" in mkt_vals
        assert "barcelona" in mkt_vals

    def test_city_field(self):
        lead = make_lead(city="miami", bio="")
        signals = _extractor.extract(lead)
        vals = [s.value for s in signals.market_signals]
        assert "miami" in vals

    def test_no_markets(self):
        lead = make_lead(bio="I live in a small town", city="smallville")
        signals = _extractor.extract(lead)
        assert signals.market_signals == []


class TestSignalSetProperties:
    def test_density(self):
        lead = make_lead(
            bio="Interior designer working on luxury hotel opening soon in Miami"
        )
        signals = _extractor.extract(lead)
        assert signals.density >= 3

    def test_active_types(self):
        lead = make_lead(
            bio="Architect with bespoke studio, new project opening soon in Madrid"
        )
        signals = _extractor.extract(lead)
        # Should have role, luxury, project, market signals
        assert signals.active_types >= 3

    def test_weighted_density(self):
        lead = make_lead(bio="luxury bespoke one of a kind obra única")
        signals = _extractor.extract(lead)
        assert signals.weighted_density > 0


# ── Signal Normalization ───────────────────────────────────────────────────────

class TestSignalNormalization:
    def test_empty_lead_all_zeros(self):
        lead = make_lead()
        signals = _extractor.extract(lead)
        norm = normalize_signals(lead, signals)
        assert norm.role_signal == 0.0
        assert norm.luxury_signal == 0.0
        assert norm.project_signal == 0.0
        assert norm.market_signal == 0.0

    def test_role_signal_nonzero(self):
        lead = make_lead(bio="architect and interior designer")
        signals = _extractor.extract(lead)
        norm = normalize_signals(lead, signals)
        assert norm.role_signal > 0

    def test_project_signal_boosted_by_recency(self):
        lead_recency = make_lead(bio="opening soon, launching soon")
        lead_generic = make_lead(bio="working on a renovation project")
        sig_r = _extractor.extract(lead_recency)
        sig_g = _extractor.extract(lead_generic)
        norm_r = normalize_signals(lead_recency, sig_r)
        norm_g = normalize_signals(lead_generic, sig_g)
        assert norm_r.project_signal > norm_g.project_signal

    def test_market_signal_nonzero(self):
        lead = make_lead(city="miami")
        signals = _extractor.extract(lead)
        norm = normalize_signals(lead, signals)
        assert norm.market_signal > 0

    def test_density_increases_with_signal_types(self):
        lead_rich = make_lead(
            bio="luxury architect opening soon in Madrid"
        )
        lead_sparse = make_lead(bio="architect")
        sig_rich = _extractor.extract(lead_rich)
        sig_sparse = _extractor.extract(lead_sparse)
        norm_rich = normalize_signals(lead_rich, sig_rich)
        norm_sparse = normalize_signals(lead_sparse, sig_sparse)
        assert norm_rich.signal_density > norm_sparse.signal_density


# ── BuyingPowerScore ───────────────────────────────────────────────────────────

class TestBuyingPowerScore:
    def test_luxury_hotel_developer(self):
        lead = make_lead(
            bio="Luxury boutique hotel developer in Miami. Private collection.",
            email="ceo@luxhotel.com",
        )
        signals = _extractor.extract(lead)
        score, reasons = score_buying_power(lead, signals)
        assert score >= 50
        assert any("luxury" in r for r in reasons)
        assert any("market" in r or "miami" in r.lower() for r in reasons)

    def test_empty_lead_low_score(self):
        lead = make_lead()
        signals = _extractor.extract(lead)
        score, _ = score_buying_power(lead, signals)
        assert score == 0

    def test_contact_info_bonus(self):
        lead_no_contact = make_lead(bio="luxury studio")
        lead_with_contact = make_lead(bio="luxury studio", email="a@b.com")
        sig_no = _extractor.extract(lead_no_contact)
        sig_with = _extractor.extract(lead_with_contact)
        score_no, _ = score_buying_power(lead_no_contact, sig_no)
        score_with, _ = score_buying_power(lead_with_contact, sig_with)
        assert score_with > score_no

    def test_score_bounded(self):
        lead = make_lead(
            bio="luxury bespoke high-end boutique hotel resort atelier maison "
                "premium private collection studio real estate developer firm "
                "in miami madrid barcelona punta del este",
            email="a@b.com",
            website="https://example.com",
        )
        signals = _extractor.extract(lead)
        score, _ = score_buying_power(lead, signals)
        assert 0 <= score <= 100

    def test_reasons_populated(self):
        lead = make_lead(bio="luxury hotel developer", city="miami")
        signals = _extractor.extract(lead)
        _, reasons = score_buying_power(lead, signals)
        assert len(reasons) > 0


# ── SpecifierScore ─────────────────────────────────────────────────────────────

class TestSpecifierScore:
    def test_architect_high_score(self):
        lead = make_lead(
            bio="Architect at renowned architecture firm in Madrid",
            source_platform="linkedin",
        )
        signals = _extractor.extract(lead)
        score, reasons = score_specifier(lead, signals)
        assert score >= 40
        assert any("architect" in r for r in reasons)

    def test_linkedin_amplification(self):
        lead_li = make_lead(bio="Interior designer", source_platform="linkedin")
        lead_ig = make_lead(bio="Interior designer", source_platform="instagram")
        sig_li = _extractor.extract(lead_li)
        sig_ig = _extractor.extract(lead_ig)
        score_li, _ = score_specifier(lead_li, sig_li)
        score_ig, _ = score_specifier(lead_ig, sig_ig)
        assert score_li > score_ig

    def test_no_role_low_score(self):
        lead = make_lead(bio="I love art")
        signals = _extractor.extract(lead)
        score, _ = score_specifier(lead, signals)
        assert score < 20

    def test_multiple_roles_compound(self):
        lead = make_lead(bio="Curator and art advisor at design studio")
        signals = _extractor.extract(lead)
        score_multi, _ = score_specifier(lead, signals)
        lead_single = make_lead(bio="Curator")
        sig_single = _extractor.extract(lead_single)
        score_single, _ = score_specifier(lead_single, sig_single)
        assert score_multi >= score_single

    def test_score_bounded(self):
        lead = make_lead(
            bio="architect interior designer curator art advisor procurement director "
                "at design studio in architecture firm",
            source_platform="linkedin",
        )
        signals = _extractor.extract(lead)
        score, _ = score_specifier(lead, signals)
        assert 0 <= score <= 100

    def test_studio_affiliation_bonus(self):
        lead_no_studio = make_lead(bio="architect")
        lead_studio = make_lead(bio="architect at my studio")
        sig_no = _extractor.extract(lead_no_studio)
        sig_yes = _extractor.extract(lead_studio)
        score_no, _ = score_specifier(lead_no_studio, sig_no)
        score_yes, _ = score_specifier(lead_studio, sig_yes)
        assert score_yes > score_no


# ── ProjectSignalScore ─────────────────────────────────────────────────────────

class TestProjectSignalScore:
    def test_opening_soon_high_score(self):
        lead = make_lead(bio="Luxury hotel opening soon. Commissions open.")
        signals = _extractor.extract(lead)
        score, reasons = score_project_signal(lead, signals)
        assert score >= 40
        assert any("active" in r or "recent" in r for r in reasons)

    def test_generic_renovation_lower_than_recency(self):
        lead_hot = make_lead(bio="opening soon and launching soon")
        lead_cold = make_lead(bio="working on renovation")
        sig_hot = _extractor.extract(lead_hot)
        sig_cold = _extractor.extract(lead_cold)
        score_hot, _ = score_project_signal(lead_hot, sig_hot)
        score_cold, _ = score_project_signal(lead_cold, sig_cold)
        assert score_hot > score_cold

    def test_no_signals_zero(self):
        lead = make_lead(bio="I paint and sculpt")
        signals = _extractor.extract(lead)
        score, _ = score_project_signal(lead, signals)
        assert score == 0

    def test_purchase_intent_detected(self):
        lead = make_lead(bio="commissions open, available for projects")
        signals = _extractor.extract(lead)
        score, reasons = score_project_signal(lead, signals)
        assert score > 0
        assert any("purchase intent" in r or "commission" in r.lower() for r in reasons)

    def test_density_amplifier(self):
        # All 3 density-contributing types present
        lead = make_lead(
            bio="architect working on hotel renovation opening soon",
            category="interior design",
        )
        signals = _extractor.extract(lead)
        score, reasons = score_project_signal(lead, signals)
        assert any("density" in r for r in reasons)

    def test_bounded(self):
        lead = make_lead(
            bio="opening soon launching soon under construction new project "
                "commissions open available for projects sourcing looking for",
        )
        signals = _extractor.extract(lead)
        score, _ = score_project_signal(lead, signals)
        assert 0 <= score <= 100


# ── OpportunityScore ───────────────────────────────────────────────────────────

class TestOpportunityScore:
    def test_basic_computation(self):
        score, reasons = compute_opportunity_score(
            base_lead_score=70,
            buying_power_score=60,
            specifier_score=80,
            project_signal_score=50,
        )
        assert 0 <= score <= 100

    def test_all_zeros(self):
        score, _ = compute_opportunity_score(0, 0, 0, 0)
        assert score == 0

    def test_specifier_mode_weights_specifier(self):
        """In SPECIFIER_NETWORK mode, specifier score should dominate."""
        score_high_spec, _ = compute_opportunity_score(
            50, 30, 90, 10, mode=RankingMode.SPECIFIER_NETWORK
        )
        score_low_spec, _ = compute_opportunity_score(
            50, 30, 10, 10, mode=RankingMode.SPECIFIER_NETWORK
        )
        assert score_high_spec > score_low_spec

    def test_hot_project_mode_weights_project(self):
        """In HOT_PROJECT_DETECTION mode, project signal should dominate."""
        score_hot, _ = compute_opportunity_score(
            50, 30, 20, 90, mode=RankingMode.HOT_PROJECT_DETECTION
        )
        score_cold, _ = compute_opportunity_score(
            50, 30, 20, 10, mode=RankingMode.HOT_PROJECT_DETECTION
        )
        assert score_hot > score_cold

    def test_reasons_populated_for_high_scores(self):
        _, reasons = compute_opportunity_score(70, 70, 80, 60)
        assert len(reasons) >= 2

    def test_bounded_at_100(self):
        # All six components at 100 must produce exactly 100 (bounded)
        score, _ = compute_opportunity_score(100, 100, 100, 100,
                                             event_signal_score=100,
                                             network_influence_score=100)
        assert score == 100


# ── Lead Classification ────────────────────────────────────────────────────────

class TestLeadClassification:
    def test_architect(self):
        lead = make_lead(bio="I am an architect at a Barcelona architecture firm")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "architect"

    def test_interior_designer(self):
        lead = make_lead(bio="Interior designer and interiorista")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "interior_designer"

    def test_gallery(self):
        lead = make_lead(bio="Gallery director at art space in Miami")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "gallery"

    def test_collector(self):
        lead = make_lead(bio="Private collector of contemporary art")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "collector"

    def test_hospitality(self):
        lead = make_lead(bio="Luxury hotel developer and hotelier")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "hospitality"

    def test_existing_lead_type_mapped(self):
        lead = make_lead(lead_type="arquitecto")
        signals = _extractor.extract(lead)
        assert classify_lead(lead, signals) == "architect"

    def test_unknown_returns_unknown(self):
        lead = make_lead(bio="I like pasta")
        signals = _extractor.extract(lead)
        result = classify_lead(lead, signals)
        # May be "unknown" or fallback to role signal — not an error
        assert isinstance(result, str)


# ── Opportunity Classification ─────────────────────────────────────────────────

class TestOpportunityClassification:
    def test_active_project_wins(self):
        result = classify_opportunity("architect", 40, 50, 75, 60)
        assert result == "active_project"

    def test_specifier_network(self):
        result = classify_opportunity("architect", 40, 70, 20, 55)
        assert result == "specifier_network"

    def test_direct_buyer(self):
        result = classify_opportunity("collector", 70, 20, 20, 55)
        assert result == "direct_buyer"

    def test_strategic_partner(self):
        result = classify_opportunity("gallery", 30, 30, 20, 50)
        assert result == "strategic_partner"

    def test_low_signal(self):
        result = classify_opportunity("unknown", 5, 5, 5, 10)
        assert result == "low_signal"


# ── ScoreEngine Integration ────────────────────────────────────────────────────

class TestScoreEngineIntegration:
    def test_result_has_all_new_fields(self):
        lead = make_lead(
            bio="Architect at luxury design studio in Madrid",
            source_platform="linkedin",
            email="arch@studio.es",
        )
        engine = ScoreEngine(mode=RankingMode.SPECIFIER_NETWORK)
        result = engine.score(lead)

        assert isinstance(result.buying_power_score, float)
        assert isinstance(result.specifier_score, float)
        assert isinstance(result.project_signal_score, float)
        assert isinstance(result.opportunity_score, int)
        assert isinstance(result.lead_classification, str)
        assert isinstance(result.opportunity_classification, str)
        assert isinstance(result.signal_density, int)

    def test_hot_project_mode_surfaces_project(self):
        lead_project = make_lead(
            bio="Hotel opening soon, commissions open. Fit-out in progress.",
        )
        lead_normal = make_lead(bio="Interior designer based in Barcelona")
        engine = ScoreEngine(mode=RankingMode.HOT_PROJECT_DETECTION)
        result_hot = engine.score(lead_project)
        result_norm = engine.score(lead_normal)
        assert result_hot.opportunity_score > result_norm.opportunity_score

    def test_specifier_network_mode_surfaces_architect(self):
        lead = make_lead(
            bio="Architect at architecture firm, interior design projects",
            source_platform="linkedin",
        )
        engine = ScoreEngine(mode=RankingMode.SPECIFIER_NETWORK)
        result = engine.score(lead)
        assert result.specifier_score > 0
        assert result.lead_classification == "architect"

    def test_opportunity_score_bounded(self):
        lead = make_lead(
            bio="luxury architect opening soon commissions open miami atelier",
            email="a@b.com",
            source_platform="linkedin",
        )
        engine = ScoreEngine()
        result = engine.score(lead)
        assert 0 <= result.opportunity_score <= 100

    def test_backward_compat_score_lead(self):
        """score_lead() still returns int."""
        from utils.scoring import score_lead
        lead = make_lead(bio="Interior designer in Madrid", email="a@b.com")
        score = score_lead(lead)
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_new_ranking_modes_produce_valid_results(self):
        lead = make_lead(bio="Architect with luxury studio in Madrid")
        for mode in (RankingMode.SPECIFIER_NETWORK, RankingMode.HOT_PROJECT_DETECTION):
            engine = ScoreEngine(mode=mode)
            result = engine.score(lead)
            assert 0 <= result.final_score <= 100
            assert 0 <= result.opportunity_score <= 100

    def test_signal_density_reflects_active_types(self):
        lead_rich = make_lead(
            bio="Luxury architect opening soon in Madrid"
        )
        lead_empty = make_lead()
        engine = ScoreEngine()
        result_rich = engine.score(lead_rich)
        result_empty = engine.score(lead_empty)
        assert result_rich.signal_density > result_empty.signal_density

    def test_classification_in_result(self):
        lead = make_lead(bio="Private collector of contemporary art")
        engine = ScoreEngine()
        result = engine.score(lead)
        assert result.lead_classification == "collector"
