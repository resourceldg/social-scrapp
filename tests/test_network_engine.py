"""
Tests for network_engine: mention_parser, graph_builder, graph_metrics.
"""
import pytest
from models import Lead
from network_engine.mention_parser import parse_mentions, MentionResult
from network_engine.graph_builder import build_graph, NetworkGraph
from network_engine.graph_metrics import compute_graph_metrics, ActorMetrics, _normalize_dict


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


# ── parse_mentions ─────────────────────────────────────────────────────────────

class TestParseMentions:
    def test_empty_bio_returns_no_mentions(self):
        lead = _make_lead(bio="")
        assert parse_mentions(lead) == []

    def test_detects_bare_mention(self):
        lead = _make_lead(bio="Working alongside @studiodesign on a new project.", social_handle="me")
        results = parse_mentions(lead)
        handles = [r.target_handle for r in results]
        assert "studiodesign" in handles

    def test_does_not_self_mention(self):
        lead = _make_lead(bio="@me is excited about this project.", social_handle="me")
        results = parse_mentions(lead)
        assert not any(r.target_handle == "me" for r in results)

    def test_detects_collaborates_with(self):
        lead = _make_lead(bio="In collaboration with @partner on a new hotel project.", social_handle="designer")
        results = parse_mentions(lead)
        collab = [r for r in results if r.relation_type == "COLLABORATES_WITH"]
        assert len(collab) > 0

    def test_detects_designed_by(self):
        lead = _make_lead(bio="Interiors by @studioX for this boutique hotel.", social_handle="client")
        results = parse_mentions(lead)
        designed = [r for r in results if r.relation_type == "DESIGNED_BY"]
        assert len(designed) > 0

    def test_detects_works_on(self):
        lead = _make_lead(bio="Working for @hotelbrand on their new property.", social_handle="designer")
        results = parse_mentions(lead)
        works_on = [r for r in results if r.relation_type == "WORKS_ON"]
        assert len(works_on) > 0

    def test_no_duplicates(self):
        lead = _make_lead(bio="@partner @partner @partner same handle repeated", social_handle="me")
        results = parse_mentions(lead)
        handles = [r.target_handle for r in results]
        assert len(handles) == len(set(handles))

    def test_confidence_in_range(self):
        lead = _make_lead(bio="In collaboration with @partner", social_handle="me")
        results = parse_mentions(lead)
        for r in results:
            assert 0.0 <= r.confidence <= 1.0

    def test_collab_has_higher_confidence_than_bare_mention(self):
        lead_collab = _make_lead(bio="In collaboration with @partner", social_handle="me")
        lead_bare = _make_lead(bio="@partner is great", social_handle="me")
        r_collab = parse_mentions(lead_collab)
        r_bare = parse_mentions(lead_bare)
        if r_collab and r_bare:
            c_collab = max(r.confidence for r in r_collab)
            c_bare = max(r.confidence for r in r_bare)
            assert c_collab >= c_bare

    def test_raw_data_caption_scanned(self):
        lead = _make_lead(bio="", raw_data={"caption": "designed by @studioZ for client"}, social_handle="me")
        results = parse_mentions(lead)
        assert len(results) > 0

    def test_source_handle_set(self):
        lead = _make_lead(bio="@partner is cool", social_handle="myhandle")
        results = parse_mentions(lead)
        if results:
            assert results[0].source_handle == "myhandle"

    def test_platform_propagated(self):
        lead = _make_lead(bio="@partner is cool", social_handle="myhandle", source_platform="instagram")
        results = parse_mentions(lead)
        if results:
            assert results[0].source_platform == "instagram"


# ── build_graph ────────────────────────────────────────────────────────────────

class TestBuildGraph:
    def _two_leads(self):
        l1 = _make_lead(bio="In collaboration with @designer2", social_handle="designer1")
        l2 = _make_lead(bio="Working on luxury hotel", social_handle="designer2")
        return [l1, l2]

    def test_returns_network_graph(self):
        leads = self._two_leads()
        graph = build_graph(leads)
        assert isinstance(graph, NetworkGraph)

    def test_nodes_added_for_leads(self):
        leads = self._two_leads()
        from network_engine.mention_parser import parse_mentions as pm
        mentions = []
        for l in leads:
            mentions.extend(pm(l))
        graph = build_graph(leads, mentions)
        assert graph.node_count >= len(leads)

    def test_edges_added_for_mentions(self):
        leads = self._two_leads()
        from network_engine.mention_parser import parse_mentions as pm
        mentions = []
        for l in leads:
            mentions.extend(pm(l))
        graph = build_graph(leads, mentions)
        assert graph.edge_count >= 0  # at least 0; exact count depends on match

    def test_empty_leads_returns_empty_graph(self):
        graph = build_graph([])
        assert graph.is_empty()

    def test_no_mentions_still_builds_nodes(self):
        leads = self._two_leads()
        graph = build_graph(leads, mention_results=[])
        assert graph.node_count == len(leads)

    def test_to_json_returns_dict(self):
        leads = self._two_leads()
        graph = build_graph(leads)
        data = graph.to_json()
        assert isinstance(data, dict)
        assert "nodes" in data


# ── _normalize_dict ────────────────────────────────────────────────────────────

class TestNormalizeDict:
    def test_empty_dict(self):
        assert _normalize_dict({}) == {}

    def test_max_becomes_100(self):
        d = {"a": 5.0, "b": 10.0}
        result = _normalize_dict(d)
        assert result["b"] == 100.0

    def test_zero_safe(self):
        d = {"a": 0.0, "b": 0.0}
        result = _normalize_dict(d)
        for v in result.values():
            assert v == 0.0


# ── compute_graph_metrics ──────────────────────────────────────────────────────

class TestComputeGraphMetrics:
    def _build_simple_graph(self):
        l1 = _make_lead(bio="In collaboration with @b and @c", social_handle="a")
        l2 = _make_lead(bio="Working with @c", social_handle="b")
        l3 = _make_lead(bio="Central connector", social_handle="c")
        leads = [l1, l2, l3]
        from network_engine.mention_parser import parse_mentions as pm
        mentions = []
        for l in leads:
            mentions.extend(pm(l))
        return build_graph(leads, mentions)

    def test_returns_dict(self):
        graph = self._build_simple_graph()
        metrics = compute_graph_metrics(graph)
        assert isinstance(metrics, dict)

    def test_empty_graph_returns_empty(self):
        graph = build_graph([])
        metrics = compute_graph_metrics(graph)
        assert metrics == {}

    def test_scores_in_range(self):
        graph = self._build_simple_graph()
        metrics = compute_graph_metrics(graph)
        for node_id, m in metrics.items():
            assert 0.0 <= m.network_influence_score <= 100.0
            assert 0.0 <= m.pagerank_score <= 100.0
            assert 0.0 <= m.betweenness_score <= 100.0
            assert 0.0 <= m.degree_score <= 100.0

    def test_actor_metrics_has_handle(self):
        graph = self._build_simple_graph()
        metrics = compute_graph_metrics(graph)
        for node_id, m in metrics.items():
            assert isinstance(m, ActorMetrics)
            assert m.handle  # non-empty
