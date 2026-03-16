"""
NetworkRenderer — renders a NetworkGraph as an interactive Pyvis HTML graph.

Node colors by type:
  lead (specifier)      → #6C63FF  purple
  lead (buyer)          → #FF6B6B  coral
  lead (project_actor)  → #FF9F43  orange
  lead (influencer)     → #48CAE4  sky blue
  lead (gallery_node)   → #A29BFE  lavender
  lead (other)          → #B2BEC3  grey
  project               → #00B894  green
  event                 → #FDCB6E  gold
  account               → #E17055  terracotta

Edge styles by relation type:
  COLLABORATES_WITH     → solid, width=3
  DESIGNED_BY           → dashed, width=2
  WORKS_ON              → dotted, width=2
  FEATURES              → solid, width=1
  MENTIONED_WITH        → dotted, width=1

Usage
-----
    from visualization.network_renderer import render_network_html
    html = render_network_html(network_graph, min_confidence=0.5)
    # Embed in Streamlit: st.components.v1.html(html, height=600, scrolling=False)
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from network_engine.graph_builder import NetworkGraph

logger = logging.getLogger(__name__)

try:
    from pyvis.network import Network as _PyvisNetwork
    _PYVIS_OK = True
except ImportError:
    _PYVIS_OK = False

# ── Visual constants ──────────────────────────────────────────────────────────

_PROFILE_COLORS: dict[str, str] = {
    "specifier":     "#6C63FF",
    "buyer":         "#FF6B6B",
    "project_actor": "#FF9F43",
    "influencer":    "#48CAE4",
    "gallery_node":  "#A29BFE",
    "aspirational":  "#B2BEC3",
    "unknown":       "#B2BEC3",
}

_TYPE_COLORS: dict[str, str] = {
    "project": "#00B894",
    "event":   "#FDCB6E",
    "account": "#E17055",
    "lead":    "#B2BEC3",  # fallback — overridden by profile
}

_EDGE_STYLES: dict[str, dict] = {
    "COLLABORATES_WITH": {"color": "#6C63FF", "width": 3, "dashes": False},
    "DESIGNED_BY":       {"color": "#00B894", "width": 2, "dashes": True},
    "WORKS_ON":          {"color": "#FF9F43", "width": 2, "dashes": True},
    "FEATURES":          {"color": "#FDCB6E", "width": 1, "dashes": False},
    "MENTIONED_WITH":    {"color": "#B2BEC3", "width": 1, "dashes": True},
    "MEMBER_OF":         {"color": "#E17055", "width": 1, "dashes": True},
    "PARTICIPATES_IN":   {"color": "#FDCB6E", "width": 2, "dashes": False},
    "EXHIBITS_AT":       {"color": "#FDCB6E", "width": 2, "dashes": False},
    "COMMISSIONED_BY":   {"color": "#E17055", "width": 2, "dashes": True},
}
_DEFAULT_EDGE_STYLE = {"color": "#DFE6E9", "width": 1, "dashes": True}


def _node_size(attrs: dict) -> int:
    """Size node by opportunity_score or score."""
    opp = attrs.get("opportunity_score", 0) or 0
    score = attrs.get("score", 0) or 0
    val = max(opp, score)
    if val >= 70:
        return 40
    if val >= 45:
        return 28
    if val >= 25:
        return 20
    return 14


def _node_color(attrs: dict) -> str:
    ntype = attrs.get("type", "lead")
    if ntype != "lead":
        return _TYPE_COLORS.get(ntype, "#B2BEC3")
    profile = attrs.get("lead_profile", "aspirational")
    return _PROFILE_COLORS.get(profile, _PROFILE_COLORS["aspirational"])


def _node_title(node_id: str, attrs: dict) -> str:
    """HTML tooltip for a node."""
    parts = [f"<b>{attrs.get('label', node_id)}</b>"]
    ntype = attrs.get("type", "lead")
    parts.append(f"Type: {ntype}")
    if ntype == "lead":
        parts.append(f"Platform: {attrs.get('platform','')}")
        parts.append(f"Lead type: {attrs.get('lead_type','')}")
        parts.append(f"Score: {attrs.get('score', 0)}")
        opp = attrs.get("opportunity_score", 0)
        if opp:
            parts.append(f"Opp. score: {opp}")
        opp_c = attrs.get("opportunity_classification", "")
        if opp_c:
            parts.append(f"Classification: {opp_c}")
        city = attrs.get("city", "")
        if city:
            parts.append(f"City: {city}")
    return "<br>".join(parts)


def render_network_html(
    network_graph: NetworkGraph,
    min_confidence: float = 0.4,
    height: int = 580,
    max_nodes: int = 300,
) -> str:
    """
    Render a NetworkGraph as a self-contained interactive HTML string.

    Parameters
    ----------
    network_graph : NetworkGraph
    min_confidence : float
        Edges below this confidence are hidden.
    height : int
        Canvas height in pixels.
    max_nodes : int
        Truncate graph to the top N nodes by opportunity_score to keep
        the browser responsive.

    Returns
    -------
    str
        Complete HTML string. Embed with st.components.v1.html().
        Returns a plain error HTML string if pyvis is not installed.
    """
    if not _PYVIS_OK:
        return "<p style='color:red'>pyvis not installed — run: pip install pyvis</p>"

    G = network_graph.G
    if G is None or G.number_of_nodes() == 0:
        return "<p style='color:#636e72'>No hay datos de red todavía. Ejecuta un scrape y enriquecimiento primero.</p>"

    try:
        import networkx as nx

        # Limit nodes for browser performance
        if G.number_of_nodes() > max_nodes:
            top_nodes = sorted(
                G.nodes(data=True),
                key=lambda x: x[1].get("opportunity_score", 0) + x[1].get("score", 0),
                reverse=True,
            )[:max_nodes]
            sub_node_ids = {n for n, _ in top_nodes}
            G = G.subgraph(sub_node_ids)

        net = _PyvisNetwork(
            height=f"{height}px",
            width="100%",
            bgcolor="#1E1E2E",
            font_color="#CDD6F4",
            directed=True,
            notebook=False,
        )

        # Physics options — force-directed, stabilises quickly
        net.set_options("""
        {
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -80,
              "centralGravity": 0.01,
              "springLength": 120,
              "springConstant": 0.08,
              "damping": 0.6
            },
            "solver": "forceAtlas2Based",
            "stabilization": { "iterations": 150 }
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          },
          "edges": { "smooth": { "type": "dynamic" } }
        }
        """)

        # Add nodes
        for node_id, attrs in G.nodes(data=True):
            net.add_node(
                node_id,
                label=str(attrs.get("label", node_id))[:22],
                color=_node_color(attrs),
                size=_node_size(attrs),
                title=_node_title(node_id, attrs),
                font={"size": 11, "color": "#CDD6F4"},
                borderWidth=2,
                borderWidthSelected=4,
            )

        # Add edges
        for src, dst, edata in G.edges(data=True):
            conf = edata.get("confidence", 0.5)
            if conf < min_confidence:
                continue
            rel = edata.get("relation_type", "MENTIONED_WITH")
            style = _EDGE_STYLES.get(rel, _DEFAULT_EDGE_STYLE)
            tooltip = (
                f"<b>{rel}</b><br>"
                f"confidence: {conf:.2f}<br>"
                f"platform: {edata.get('platform','')}"
            )
            net.add_edge(
                src, dst,
                color={"color": style["color"], "opacity": min(1.0, conf + 0.2)},
                width=style["width"],
                dashes=style["dashes"],
                title=tooltip,
                arrows={"to": {"enabled": True, "scaleFactor": 0.6}},
            )

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            tmp_path = f.name

        net.save_graph(tmp_path)
        html = Path(tmp_path).read_text(encoding="utf-8")
        Path(tmp_path).unlink(missing_ok=True)
        return html

    except Exception as exc:
        logger.exception("network render failed")
        return f"<p style='color:red'>Error rendering network: {exc}</p>"
