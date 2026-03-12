from __future__ import annotations

import io
import json
import subprocess
import pandas as pd
import plotly.express as px
import streamlit as st

from config import load_config
from utils.database import get_leads_df, get_runs_df, init_db

st.set_page_config(page_title="Lead Dashboard", page_icon="📈", layout="wide")

config = load_config()
init_db(config.sqlite_db_path)

st.title("📈 Dashboard de Leads (SQLite)")
st.caption("Visualización, acciones y control del pipeline de scraping.")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🔄 Refrescar datos", use_container_width=True):
        st.rerun()

with col2:
    if st.button("🚀 Ejecutar scraping ahora", use_container_width=True):
        with st.spinner("Ejecutando main.py..."):
            result = subprocess.run(["python", "main.py"], capture_output=True, text=True)
        if result.returncode == 0:
            st.success("Scraping finalizado correctamente.")
        else:
            st.error("El scraping terminó con errores.")
            st.code(result.stderr or result.stdout)

with col3:
    st.info(f"Base SQLite: `{config.sqlite_db_path}`")

leads_df = get_leads_df(config.sqlite_db_path)
runs_df = get_runs_df(config.sqlite_db_path)

if leads_df.empty:
    st.warning("No hay leads cargados todavía. Ejecuta el scraping primero.")
    st.stop()

for col in ["interest_signals", "raw_data"]:
    if col in leads_df.columns:
        leads_df[col] = leads_df[col].fillna("[]")

st.subheader("Filtros")
filter_col1, filter_col2, filter_col3 = st.columns(3)

platforms = sorted([p for p in leads_df["source_platform"].dropna().unique().tolist() if p])
lead_types = sorted([p for p in leads_df["lead_type"].dropna().unique().tolist() if p])

selected_platforms = filter_col1.multiselect("Plataformas", platforms, default=platforms)
selected_types = filter_col2.multiselect("Tipo de lead", lead_types, default=lead_types[: min(8, len(lead_types))])
min_score = int(filter_col3.slider("Score mínimo", 0, 100, 40))

filtered = leads_df.copy()
if selected_platforms:
    filtered = filtered[filtered["source_platform"].isin(selected_platforms)]
if selected_types:
    filtered = filtered[filtered["lead_type"].isin(selected_types)]
filtered = filtered[filtered["score"].fillna(0) >= min_score]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Leads filtrados", len(filtered))
k2.metric("Score promedio", round(filtered["score"].fillna(0).mean(), 1) if not filtered.empty else 0)
k3.metric("Con email", int((filtered["email"].fillna("") != "").sum()))
k4.metric("Con website", int((filtered["website"].fillna("") != "").sum()))

st.subheader("Visualizaciones")
chart_col1, chart_col2 = st.columns(2)

if not filtered.empty:
    platform_counts = filtered.groupby("source_platform", as_index=False).size().rename(columns={"size": "count"})
    fig_platform = px.bar(platform_counts, x="source_platform", y="count", title="Leads por plataforma")
    chart_col1.plotly_chart(fig_platform, use_container_width=True)

    if "lead_type" in filtered.columns:
        lt_counts = filtered[filtered["lead_type"].fillna("") != ""].groupby("lead_type", as_index=False).size().rename(columns={"size": "count"})
        fig_types = px.pie(lt_counts, names="lead_type", values="count", title="Distribución por tipo de lead")
        chart_col2.plotly_chart(fig_types, use_container_width=True)

    chart_col3, chart_col4 = st.columns(2)
    fig_score = px.histogram(filtered, x="score", nbins=20, title="Distribución de score")
    chart_col3.plotly_chart(fig_score, use_container_width=True)

    country_counts = filtered[filtered["country"].fillna("") != ""].groupby("country", as_index=False).size().rename(columns={"size": "count"})
    if not country_counts.empty:
        fig_country = px.bar(country_counts.sort_values("count", ascending=False).head(10), x="country", y="count", title="Top países")
        chart_col4.plotly_chart(fig_country, use_container_width=True)

st.subheader("Tabla de leads")
show_cols = [
    "source_platform",
    "name",
    "social_handle",
    "lead_type",
    "score",
    "email",
    "website",
    "city",
    "country",
    "profile_url",
]
show_cols = [c for c in show_cols if c in filtered.columns]
st.dataframe(filtered[show_cols].sort_values("score", ascending=False), use_container_width=True)

st.subheader("Acciones de exportación")
export_col1, export_col2 = st.columns(2)

csv_bytes = filtered.to_csv(index=False).encode("utf-8")
export_col1.download_button("⬇️ Descargar CSV filtrado", data=csv_bytes, file_name="leads_filtrados.csv", mime="text/csv", use_container_width=True)

json_buffer = io.StringIO()
json.dump(filtered.to_dict(orient="records"), json_buffer, ensure_ascii=False, indent=2)
export_col2.download_button(
    "⬇️ Descargar JSON filtrado",
    data=json_buffer.getvalue().encode("utf-8"),
    file_name="leads_filtrados.json",
    mime="application/json",
    use_container_width=True,
)

st.subheader("Histórico de ejecuciones")
if runs_df.empty:
    st.info("Aún no hay ejecuciones registradas.")
else:
    st.dataframe(runs_df, use_container_width=True)
