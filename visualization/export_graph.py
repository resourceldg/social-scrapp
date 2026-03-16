"""
GraphExporter — serializes the NetworkGraph to standard formats.

Formats supported
-----------------
  gexf      → Gephi-compatible XML (best for external analysis)
  graphml   → Standard XML (Cytoscape, yEd)
  json      → node-link JSON (D3.js, custom frontends)
  csv       → two CSVs: nodes.csv + edges.csv (spreadsheet-friendly)

Usage
-----
    from visualization.export_graph import export_graph

    payload, filename, mime = export_graph(network_graph, fmt="gexf")
    st.download_button("Download GEXF", payload, filename, mime)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import zipfile

from network_engine.graph_builder import NetworkGraph

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    _NX_OK = True
except ImportError:
    _NX_OK = False


def export_graph(
    network_graph: NetworkGraph,
    fmt: str = "gexf",
) -> tuple[bytes, str, str]:
    """
    Export the graph to the specified format.

    Parameters
    ----------
    network_graph : NetworkGraph
    fmt : str
        One of: "gexf", "graphml", "json", "csv"

    Returns
    -------
    tuple[bytes, str, str]
        (file_bytes, filename, mime_type)
        Returns empty bytes with an error filename on failure.
    """
    if not _NX_OK:
        return b"", "error_no_networkx.txt", "text/plain"

    G = network_graph.G
    if G is None or G.number_of_nodes() == 0:
        return b"", "empty_graph.txt", "text/plain"

    fmt = fmt.lower().strip()

    try:
        if fmt == "gexf":
            buf = io.BytesIO()
            nx.write_gexf(G, buf)
            return buf.getvalue(), "social_graph.gexf", "application/xml"

        if fmt == "graphml":
            buf = io.BytesIO()
            nx.write_graphml(G, buf)
            return buf.getvalue(), "social_graph.graphml", "application/xml"

        if fmt == "json":
            data = nx.node_link_data(G)
            raw  = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            return raw, "social_graph.json", "application/json"

        if fmt == "csv":
            # nodes.csv
            node_buf = io.StringIO()
            node_fields = ["id", "type", "label", "platform", "lead_type",
                           "lead_profile", "city", "country", "score",
                           "specifier_score", "buying_power_score",
                           "event_signal_score", "opportunity_score",
                           "opportunity_classification"]
            w = csv.DictWriter(node_buf, fieldnames=node_fields, extrasaction="ignore")
            w.writeheader()
            for nid, attrs in G.nodes(data=True):
                row = {"id": nid}
                row.update(attrs)
                w.writerow(row)

            # edges.csv
            edge_buf = io.StringIO()
            edge_fields = ["source", "target", "relation_type", "confidence", "platform", "evidence"]
            ew = csv.DictWriter(edge_buf, fieldnames=edge_fields, extrasaction="ignore")
            ew.writeheader()
            for src, dst, edata in G.edges(data=True):
                ew.writerow({"source": src, "target": dst, **edata})

            # Zip both
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("nodes.csv", node_buf.getvalue())
                zf.writestr("edges.csv", edge_buf.getvalue())
            return zip_buf.getvalue(), "social_graph.zip", "application/zip"

    except Exception as exc:
        logger.exception("Graph export failed (fmt=%s): %s", fmt, exc)

    return b"", "export_error.txt", "text/plain"
