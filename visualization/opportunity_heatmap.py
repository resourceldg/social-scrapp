"""
OpportunityHeatmap — Plotly heatmap of opportunity score × geography × lead type.

Returns a Plotly Figure ready for st.plotly_chart().

Usage
-----
    from visualization.opportunity_heatmap import render_opportunity_heatmap
    fig = render_opportunity_heatmap(leads_df)
    st.plotly_chart(fig, use_container_width=True)
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def render_opportunity_heatmap(
    leads_df: pd.DataFrame,
    score_col: str = "opportunity_score",
    city_col: str = "city",
    type_col: str = "lead_type",
    top_cities: int = 15,
    top_types: int = 10,
) -> go.Figure:
    """
    Build a heatmap: cities (y) × lead types (x) coloured by avg opportunity_score.

    Falls back to 'score' column if opportunity_score is absent or all-zero.

    Parameters
    ----------
    leads_df : pd.DataFrame
    score_col : str
    city_col : str
    type_col : str
    top_cities : int
    top_types : int

    Returns
    -------
    go.Figure
    """
    df = leads_df.copy()

    # Fallback to base score if opportunity_score missing / all zero
    if score_col not in df.columns or df[score_col].fillna(0).sum() == 0:
        score_col = "score"

    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)

    # Filter rows with valid city and lead_type
    df = df[
        df[city_col].notna() & (df[city_col] != "") &
        df[type_col].notna() & (df[type_col] != "")
    ].copy()

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No hay datos suficientes para el heatmap.<br>Enriquece leads y asegúrate de tener ciudad y tipo detectados.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=13, color="#B2BEC3"),
        )
        fig.update_layout(
            paper_bgcolor="#1E1E2E", plot_bgcolor="#1E1E2E",
            height=350, margin=dict(l=10, r=10, t=30, b=10),
        )
        return fig

    # Top cities by lead count
    top_city_list = (
        df[city_col].value_counts().head(top_cities).index.tolist()
    )
    # Top lead types by count
    top_type_list = (
        df[type_col].value_counts().head(top_types).index.tolist()
    )

    df_filt = df[df[city_col].isin(top_city_list) & df[type_col].isin(top_type_list)]

    pivot = (
        df_filt.groupby([city_col, type_col])[score_col]
        .mean()
        .round(1)
        .unstack(fill_value=0)
        .reindex(index=top_city_list, columns=top_type_list, fill_value=0)
    )

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c).replace("_", " ").title() for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[
            [0.0, "#1E1E2E"],
            [0.3, "#6C63FF"],
            [0.6, "#FF9F43"],
            [1.0, "#FF6B6B"],
        ],
        zmin=0, zmax=100,
        hoverongaps=False,
        hovertemplate="<b>%{y}</b> · %{x}<br>Avg opp. score: %{z:.0f}<extra></extra>",
        colorbar=dict(
            title="Avg Score",
            tickvals=[0, 25, 50, 75, 100],
            thickness=12,
            len=0.8,
        ),
    ))

    fig.update_layout(
        title=dict(
            text="Opportunity Score · Ciudad × Tipo de Lead",
            font=dict(color="#CDD6F4", size=14),
            x=0.01,
        ),
        paper_bgcolor="#1E1E2E",
        plot_bgcolor="#1E1E2E",
        font=dict(color="#CDD6F4"),
        xaxis=dict(tickangle=-35, tickfont=dict(size=11)),
        yaxis=dict(tickfont=dict(size=11)),
        margin=dict(l=10, r=10, t=50, b=60),
        height=max(300, min(600, 40 * len(top_city_list) + 100)),
    )
    return fig
