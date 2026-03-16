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
    """HTML tooltip — sanitization is disabled via JS injection in render_network_html."""
    label = attrs.get("label", node_id)
    ntype = attrs.get("type", "lead")
    city = attrs.get("city", "")
    country = attrs.get("country", "")
    loc = ", ".join(p for p in [city, country] if p)

    lines = [f"<b style='font-size:13px'>{label}</b>"]
    if loc:
        lines.append(f"<span style='color:#C4A35A'>📍 {loc}</span>")

    if ntype == "lead":
        platform = attrs.get("platform", "")
        lead_type = attrs.get("lead_type", "") or "—"
        score = attrs.get("score", 0)
        opp = attrs.get("opportunity_score", 0)
        opp_c = attrs.get("opportunity_classification", "")
        proj_sig = attrs.get("project_signal_score", 0.0) or 0
        evt_sig = attrs.get("event_signal_score", 0.0) or 0
        followers = attrs.get("followers", "")
        bio = attrs.get("bio", "")
        profile_url = attrs.get("profile_url", "")

        lines.append(f"<span style='color:#aaa'>{platform} · {lead_type}</span>")
        lines.append(f"Score <b>{score}</b>" + (f" · Opp <b>{opp}</b>" if opp else ""))
        if opp_c:
            lines.append(f"<span style='color:#C4A35A'>{opp_c.replace('_',' ')}</span>")
        if followers:
            lines.append(f"Followers: {followers}")
        _signals = []
        if proj_sig > 0:
            _signals.append(f"Project {proj_sig:.0f}")
        if evt_sig > 0:
            _signals.append(f"Event {evt_sig:.0f}")
        if _signals:
            lines.append("Signals: " + " · ".join(_signals))
        if bio:
            lines.append(f"<i style='color:#ccc;font-size:11px'>{bio[:100]}…</i>")
        if profile_url:
            lines.append(
                f'<a href="{profile_url}" target="_blank" '
                f'style="color:#C4A35A;text-decoration:underline">Open profile ↗</a>'
            )
    elif ntype == "project":
        lines.append("<span style='color:#00B894'>Project node</span>")
    elif ntype == "event":
        lines.append("<span style='color:#FDCB6E'>Event node</span>")

    return "<br>".join(lines)


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

        # ── Node selection: always include connected nodes, fill with top-scored ──
        import networkx as _nx_local
        _connected_ids = {n for n in G.nodes() if G.degree(n) > 0}
        _isolated_ids = [
            n for n, d in sorted(
                G.nodes(data=True),
                key=lambda x: x[1].get("opportunity_score", 0) + x[1].get("score", 0),
                reverse=True,
            ) if n not in _connected_ids
        ]
        _slots = max(0, max_nodes - len(_connected_ids))
        _show_ids = _connected_ids | set(_isolated_ids[:_slots])
        G = G.subgraph(_show_ids)

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

        # Add nodes — connected nodes get gold border + larger size
        _connected_set = {n for n in G.nodes() if G.degree(n) > 0}
        for node_id, attrs in G.nodes(data=True):
            _name = str(attrs.get("label", node_id))[:20]
            _city = attrs.get("city", "")
            _label = f"{_name}\n{_city[:12]}" if _city else _name
            _is_conn = node_id in _connected_set
            _base_color = _node_color(attrs)
            _color = {
                "background": _base_color,
                "border": "#C4A35A" if _is_conn else "#444",
                "highlight": {"background": _base_color, "border": "#F5F0E6"},
            }
            net.add_node(
                node_id,
                label=_label,
                color=_color,
                size=(_node_size(attrs) + 10) if _is_conn else _node_size(attrs),
                font={"size": 12 if _is_conn else 10, "color": "#F5F0E6" if _is_conn else "#9A9A9A"},
                borderWidth=3 if _is_conn else 1,
                borderWidthSelected=5,
            )

        # Add edges
        for src, dst, edata in G.edges(data=True):
            conf = edata.get("confidence", 0.5)
            if conf < min_confidence:
                continue
            rel = edata.get("relation_type", "MENTIONED_WITH")
            style = _EDGE_STYLES.get(rel, _DEFAULT_EDGE_STYLE)
            net.add_edge(
                src, dst,
                color={"color": style["color"], "opacity": 0.9, "highlight": "#F5F0E6"},
                width=max(style["width"], 3),
                dashes=style["dashes"],
                arrows={"to": {"enabled": True, "scaleFactor": 0.8}},
                smooth={"type": "curvedCW", "roundness": 0.2},
            )

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            tmp_path = f.name

        # Build tooltip data map (node_id → HTML string)
        import json as _json
        _tip_map: dict[str, str] = {}
        for _nid, _nattrs in G.nodes(data=True):
            _tip_map[str(_nid)] = _node_title(_nid, _nattrs)
        _tip_json = _json.dumps(_tip_map)

        # Build edge tooltip map (src__dst → HTML string)
        _edge_tip_map: dict[str, str] = {}
        for _src, _dst, _edata in G.edges(data=True):
            _conf = _edata.get("confidence", 0.5)
            _rel  = _edata.get("relation_type", "MENTIONED_WITH")
            _ev   = _edata.get("evidence", "")
            _etip = (
                f"<b>{_rel.replace('_', ' ')}</b><br>"
                f"confidence: {_conf:.2f}  platform: {_edata.get('platform','')}"
                + (f"<br><i style='color:#ccc;font-size:11px'>{_ev[:80]}…</i>" if _ev else "")
            )
            _edge_tip_map[f"{_src}__{_dst}"] = _etip
        _etip_json = _json.dumps(_edge_tip_map)

        net.save_graph(tmp_path)
        html = Path(tmp_path).read_text(encoding="utf-8")
        Path(tmp_path).unlink(missing_ok=True)

        # ── Expose network to window scope so our JS can hook events ──────────
        # Pyvis generates:  network = new vis.Network(  (no 'var')
        html = html.replace(
            "network = new vis.Network(",
            "window.network = new vis.Network(",
            1,
        )

        # ── Dark RM base styles (hide default vis tooltip) ────────────────────
        _style_inject = """
<style>
  body { background:#0F0E0C !important; margin:0; padding:0; }
  div.vis-tooltip { display:none !important; }  /* replaced by custom overlay */
  #rm-tip {
    display:none; position:fixed; z-index:9999; pointer-events:none;
    background:#141210; color:#F5F0E6;
    border:1px solid rgba(196,163,90,0.40);
    border-radius:4px; padding:9px 12px;
    font:12px/1.55 Inter,sans-serif;
    max-width:290px; box-shadow:0 6px 24px rgba(0,0,0,.55);
  }
  #rm-tip b  { color:#F5F0E6; }
  #rm-tip a  { color:#C4A35A; text-decoration:underline; pointer-events:all; }
  #rm-tip i  { color:#aaa; }
  #rm-tip span { }
</style>"""

        # ── Custom tooltip overlay using network hover events ─────────────────
        _js_inject = f"""
<div id="rm-tip"></div>
<script>
var RM_TIPS  = {_tip_json};
var RM_ETIPS = {_etip_json};
(function waitNet() {{
  var net = window.network;
  var tip = document.getElementById('rm-tip');
  if (!net || !tip) {{ setTimeout(waitNet, 120); return; }}

  document.addEventListener('mousemove', function(e) {{
    if (tip.style.display === 'block') {{
      var x = e.clientX + 14, y = e.clientY + 14;
      if (x + 300 > window.innerWidth)  x = e.clientX - 305;
      if (y + 240 > window.innerHeight) y = e.clientY - 180;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }}
  }});

  net.on('hoverNode', function(p) {{
    var html = RM_TIPS[String(p.node)];
    if (html) {{ tip.innerHTML = html; tip.style.display = 'block'; }}
  }});
  net.on('blurNode',  function() {{ tip.style.display = 'none'; }});

  net.on('hoverEdge', function(p) {{
    var key = null;
    net.body.data.edges.forEach(function(e) {{
      if (e.id === p.edge) key = String(e.from) + '__' + String(e.to);
    }});
    var html = key && RM_ETIPS[key];
    if (html) {{ tip.innerHTML = html; tip.style.display = 'block'; }}
  }});
  net.on('blurEdge',  function() {{ tip.style.display = 'none'; }});
}})();
</script>"""

        html = html.replace("</head>", _style_inject + "\n</head>", 1)
        html = html.replace("</body>", _js_inject + "\n</body>", 1)
        return html

    except Exception as exc:
        logger.exception("network render failed")
        return f"<p style='color:red'>Error rendering network: {exc}</p>"
