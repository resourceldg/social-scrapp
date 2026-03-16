"""
WorldMap — renders project clusters and event locations on an interactive Folium map.

Layers
------
  Project clusters  → circle markers, radius ∝ opportunity_density,
                       color by status (active=orange, emerging=blue, completed=grey)
  Events            → star markers, color by prestige tier (A=gold, B=silver, C=grey)
  Lead density      → optional heatmap layer (HeatMap plugin)

Usage
-----
    from visualization.world_map import render_world_map_html
    html = render_world_map_html(clusters, events, leads_df)
    # st.components.v1.html(html, height=500)
"""
from __future__ import annotations

import logging

import pandas as pd

from project_engine.project_clusterer import ProjectCluster

logger = logging.getLogger(__name__)

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    _FOLIUM_OK = True
except ImportError:
    _FOLIUM_OK = False

# ── Visual constants ──────────────────────────────────────────────────────────

_STATUS_COLOR = {
    "active":    "#FF9F43",
    "emerging":  "#6C63FF",
    "completed": "#B2BEC3",
    "rumour":    "#74B9FF",
}

_PRESTIGE_COLOR = {
    "A": "#FDCB6E",   # gold
    "B": "#A29BFE",   # silver-purple
    "C": "#DFE6E9",   # light grey
    "unknown": "#DFE6E9",
}

_WORLD_CENTER = [20.0, 10.0]
_DEFAULT_ZOOM = 2


def _cluster_popup(cluster: ProjectCluster) -> str:
    rows = [
        f"<b>{cluster.project_type.replace('_',' ').title()}</b>",
        f"<i>{cluster.location_city}, {cluster.location_country}</i>",
        f"Status: {cluster.status}",
        f"Budget: {cluster.budget_tier}",
        f"Actors: {cluster.actor_count}",
        f"Opportunity density: {cluster.opportunity_density:.2f}",
        f"Confidence: {cluster.confidence:.2f}",
    ]
    if cluster.timeline_hint:
        rows.append(f"Timeline: {cluster.timeline_hint}")
    return "<br>".join(rows)


def render_world_map_html(
    clusters: list[ProjectCluster] | None = None,
    events: list[dict] | None = None,
    leads_df: pd.DataFrame | None = None,
    height: int = 480,
) -> str:
    """
    Build an interactive Folium world map.

    Parameters
    ----------
    clusters : list[ProjectCluster], optional
        ProjectClusters with lat/lon populated (or location_city for geocoding).
    events : list[dict], optional
        Dicts with keys: name, lat, lon, prestige_tier, event_type, event_date.
    leads_df : pd.DataFrame, optional
        DataFrame with 'city', 'country', 'score' columns for heatmap layer.
    height : int
        Map iframe height in pixels.

    Returns
    -------
    str
        Self-contained HTML string for embedding with st.components.v1.html().
    """
    if not _FOLIUM_OK:
        return "<p style='color:red'>folium not installed — run: pip install folium</p>"

    m = folium.Map(
        location=_WORLD_CENTER,
        zoom_start=_DEFAULT_ZOOM,
        tiles="CartoDB dark_matter",
        prefer_canvas=True,
    )

    # ── Project cluster layer ─────────────────────────────────────────────────
    if clusters:
        cluster_group = folium.FeatureGroup(name="Project Clusters", show=True)
        for c in clusters:
            lat, lon = c.lat, c.lon
            if not lat and not lon:
                continue   # skip ungeocoded clusters
            radius = max(8, min(40, int(c.opportunity_density * 50 + c.actor_count * 3)))
            color  = _STATUS_COLOR.get(c.status, "#B2BEC3")
            folium.CircleMarker(
                location=[lat, lon],
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.55,
                weight=2,
                popup=folium.Popup(_cluster_popup(c), max_width=280),
                tooltip=f"{c.project_type.title()} — {c.location_city} ({c.status})",
            ).add_to(cluster_group)
        cluster_group.add_to(m)

    # ── Event layer ───────────────────────────────────────────────────────────
    if events:
        event_group = folium.FeatureGroup(name="Events", show=True)
        for ev in events:
            lat  = ev.get("lat", 0)
            lon  = ev.get("lon", 0)
            if not lat and not lon:
                continue
            tier  = ev.get("prestige_tier", "unknown")
            color = _PRESTIGE_COLOR.get(tier, "#DFE6E9")
            popup_text = (
                f"<b>{ev.get('name','')}</b><br>"
                f"Type: {ev.get('event_type','')}<br>"
                f"Tier: {tier}<br>"
                f"Date: {ev.get('event_date','')}<br>"
                f"Participants: {ev.get('participant_count',0)}"
            )
            folium.Marker(
                location=[lat, lon],
                icon=folium.Icon(color="orange" if tier == "A" else "purple", icon="star", prefix="fa"),
                popup=folium.Popup(popup_text, max_width=220),
                tooltip=ev.get("name", "Event"),
            ).add_to(event_group)
        event_group.add_to(m)

    # ── Lead heatmap layer ────────────────────────────────────────────────────
    if leads_df is not None and not leads_df.empty:
        _CITY_COORDS: dict[str, tuple[float, float]] = {
            "miami": (25.77, -80.19), "new york": (40.71, -74.01),
            "london": (51.51, -0.13), "paris": (48.86, 2.35),
            "milan": (45.47, 9.19), "madrid": (40.42, -3.70),
            "barcelona": (41.39, 2.15), "buenos aires": (-34.61, -58.38),
            "são paulo": (-23.55, -46.63), "sao paulo": (-23.55, -46.63),
            "mexico city": (19.43, -99.13), "bogotá": (4.71, -74.07),
            "bogota": (4.71, -74.07), "santiago": (-33.46, -70.65),
            "dubai": (25.20, 55.27), "singapore": (1.35, 103.82),
            "hong kong": (22.32, 114.17), "tokyo": (35.69, 139.69),
            "sydney": (-33.87, 151.21), "amsterdam": (52.37, 4.90),
            "berlin": (52.52, 13.40), "lisbon": (38.72, -9.14),
            "istanbul": (41.01, 28.95), "rome": (41.90, 12.50),
            "florence": (43.77, 11.25), "cartagena": (10.39, -75.48),
            "lima": (-12.05, -77.04), "punta del este": (-34.96, -54.95),
            "tulum": (20.21, -87.46), "st moritz": (46.50, 9.84),
        }
        heat_data = []
        for _, row in leads_df.iterrows():
            city_key = str(row.get("city", "")).lower().strip()
            coords   = _CITY_COORDS.get(city_key)
            if coords:
                weight = max(0.1, (row.get("score", 0) or 0) / 100)
                heat_data.append([coords[0], coords[1], weight])
        if heat_data:
            HeatMap(
                heat_data, radius=18, blur=12, max_zoom=6,
                gradient={"0.2": "#6C63FF", "0.5": "#FF9F43", "1.0": "#FF6B6B"},
                name="Lead Density",
            ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    html = m._repr_html_()
    # Ensure full height
    html = html.replace('style="width: 100%;"', f'style="width: 100%; height: {height}px;"')
    return html
