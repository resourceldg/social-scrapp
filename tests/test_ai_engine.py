"""
Tests for ai_engine: ollama_client (mocked), lead_analyst fallback, project_analyst fallback.
"""
import pytest
from unittest.mock import patch, MagicMock
from models import Lead
from scoring.score_result import LeadScoreResult
from ai_engine.lead_analyst import analyse_lead, AILeadAnalysis, _rule_based_fallback
from ai_engine.project_analyst import analyse_project_cluster, AIProjectAnalysis, _rule_based_project_fallback


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_lead(**kwargs) -> Lead:
    defaults = dict(
        name="Test Lead",
        social_handle="testhandle",
        source_platform="instagram",
        search_term="luxury hotel",
        bio="Luxury hotel designer",
        category="interior_designer",
        interest_signals=[],
        raw_data={},
        lead_type="interior_designer",
        city="Miami",
        country="US",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


def _make_score_result(**kwargs) -> LeadScoreResult:
    defaults = dict(
        final_score=60,
        contactability_score=50.0,
        relevance_score=70.0,
        authority_score=60.0,
        commercial_intent_score=55.0,
        premium_fit_score=65.0,
        platform_specific_score=50.0,
        data_quality_score=70.0,
        ranking_mode="balanced",
        buying_power_score=65.0,
        specifier_score=70.0,
        project_signal_score=55.0,
        event_signal_score=40.0,
        network_influence_score=0.0,
        opportunity_score=62,
        lead_classification="interior_designer",
        opportunity_classification="specifier_network",
        signal_density=3,
        confidence=0.75,
    )
    defaults.update(kwargs)
    return LeadScoreResult(**defaults)


def _make_cluster():
    """Build a minimal ProjectCluster for testing."""
    from project_engine.project_clusterer import ProjectCluster
    return ProjectCluster(
        project_type="hospitality",
        location_city="Miami",
        location_country="US",
        status="active",
        budget_tier="high",
        timeline_hint="Q3 2025",
        actor_handles=["designer1", "architect1", "developer1"],
        actor_ids=[1, 2, 3],
        evidence_texts=["luxury hotel under construction"],
        confidence=0.75,
        opportunity_density=0.6,
        avg_specifier_score=65.0,
        avg_buying_power_score=55.0,
        avg_event_signal_score=40.0,
    )


# ── AILeadAnalysis dataclass ───────────────────────────────────────────────────

class TestAILeadAnalysisDataclass:
    def test_default_values(self):
        a = AILeadAnalysis()
        assert a.ai_priority_score == 0
        assert a.recommended_action == "monitor"
        assert a.source == "fallback"
        assert isinstance(a.reasons, list)
        assert isinstance(a.uncertainties, list)

    def test_custom_values(self):
        a = AILeadAnalysis(
            ai_priority_score=85,
            recommended_action="contact_now",
            source="ai",
            confidence=0.9,
        )
        assert a.ai_priority_score == 85
        assert a.recommended_action == "contact_now"
        assert a.source == "ai"


# ── _rule_based_fallback ───────────────────────────────────────────────────────

class TestRuleBasedFallback:
    def test_returns_ai_lead_analysis(self):
        lead = _make_lead()
        result = _make_score_result()
        analysis = _rule_based_fallback(lead, result)
        assert isinstance(analysis, AILeadAnalysis)

    def test_source_is_fallback(self):
        lead = _make_lead()
        result = _make_score_result()
        analysis = _rule_based_fallback(lead, result)
        assert analysis.source == "fallback"

    def test_priority_score_in_range(self):
        lead = _make_lead()
        result = _make_score_result()
        analysis = _rule_based_fallback(lead, result)
        assert 0 <= analysis.ai_priority_score <= 100

    def test_action_contact_now_when_strong_signals(self):
        lead = _make_lead()
        result = _make_score_result(
            project_signal_score=60.0,
            buying_power_score=55.0,
            final_score=50,
        )
        analysis = _rule_based_fallback(lead, result)
        assert analysis.recommended_action == "contact_now"

    def test_action_skip_when_low_signals(self):
        lead = _make_lead()
        result = _make_score_result(
            project_signal_score=5.0,
            buying_power_score=5.0,
            specifier_score=5.0,
            opportunity_score=5,
            final_score=10,
        )
        analysis = _rule_based_fallback(lead, result)
        assert analysis.recommended_action == "skip"

    def test_action_nurture_when_medium_specifier(self):
        lead = _make_lead()
        result = _make_score_result(
            project_signal_score=10.0,
            specifier_score=55.0,
            buying_power_score=30.0,
            final_score=40,
        )
        analysis = _rule_based_fallback(lead, result)
        assert analysis.recommended_action == "nurture"

    def test_buying_intent_in_range(self):
        lead = _make_lead()
        result = _make_score_result()
        analysis = _rule_based_fallback(lead, result)
        assert 0 <= analysis.buying_intent <= 10

    def test_specifier_strength_in_range(self):
        lead = _make_lead()
        result = _make_score_result()
        analysis = _rule_based_fallback(lead, result)
        assert 0 <= analysis.specifier_strength <= 10

    def test_reasons_populated_with_strong_signals(self):
        lead = _make_lead()
        result = _make_score_result(
            project_signal_score=50.0,
            specifier_score=50.0,
            buying_power_score=50.0,
            event_signal_score=40.0,
        )
        analysis = _rule_based_fallback(lead, result)
        assert len(analysis.reasons) > 0

    def test_confidence_propagated(self):
        lead = _make_lead()
        result = _make_score_result(confidence=0.82)
        analysis = _rule_based_fallback(lead, result)
        assert analysis.confidence == round(0.82, 2)


# ── analyse_lead (with Ollama mocked unavailable) ─────────────────────────────

class TestAnalyseLead:
    @patch("ai_engine.lead_analyst.is_ai_available", return_value=False)
    def test_returns_fallback_when_ai_unavailable(self, _mock):
        lead = _make_lead()
        result = _make_score_result()
        analysis = analyse_lead(lead, result)
        assert isinstance(analysis, AILeadAnalysis)
        assert analysis.source == "fallback"

    @patch("ai_engine.lead_analyst.is_ai_available", return_value=False)
    def test_never_returns_none(self, _mock):
        lead = _make_lead()
        result = _make_score_result()
        analysis = analyse_lead(lead, result)
        assert analysis is not None

    @patch("ai_engine.lead_analyst.is_ai_available", return_value=True)
    @patch("ai_engine.lead_analyst.call_ollama")
    def test_parses_valid_ai_response(self, mock_call, _mock_avail):
        mock_call.return_value = {
            "ai_priority_score": 78,
            "lead_type": "interior_designer",
            "buying_intent": 7,
            "specifier_strength": 8,
            "project_context": "Hotel renovation in Miami",
            "recommended_action": "contact_now",
            "contact_angle": "Offer premium art collection for lobby",
            "confidence": 0.85,
            "reasons": ["active project signal", "high specifier score"],
            "uncertainties": ["limited social history"],
        }
        lead = _make_lead()
        result = _make_score_result()
        analysis = analyse_lead(lead, result)
        assert analysis.source == "ai"
        assert analysis.ai_priority_score == 78
        assert analysis.recommended_action == "contact_now"
        assert analysis.confidence == 0.85

    @patch("ai_engine.lead_analyst.is_ai_available", return_value=True)
    @patch("ai_engine.lead_analyst.call_ollama")
    def test_falls_back_when_ai_returns_invalid_action(self, mock_call, _mock_avail):
        mock_call.return_value = {
            "ai_priority_score": 50,
            "lead_type": "interior_designer",
            "buying_intent": 5,
            "specifier_strength": 5,
            "project_context": "",
            "recommended_action": "invalid_action",  # not a valid action
            "contact_angle": "",
            "confidence": 0.5,
            "reasons": [],
            "uncertainties": [],
        }
        lead = _make_lead()
        result = _make_score_result()
        analysis = analyse_lead(lead, result)
        # Should clamp to "monitor" (default)
        assert analysis.recommended_action == "monitor"

    @patch("ai_engine.lead_analyst.is_ai_available", return_value=True)
    @patch("ai_engine.lead_analyst.call_ollama", return_value=None)
    def test_graceful_fallback_when_ollama_returns_none(self, mock_call, _mock_avail):
        """call_ollama returning None should fall back to rule-based analysis."""
        lead = _make_lead()
        result = _make_score_result()
        analysis = analyse_lead(lead, result)
        assert isinstance(analysis, AILeadAnalysis)
        assert analysis.source == "fallback"


# ── AIProjectAnalysis dataclass ────────────────────────────────────────────────

class TestAIProjectAnalysisDataclass:
    def test_default_values(self):
        a = AIProjectAnalysis()
        assert a.urgency == "unknown"
        assert a.source == "fallback"
        assert isinstance(a.key_actors, list)
        assert isinstance(a.flags, list)


# ── _rule_based_project_fallback ───────────────────────────────────────────────

class TestRuleBasedProjectFallback:
    def test_returns_ai_project_analysis(self):
        cluster = _make_cluster()
        analysis = _rule_based_project_fallback(cluster)
        assert isinstance(analysis, AIProjectAnalysis)

    def test_source_is_fallback(self):
        cluster = _make_cluster()
        analysis = _rule_based_project_fallback(cluster)
        assert analysis.source == "fallback"

    def test_urgency_active_maps_to_immediate(self):
        cluster = _make_cluster()
        cluster.status = "active"
        analysis = _rule_based_project_fallback(cluster)
        assert analysis.urgency == "immediate"

    def test_urgency_emerging_maps_to_near_term(self):
        cluster = _make_cluster()
        cluster.status = "emerging"
        analysis = _rule_based_project_fallback(cluster)
        assert analysis.urgency == "near_term"

    def test_budget_range_set(self):
        cluster = _make_cluster()
        analysis = _rule_based_project_fallback(cluster)
        assert analysis.estimated_budget_range != ""

    def test_key_actors_from_handles(self):
        cluster = _make_cluster()
        analysis = _rule_based_project_fallback(cluster)
        assert len(analysis.key_actors) > 0


# ── analyse_project_cluster (with Ollama mocked) ──────────────────────────────

class TestAnalyseProjectCluster:
    @patch("ai_engine.project_analyst.is_ai_available", return_value=False)
    def test_returns_fallback_when_unavailable(self, _mock):
        cluster = _make_cluster()
        analysis = analyse_project_cluster(cluster)
        assert isinstance(analysis, AIProjectAnalysis)
        assert analysis.source == "fallback"

    @patch("ai_engine.project_analyst.is_ai_available", return_value=True)
    @patch("ai_engine.project_analyst.call_ollama")
    def test_parses_valid_ai_response(self, mock_call, _mock_avail):
        mock_call.return_value = {
            "project_name": "Miami Boutique Hotel",
            "summary": "Luxury hospitality project in Miami",
            "key_actors": ["designer1", "architect1"],
            "estimated_budget_range": "$500K-2M USD",
            "urgency": "immediate",
            "recommended_approach": "Contact lead architect first",
            "confidence": 0.80,
            "flags": ["active construction"],
        }
        cluster = _make_cluster()
        analysis = analyse_project_cluster(cluster)
        assert analysis.source == "ai"
        assert analysis.project_name == "Miami Boutique Hotel"
        assert analysis.urgency == "immediate"
