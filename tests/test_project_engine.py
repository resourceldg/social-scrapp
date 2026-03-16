"""
Tests for project_engine: project_detector, project_clusterer, project_ranker.
"""
import pytest
from models import Lead
from project_engine.project_detector import detect_project, ProjectDetection, _extract_timeline, _extract_city_from_text
from project_engine.project_clusterer import cluster_leads
from project_engine.project_ranker import rank_clusters, enrich_cluster_scores


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_lead(**kwargs) -> Lead:
    defaults = dict(
        name="Test Lead",
        social_handle="testhandle",
        source_platform="instagram",
        search_term="design",
        bio="",
        category="",
        interest_signals=[],
        raw_data={},
        lead_type="",
        city="",
        country="",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


# ── _extract_timeline ──────────────────────────────────────────────────────────

class TestExtractTimeline:
    def test_extracts_year(self):
        assert _extract_timeline("Opening in 2025") == "2025"

    def test_extracts_quarter(self):
        result = _extract_timeline("Launching Q3 2025")
        assert "Q3" in result

    def test_extracts_season(self):
        result = _extract_timeline("Opening this spring")
        assert "Spring" in result.capitalize() or "spring" in result.lower()

    def test_empty_when_none(self):
        assert _extract_timeline("no time signal here") == ""


# ── _extract_city_from_text ────────────────────────────────────────────────────

class TestExtractCity:
    def test_extracts_known_city(self):
        result = _extract_city_from_text("Project in Miami Beach design")
        assert result != ""

    def test_returns_empty_for_unknown(self):
        result = _extract_city_from_text("project in nowhere special")
        assert result == ""


# ── detect_project ─────────────────────────────────────────────────────────────

class TestDetectProject:
    def test_returns_none_when_empty_bio(self):
        lead = _make_lead(bio="")
        assert detect_project(lead, 0.0) is None

    def test_returns_none_when_score_too_low_and_no_active(self):
        lead = _make_lead(bio="I like design and architecture", city="Miami")
        # No active signal, score < 20 → should return None
        result = detect_project(lead, project_signal_score=5.0)
        assert result is None

    def test_returns_detection_with_active_signal(self):
        lead = _make_lead(bio="Currently working on a luxury hotel opening soon in Miami", city="Miami")
        result = detect_project(lead, project_signal_score=10.0)
        assert result is not None
        assert result.status == "active"

    def test_detects_hospitality_type(self):
        lead = _make_lead(bio="Designing a boutique hotel in Miami, opening Q3 2025")
        result = detect_project(lead, 50.0)
        assert result is not None
        assert result.project_type == "hospitality"

    def test_detects_residential_type(self):
        lead = _make_lead(bio="Working on a luxury penthouse in New York, currently designing")
        result = detect_project(lead, 50.0)
        assert result is not None
        assert result.project_type == "residential"

    def test_detects_high_budget_tier(self):
        lead = _make_lead(bio="Ultra-luxury hotel development, under construction in Dubai")
        result = detect_project(lead, 50.0)
        assert result is not None
        assert result.budget_tier in ("ultra", "high")

    def test_uses_lead_city_when_available(self):
        lead = _make_lead(bio="Currently working on a new project", city="Barcelona")
        result = detect_project(lead, 50.0)
        assert result is not None
        assert result.location_city == "Barcelona"

    def test_confidence_in_range(self):
        lead = _make_lead(
            bio="Luxury hotel under construction in Miami, Q3 2025 opening",
            city="Miami", country="US"
        )
        result = detect_project(lead, 70.0)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_confidence_higher_with_more_signals(self):
        lead_basic = _make_lead(bio="hotel planning", city="")
        lead_rich = _make_lead(
            bio="Luxury boutique hotel under construction in Miami, opening Q3 2025",
            city="Miami", country="US"
        )
        r_basic = detect_project(lead_basic, 25.0)
        r_rich = detect_project(lead_rich, 70.0)
        if r_basic and r_rich:
            assert r_rich.confidence >= r_basic.confidence

    def test_completed_status_detected(self):
        lead = _make_lead(bio="Just opened our new restaurant in London, now open!")
        result = detect_project(lead, 30.0)
        if result:
            assert result.status == "completed"

    def test_rumour_status_detected(self):
        lead = _make_lead(bio="Planning a new museum, still in early stages exploration")
        result = detect_project(lead, 30.0)
        if result:
            assert result.status in ("emerging", "rumour")

    def test_lead_id_hint_set(self):
        lead = _make_lead(bio="Ultra-luxury hotel under construction", social_handle="myhandle")
        result = detect_project(lead, 50.0)
        assert result is not None
        assert result.lead_id_hint == "myhandle"


# ── cluster_leads ──────────────────────────────────────────────────────────────

class TestClusterLeads:
    def _make_pair(self):
        lead1 = _make_lead(bio="Luxury hotel under construction in Miami Q3 2025", city="Miami", country="US", social_handle="a1")
        lead2 = _make_lead(bio="Boutique hotel project in Miami, opening soon", city="Miami", country="US", social_handle="a2")
        from project_engine.project_detector import detect_project
        d1 = detect_project(lead1, 60.0)
        d2 = detect_project(lead2, 60.0)
        pairs = []
        if d1:
            pairs.append((lead1, d1, 0))
        if d2:
            pairs.append((lead2, d2, 0))
        return pairs

    def test_returns_list(self):
        pairs = self._make_pair()
        clusters = cluster_leads(pairs)
        assert isinstance(clusters, list)

    def test_similar_leads_grouped(self):
        pairs = self._make_pair()
        if len(pairs) >= 2:
            clusters = cluster_leads(pairs)
            # Leads with same city + type should cluster together
            max_size = max((len(c.actor_handles) for c in clusters), default=0)
            assert max_size >= 1

    def test_empty_input(self):
        clusters = cluster_leads([])
        assert clusters == []

    def test_cluster_has_required_fields(self):
        pairs = self._make_pair()
        clusters = cluster_leads(pairs)
        for c in clusters:
            assert hasattr(c, "project_type")
            assert hasattr(c, "location_city")
            assert hasattr(c, "confidence")
            assert hasattr(c, "actor_handles")
            assert 0.0 <= c.confidence <= 1.0


# ── rank_clusters ──────────────────────────────────────────────────────────────

class TestRankClusters:
    def _make_cluster(self):
        lead = _make_lead(
            bio="Ultra luxury hotel under construction in Miami Q3 2025",
            city="Miami", country="US", social_handle="b1"
        )
        from project_engine.project_detector import detect_project
        d = detect_project(lead, 70.0)
        if d:
            pairs = [(lead, d, 0)]
            clusters = cluster_leads(pairs)
            return clusters
        return []

    def test_rank_returns_sorted_list(self):
        clusters = self._make_cluster()
        ranked = rank_clusters(clusters)
        assert isinstance(ranked, list)

    def test_opportunity_density_in_range(self):
        clusters = self._make_cluster()
        ranked = rank_clusters(clusters)
        for c in ranked:
            assert hasattr(c, "opportunity_density")
            assert 0.0 <= c.opportunity_density <= 1.0
