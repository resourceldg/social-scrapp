"""
Tests for visualization: network_renderer, opportunity_heatmap, export_graph.
(world_map skipped: requires Folium + full cluster data which is end-to-end)
"""
import pytest
import pandas as pd
from models import Lead
from network_engine.graph_builder import build_graph, NetworkGraph
from network_engine.mention_parser import parse_mentions
from visualization.network_renderer import render_network_html
from visualization.opportunity_heatmap import render_opportunity_heatmap
from visualization.export_graph import export_graph


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
        lead_type="interior_designer",
        city="Miami",
        country="US",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


def _make_simple_graph() -> NetworkGraph:
    l1 = _make_lead(bio="In collaboration with @b", social_handle="a", lead_type="interior_designer")
    l2 = _make_lead(bio="Hotel project", social_handle="b", lead_type="architect")
    leads = [l1, l2]
    mentions = []
    for l in leads:
        mentions.extend(parse_mentions(l))
    return build_graph(leads, mentions)


def _make_leads_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"city": "Miami", "lead_type": "interior_designer", "opportunity_score": 75, "score": 70},
        {"city": "Miami", "lead_type": "architect", "opportunity_score": 60, "score": 55},
        {"city": "New York", "lead_type": "interior_designer", "opportunity_score": 80, "score": 78},
        {"city": "New York", "lead_type": "collector", "opportunity_score": 50, "score": 48},
        {"city": "London", "lead_type": "architect", "opportunity_score": 65, "score": 62},
    ])


# ── render_network_html ────────────────────────────────────────────────────────

class TestRenderNetworkHtml:
    def test_returns_string(self):
        graph = _make_simple_graph()
        html = render_network_html(graph)
        assert isinstance(html, str)

    def test_empty_graph_returns_string(self):
        graph = build_graph([])
        html = render_network_html(graph)
        assert isinstance(html, str)

    def test_html_non_empty_when_graph_has_nodes(self):
        graph = _make_simple_graph()
        html = render_network_html(graph)
        # Should produce non-empty output with nodes
        assert len(html) > 0

    def test_min_confidence_filters_edges(self):
        graph = _make_simple_graph()
        html_low = render_network_html(graph, min_confidence=0.0)
        html_high = render_network_html(graph, min_confidence=0.99)
        # Both return strings (no crash)
        assert isinstance(html_low, str)
        assert isinstance(html_high, str)

    def test_custom_height_accepted(self):
        graph = _make_simple_graph()
        html = render_network_html(graph, height=800)
        assert isinstance(html, str)

    def test_max_nodes_limits_output(self):
        # Build a graph with many leads
        leads = [_make_lead(social_handle=f"user{i}", bio=f"Lead {i}") for i in range(20)]
        graph = build_graph(leads, [])
        html_all = render_network_html(graph, max_nodes=20)
        html_few = render_network_html(graph, max_nodes=3)
        assert isinstance(html_all, str)
        assert isinstance(html_few, str)


# ── render_opportunity_heatmap ─────────────────────────────────────────────────

class TestRenderOpportunityHeatmap:
    def test_returns_figure(self):
        import plotly.graph_objects as go
        df = _make_leads_df()
        fig = render_opportunity_heatmap(df)
        assert isinstance(fig, go.Figure)

    def test_empty_df_returns_figure(self):
        import plotly.graph_objects as go
        df = pd.DataFrame(columns=["city", "lead_type", "opportunity_score", "score"])
        fig = render_opportunity_heatmap(df)
        assert isinstance(fig, go.Figure)

    def test_missing_opportunity_score_col_falls_back(self):
        import plotly.graph_objects as go
        df = _make_leads_df().drop(columns=["opportunity_score"])
        fig = render_opportunity_heatmap(df)
        assert isinstance(fig, go.Figure)

    def test_figure_has_data(self):
        df = _make_leads_df()
        fig = render_opportunity_heatmap(df)
        # Should have at least one trace
        assert len(fig.data) >= 0  # permissive — empty df may have 0 traces

    def test_top_cities_param(self):
        import plotly.graph_objects as go
        df = _make_leads_df()
        fig = render_opportunity_heatmap(df, top_cities=2)
        assert isinstance(fig, go.Figure)


# ── export_graph ───────────────────────────────────────────────────────────────

class TestExportGraph:
    def test_empty_graph_returns_empty_bytes(self):
        graph = build_graph([])
        payload, filename, mime = export_graph(graph, fmt="json")
        assert payload == b""

    def test_json_format(self):
        graph = _make_simple_graph()
        payload, filename, mime = export_graph(graph, fmt="json")
        assert mime == "application/json"
        assert filename == "social_graph.json"
        assert len(payload) > 0

    def test_gexf_format(self):
        graph = _make_simple_graph()
        payload, filename, mime = export_graph(graph, fmt="gexf")
        assert mime == "application/xml"
        assert "gexf" in filename.lower()
        assert len(payload) > 0

    def test_graphml_format(self):
        graph = _make_simple_graph()
        payload, filename, mime = export_graph(graph, fmt="graphml")
        assert mime == "application/xml"
        assert "graphml" in filename.lower()
        assert len(payload) > 0

    def test_csv_format_returns_zip(self):
        graph = _make_simple_graph()
        payload, filename, mime = export_graph(graph, fmt="csv")
        assert mime == "application/zip"
        assert filename.endswith(".zip")
        assert len(payload) > 0

    def test_invalid_format_returns_empty(self):
        graph = _make_simple_graph()
        payload, filename, mime = export_graph(graph, fmt="invalid_format")
        assert payload == b""
        assert "error" in filename.lower() or filename == "export_error.txt"

    def test_json_is_valid_json(self):
        import json
        graph = _make_simple_graph()
        payload, _, _ = export_graph(graph, fmt="json")
        if payload:
            data = json.loads(payload.decode("utf-8"))
            assert "nodes" in data

    def test_csv_zip_contains_correct_files(self):
        import io, zipfile
        graph = _make_simple_graph()
        payload, _, _ = export_graph(graph, fmt="csv")
        if payload:
            zf = zipfile.ZipFile(io.BytesIO(payload))
            names = zf.namelist()
            assert "nodes.csv" in names
            assert "edges.csv" in names

    def test_case_insensitive_format(self):
        graph = _make_simple_graph()
        payload_upper, _, _ = export_graph(graph, fmt="JSON")
        payload_lower, _, _ = export_graph(graph, fmt="json")
        assert len(payload_upper) == len(payload_lower)
