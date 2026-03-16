from __future__ import annotations

import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import set_key

from config import load_config
from feedback.feedback_analyzer import analyze_conversions
from feedback.feedback_store import FeedbackStore
from models import Lead
from scoring.score_engine import ScoreEngine
from scoring.weights_config import RankingMode
from utils.database import (
    get_leads_df,
    get_runs_df,
    init_db,
    update_lead_status,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Lead Intelligence · Rare & Magic", page_icon="◆", layout="wide")

ENV_PATH = Path(".env")

# ── Rare & Magic Design System ─────────────────────────────────────────────────
_RM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Gilda+Display&family=Inter:wght@300;400;500&display=swap');

/* ── Variables ──────────────────────────────────────────────────────────────── */
:root {
    --rm-bg:          #0F0E0C;
    --rm-bg-card:     #141210;
    --rm-bg-elevated: #1C1A17;
    --rm-fg:          #F5F0E6;
    --rm-fg-muted:    rgba(245,240,230,0.65);
    --rm-fg-subtle:   rgba(245,240,230,0.38);
    --rm-gold:        #C4A35A;
    --rm-gold-dim:    rgba(196,163,90,0.15);
    --rm-gold-hover:  rgba(196,163,90,0.25);
    --rm-rust:        #A0522D;
    --rm-warm-gray:   #6B6560;
    --rm-border:      rgba(245,240,230,0.07);
    --rm-border-md:   rgba(245,240,230,0.14);
    --rm-border-hi:   rgba(245,240,230,0.22);
    --rm-radius:      3px;
    --rm-green:       #5C9E6E;
    --rm-red:         #C0546A;
}

/* ── Base & Background ──────────────────────────────────────────────────────── */
html, body { background-color: var(--rm-bg) !important; }

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background-color: var(--rm-bg) !important;
    font-family: 'Inter', sans-serif !important;
}

section.main {
    background-color: var(--rm-bg) !important;
}

section.main > div.block-container {
    background-color: var(--rm-bg) !important;
    padding-top: 1.75rem !important;
    padding-bottom: 3rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 1440px !important;
}

/* ── Scrollbar — visible & styled ──────────────────────────────────────────── */
::-webkit-scrollbar               { width: 7px; height: 7px; }
::-webkit-scrollbar-track         { background: var(--rm-bg); }
::-webkit-scrollbar-thumb         { background: #3A3530; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover   { background: var(--rm-warm-gray); }
::-webkit-scrollbar-corner        { background: var(--rm-bg); }

/* ── Streamlit header bar ───────────────────────────────────────────────────── */
[data-testid="stHeader"] {
    background-color: var(--rm-bg) !important;
    border-bottom: 1px solid var(--rm-border) !important;
}
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"]    { right: 2rem !important; }

/* ── Typography ─────────────────────────────────────────────────────────────── */
h1, h2, h3, h4 {
    font-family: 'Gilda Display', serif !important;
    color: var(--rm-fg) !important;
    letter-spacing: 0.03em !important;
    font-weight: 400 !important;
    line-height: 1.25 !important;
}
h1 { font-size: 2rem !important; }
h2 { font-size: 1.5rem !important; }
h3 { font-size: 1.2rem !important; }
h4 { font-size: 1rem !important; }

p, li {
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.65 !important;
    color: var(--rm-fg) !important;
}

/* caption */
[data-testid="stCaptionContainer"] p,
.stCaption {
    color: var(--rm-fg-muted) !important;
    font-size: 13px !important;
    letter-spacing: 0.025em !important;
}

/* markdown body */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    font-size: 15px !important;
    color: var(--rm-fg) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--rm-border) !important;
    gap: 0 !important;
    padding: 0 !important;
    margin-bottom: 1.5rem !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--rm-fg-subtle) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    padding: 0.8rem 1.2rem !important;
    border: none !important;
    border-radius: 0 !important;
    transition: color 0.2s ease !important;
    white-space: nowrap !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--rm-fg) !important;
    background: transparent !important;
}

.stTabs [aria-selected="true"] {
    color: var(--rm-gold) !important;
    background: transparent !important;
}

.stTabs [data-baseweb="tab-highlight"] {
    background-color: var(--rm-gold) !important;
    height: 2px !important;
}

.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* ── Metric cards ────────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: var(--rm-bg-card) !important;
    border: 1px solid var(--rm-border) !important;
    border-radius: var(--rm-radius) !important;
    padding: 1.25rem 1.5rem !important;
    transition: border-color 0.25s ease !important;
}
[data-testid="metric-container"]:hover {
    border-color: var(--rm-border-md) !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stMetricLabel"] p {
    color: var(--rm-fg-muted) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
    color: var(--rm-gold) !important;
    font-family: 'Gilda Display', serif !important;
    font-size: 2.2rem !important;
    letter-spacing: 0.02em !important;
}
[data-testid="stMetricDelta"] svg { display: none !important; }
[data-testid="stMetricDeltaIcon-Up"]   { color: var(--rm-green) !important; }
[data-testid="stMetricDeltaIcon-Down"] { color: var(--rm-red) !important; }

/* ── Expanders ───────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--rm-bg-card) !important;
    border: 1px solid var(--rm-border) !important;
    border-radius: var(--rm-radius) !important;
    margin-bottom: 0.5rem !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] details summary {
    color: var(--rm-fg) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    padding: 0.9rem 1.1rem !important;
    letter-spacing: 0.02em !important;
    transition: color 0.2s ease !important;
}
[data-testid="stExpander"] details summary:hover {
    color: var(--rm-gold) !important;
}
[data-testid="stExpander"] details[open] summary {
    border-bottom: 1px solid var(--rm-border) !important;
}
[data-testid="stExpander"] details > div {
    background: var(--rm-bg-card) !important;
    padding: 1rem !important;
}

/* ── Text inputs ─────────────────────────────────────────────────────────────── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background: var(--rm-bg-elevated) !important;
    border: 1px solid var(--rm-border-md) !important;
    border-radius: var(--rm-radius) !important;
    color: var(--rm-fg) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    padding: 0.6rem 0.875rem !important;
    transition: border-color 0.2s ease !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--rm-gold) !important;
    box-shadow: 0 0 0 2px rgba(196,163,90,0.18) !important;
    outline: none !important;
}
.stTextArea textarea {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 13px !important;
}

/* ── Selectbox / Multiselect ─────────────────────────────────────────────────── */
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {
    background: var(--rm-bg-elevated) !important;
    border: 1px solid var(--rm-border-md) !important;
    border-radius: var(--rm-radius) !important;
    color: var(--rm-fg) !important;
    font-size: 14px !important;
    transition: border-color 0.2s ease !important;
}
.stSelectbox [data-baseweb="select"] > div:focus-within,
.stMultiSelect [data-baseweb="select"] > div:focus-within {
    border-color: var(--rm-gold) !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] input {
    color: var(--rm-fg) !important;
    font-size: 14px !important;
    background: transparent !important;
}
[data-baseweb="popover"] > div {
    background: var(--rm-bg-elevated) !important;
    border: 1px solid var(--rm-border-md) !important;
    border-radius: var(--rm-radius) !important;
}
[data-baseweb="menu"] li {
    color: var(--rm-fg) !important;
    font-size: 14px !important;
    background: transparent !important;
    padding: 0.5rem 1rem !important;
}
[data-baseweb="menu"] li:hover,
[data-baseweb="option"]:hover {
    background: var(--rm-gold-hover) !important;
    color: var(--rm-fg) !important;
}
/* multiselect tags */
[data-baseweb="tag"] {
    background: var(--rm-gold-dim) !important;
    border: 1px solid rgba(196,163,90,0.3) !important;
    border-radius: 2px !important;
}
[data-baseweb="tag"] span { color: var(--rm-gold) !important; font-size: 12px !important; }

/* ── Buttons ─────────────────────────────────────────────────────────────────── */
.stButton > button {
    background: transparent !important;
    border: 1px solid var(--rm-gold) !important;
    border-radius: var(--rm-radius) !important;
    color: var(--rm-gold) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.2s ease !important;
    white-space: nowrap !important;
}
.stButton > button:hover {
    background: var(--rm-gold) !important;
    color: #1A1A1A !important;
    box-shadow: none !important;
}
.stButton > button:focus {
    outline: 2px solid var(--rm-gold) !important;
    outline-offset: 2px !important;
    box-shadow: none !important;
}
/* primary variant */
.stButton > button[kind="primary"] {
    background: var(--rm-gold) !important;
    color: #1A1A1A !important;
}
.stButton > button[kind="primary"]:hover {
    background: #F5F0E6 !important;
    border-color: #F5F0E6 !important;
}
/* download button same style */
.stDownloadButton > button {
    background: transparent !important;
    border: 1px solid var(--rm-border-hi) !important;
    color: var(--rm-fg-muted) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    border-radius: var(--rm-radius) !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.2s ease !important;
}
.stDownloadButton > button:hover {
    border-color: var(--rm-gold) !important;
    color: var(--rm-gold) !important;
    background: transparent !important;
}

/* ── Alerts ──────────────────────────────────────────────────────────────────── */
[data-testid="stNotification"],
.stAlert {
    background: var(--rm-bg-card) !important;
    border-radius: var(--rm-radius) !important;
    font-size: 14px !important;
    border-left: 3px solid var(--rm-gold) !important;
    border-top: 1px solid var(--rm-border) !important;
    border-right: 1px solid var(--rm-border) !important;
    border-bottom: 1px solid var(--rm-border) !important;
}
[data-testid="stNotification"] p { font-size: 14px !important; }
/* info = gold, success = green, warning = rust, error = red */
div[data-testid="stNotification"][data-type="info"]    { border-left-color: var(--rm-gold) !important; }
div[data-testid="stNotification"][data-type="success"] { border-left-color: var(--rm-green) !important; }
div[data-testid="stNotification"][data-type="warning"] { border-left-color: var(--rm-rust) !important; }
div[data-testid="stNotification"][data-type="error"]   { border-left-color: var(--rm-red) !important; }

/* ── Dataframe ───────────────────────────────────────────────────────────────── */
[data-testid="stDataFrameResizable"] {
    border: 1px solid var(--rm-border) !important;
    border-radius: var(--rm-radius) !important;
    overflow: hidden !important;
}
.stDataFrame thead th {
    background: var(--rm-bg-elevated) !important;
    color: var(--rm-fg-muted) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid var(--rm-border-md) !important;
}
.stDataFrame tbody tr:hover td {
    background: var(--rm-gold-dim) !important;
}
.stDataFrame td {
    font-size: 14px !important;
    color: var(--rm-fg) !important;
}

/* ── Slider ──────────────────────────────────────────────────────────────────── */
[data-baseweb="slider"] div[role="slider"] {
    background: var(--rm-gold) !important;
    border: 2px solid var(--rm-gold) !important;
}
[data-baseweb="slider"] div[data-testid="stTickBar"] > div {
    color: var(--rm-fg-muted) !important;
    font-size: 12px !important;
}

/* ── Progress bar ────────────────────────────────────────────────────────────── */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, var(--rm-gold), #D4B570) !important;
}
.stProgress > div > div {
    background: var(--rm-bg-elevated) !important;
    border-radius: 2px !important;
}

/* ── Checkbox & Radio ────────────────────────────────────────────────────────── */
.stCheckbox label, .stRadio label {
    font-size: 14px !important;
    color: var(--rm-fg) !important;
}
.stCheckbox [data-baseweb="checkbox"] input:checked ~ div {
    background: var(--rm-gold) !important;
    border-color: var(--rm-gold) !important;
}

/* ── Form labels ─────────────────────────────────────────────────────────────── */
.stSelectbox label,
.stMultiSelect label,
.stTextInput label,
.stSlider label,
.stNumberInput label,
.stTextArea label,
.stCheckbox > label > div[data-testid="stMarkdownContainer"] p,
.stRadio label > div > p {
    color: var(--rm-fg-muted) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    margin-bottom: 0.4rem !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid var(--rm-border) !important;
    margin: 1.5rem 0 !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--rm-bg-card) !important;
    border-right: 1px solid var(--rm-border) !important;
}
[data-testid="stSidebar"] * { color: var(--rm-fg) !important; }

/* ── Dialog / Modal ──────────────────────────────────────────────────────────── */
[data-testid="stDialog"] > div,
div[role="dialog"] {
    background: var(--rm-bg-card) !important;
    border: 1px solid var(--rm-border-md) !important;
    border-radius: 6px !important;
    box-shadow: 0 24px 48px rgba(0,0,0,0.6) !important;
}
[data-testid="stDialog"] h1,
[data-testid="stDialog"] h2,
div[role="dialog"] h1,
div[role="dialog"] h2 {
    font-family: 'Gilda Display', serif !important;
    color: var(--rm-fg) !important;
}
div[role="dialog"] > div > div:first-child {
    border-bottom: 1px solid var(--rm-border) !important;
    padding-bottom: 0.75rem !important;
    margin-bottom: 0.75rem !important;
}
/* Modal close button */
[data-testid="stDialog"] button[aria-label="Close"],
div[role="dialog"] button[aria-label="Close"] {
    color: var(--rm-fg-muted) !important;
    background: transparent !important;
    border: none !important;
    font-size: 1.25rem !important;
    transition: color 0.2s ease !important;
}
[data-testid="stDialog"] button[aria-label="Close"]:hover {
    color: var(--rm-fg) !important;
}

/* ── Toast / status messages ─────────────────────────────────────────────────── */
[data-testid="stToast"] {
    background: var(--rm-bg-elevated) !important;
    border: 1px solid var(--rm-border-md) !important;
    border-radius: var(--rm-radius) !important;
    color: var(--rm-fg) !important;
}

/* ── Lead table: st.dataframe row highlight ───────────────────────────────────── */
[data-testid="stDataFrameResizable"] iframe {
    background: var(--rm-bg) !important;
}

/* ── Section subheaders inside tabs ─────────────────────────────────────────── */
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 {
    color: var(--rm-fg-muted) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.15em !important;
    text-transform: uppercase !important;
    font-family: 'Inter', sans-serif !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid var(--rm-border) !important;
}

/* ── Plotly chart container background ───────────────────────────────────────── */
[data-testid="stPlotlyChart"] {
    background: transparent !important;
    border: 1px solid var(--rm-border) !important;
    border-radius: var(--rm-radius) !important;
    overflow: hidden !important;
}

/* ── Info/warning/success/error boxes ────────────────────────────────────────── */
[data-testid="stAlertContainer"] {
    background: var(--rm-bg-card) !important;
    border-radius: var(--rm-radius) !important;
    font-size: 14px !important;
}

/* ── Responsive: tighter padding on narrower screens ─────────────────────────── */
@media (max-width: 768px) {
    section.main > div.block-container {
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 11px !important;
        padding: 0.65rem 0.75rem !important;
    }
}

/* ── Code blocks ─────────────────────────────────────────────────────────────── */
code, pre {
    background: var(--rm-bg-elevated) !important;
    border: 1px solid var(--rm-border) !important;
    border-radius: var(--rm-radius) !important;
    color: var(--rm-gold) !important;
    font-size: 13px !important;
}

/* ── Spinner ─────────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div > div {
    border-top-color: var(--rm-gold) !important;
}

/* ── st.columns gap ──────────────────────────────────────────────────────────── */
[data-testid="column"] { padding: 0 0.5rem !important; }
[data-testid="column"]:first-child { padding-left: 0 !important; }
[data-testid="column"]:last-child  { padding-right: 0 !important; }

/* ── Selection color ─────────────────────────────────────────────────────────── */
::selection {
    background: rgba(196,163,90,0.28) !important;
    color: var(--rm-fg) !important;
}

/* ── Smooth scroll ───────────────────────────────────────────────────────────── */
html { scroll-behavior: smooth; }

/* ── Custom header ───────────────────────────────────────────────────────────── */
.rm-header {
    padding: 0 0 1.75rem 0;
    border-bottom: 1px solid var(--rm-border);
    margin-bottom: 0.25rem;
}
.rm-eyebrow {
    font-family: 'Inter', sans-serif !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.25em !important;
    text-transform: uppercase !important;
    color: var(--rm-gold) !important;
    margin: 0 0 0.75rem 0 !important;
}
.rm-title {
    font-family: 'Gilda Display', serif !important;
    font-size: 2.4rem !important;
    font-weight: 400 !important;
    color: var(--rm-fg) !important;
    letter-spacing: 0.03em !important;
    margin: 0 0 0.5rem 0 !important;
    line-height: 1.2 !important;
}
.rm-subtitle {
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    color: var(--rm-fg-muted) !important;
    letter-spacing: 0.04em !important;
    margin: 0 !important;
}
"""

config = load_config()
init_db(config.sqlite_db_path)

# Inject theme immediately after DB init (must be before any other st.* calls)
st.markdown(f"<style>{_RM_CSS}</style>", unsafe_allow_html=True)

# Custom header — replaces st.title + st.caption
st.markdown("""
<div class="rm-header">
    <p class="rm-eyebrow">Commercial Intelligence</p>
    <h1 class="rm-title">Lead Intelligence</h1>
    <p class="rm-subtitle">Arte contemporáneo &nbsp;·&nbsp; Collectible design &nbsp;·&nbsp; Interiorismo &nbsp;·&nbsp; Arquitectura &nbsp;·&nbsp; Hospitalidad</p>
</div>
""", unsafe_allow_html=True)

tab_opp, tab_analisis, tab_mapa, tab_red, tab_discovery, tab_feedback, tab_sistema, tab_prog, tab_config, tab_docs = st.tabs([
    "Oportunidades", "Análisis", "Mapa", "Red", "Discovery",
    "Feedback", "Sistema", "Programación", "Configuración", "Documentación"
])

# ── Cron / process utilities (used by tab_prog) ────────────────────────────────

_ROOT      = Path(__file__).parent.resolve()   # absolute path to project dir
_LOCK_FILE = _ROOT / ".scrape.lock"
_LOG_DIR   = _ROOT / "logs"
_SCRIPT    = _ROOT / "run_scrape.sh"
_DAYS_ES   = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
# cron DOW: 0=Sunday … 6=Saturday; we map to display Mon-Sun → cron 1-7 (7≡0)
_DAY_TO_CRON = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}  # idx_mon0 → cron dow
_CRON_TO_IDX = {v: k for k, v in _DAY_TO_CRON.items()}       # cron dow → idx_mon0


def _get_scrape_status() -> tuple[bool, int | None, float | None]:
    """Returns (is_running, pid, elapsed_seconds_or_None)."""
    if not _LOCK_FILE.exists():
        return False, None, None
    try:
        pid = int(_LOCK_FILE.read_text().strip())
        os.kill(pid, 0)          # raises OSError if dead
        proc_mtime = _LOCK_FILE.stat().st_mtime
        elapsed = time.time() - proc_mtime
        return True, pid, elapsed
    except (ValueError, OSError):
        return False, None, None


def _kill_scrape(pid: int) -> bool:
    """SIGTERM to the process group (kills Chrome children too).

    Validates that the target PID is actually one of our scraper processes
    before sending the signal, to avoid killing an unrelated process if the
    PID was reused by the OS.
    """
    # Verify the process cmdline contains our script before killing
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        if "main.py" not in cmdline and "run_scrape" not in cmdline and "python" not in cmdline.lower():
            return False
    except OSError:
        return False
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        return True
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except OSError:
            return False


def _read_crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(text: str) -> bool:
    r = subprocess.run(["crontab", "-"], input=text, capture_output=True, text=True)
    return r.returncode == 0


def _parse_scraper_crons(crontab: str) -> list[dict]:
    """Parse our scraper cron lines into structured dicts."""
    entries = []
    for line in crontab.splitlines():
        line = line.strip()
        if "run_scrape.sh" not in line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s+(\d+)\s+\*\s+\*\s+([\d,]+)\s+.*run_scrape\.sh(.*)$", line)
        if m:
            minute, hour, dow_str, args = m.groups()
            dow_list = [int(d) for d in dow_str.split(",") if d.strip().isdigit()]
            entries.append({
                "minute":  int(minute),
                "hour":    int(hour),
                "dow":     dow_list,
                "args":    args.strip().replace(">> /dev/null 2>&1", "").strip(),
                "raw":     line,
            })
    return entries


_ALLOWED_CRON_ARG = re.compile(
    r"^(--scrape-only|--enrich-only|--enrich-max=\d{1,4}|--enrich-min-score=\d{1,3})"
    r"(\s+(--scrape-only|--enrich-only|--enrich-max=\d{1,4}|--enrich-min-score=\d{1,3}))*$"
)


def _sanitize_cron_args(args: str) -> str:
    """Whitelist-validate cron args to prevent shell injection.

    Only known run_scrape.sh flags are accepted.  Raises ValueError on
    anything that doesn't match the whitelist.
    """
    stripped = args.strip()
    if not stripped:
        return ""
    if not _ALLOWED_CRON_ARG.match(stripped):
        raise ValueError(
            f"Argumento de cron no válido: {stripped!r}. "
            "Solo se permiten: --scrape-only, --enrich-only, "
            "--enrich-max=N, --enrich-min-score=N"
        )
    return stripped


def _build_cron_line(hour: int, minute: int, days_cron: list[int], args: str) -> str:
    dow = ",".join(str(d) for d in sorted(days_cron))
    safe_dir = shlex.quote(str(_ROOT))
    cmd = f"cd {safe_dir} && ./run_scrape.sh"
    safe_args = _sanitize_cron_args(args)
    if safe_args:
        cmd += f" {safe_args}"
    cmd += " >> /dev/null 2>&1"
    return f"{minute} {hour} * * {dow}  {cmd}"


def _replace_scraper_crons(crontab: str, new_lines: list[str]) -> str:
    """Remove old scraper block and append new_lines."""
    result = []
    for line in crontab.splitlines():
        if "run_scrape.sh" in line:
            continue
        if "── Social Scraper" in line or "Social Scraper ──" in line:
            continue
        result.append(line)
    # Strip trailing blanks
    while result and result[-1].strip() == "":
        result.pop()
    if new_lines:
        result.append("")
        result.append("# ── Social Scraper ──────────────────────────────────────────────────────────")
        result.extend(new_lines)
    return "\n".join(result) + "\n"


def _get_latest_log() -> tuple[str | None, str]:
    """Return (filename, last-N-lines) of the most recent log.
    Prefers session logs; falls back to output/scraper.log."""
    if _LOG_DIR.exists():
        logs = sorted(_LOG_DIR.glob("session_*.log"), reverse=True)
        if logs:
            try:
                lines = logs[0].read_text(errors="replace").splitlines()
                return logs[0].name, "\n".join(lines[-80:])
            except Exception:
                return logs[0].name, ""
    fallback = _ROOT / "output" / "scraper.log"
    if fallback.exists():
        try:
            lines = fallback.read_text(errors="replace").splitlines()
            return "output/scraper.log", "\n".join(lines[-80:])
        except Exception:
            pass
    return None, ""


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _dow_cron_to_idx(dow_list: list[int]) -> list[int]:
    """Convert cron DOW list → Monday-0 index list for display."""
    return sorted({_CRON_TO_IDX[d] for d in dow_list if d in _CRON_TO_IDX})


_PLATFORM_ICONS: dict[str, str] = {
    "instagram": "📸",
    "linkedin":  "💼",
    "twitter":   "🐦",
    "facebook":  "📘",
    "pinterest": "📌",
    "reddit":    "🤖",
    "behance":   "🎨",
}

_PHASE_LABELS: dict[str, str] = {
    "starting":    "Iniciando proceso…",
    "scraping":    "Scraping de plataformas",
    "enrichment":  "Enriquecimiento de perfiles",
    "done":        "Sesión completada",
}


def _read_latest_log_full() -> str:
    """
    Return the full content of the most recent log.
    Prefers logs/session_*.log (written by run_scrape.sh banner + Python stdout).
    Falls back to output/scraper.log (Python RotatingFileHandler, direct runs).
    """
    if _LOG_DIR.exists():
        logs = sorted(_LOG_DIR.glob("session_*.log"), reverse=True)
        if logs:
            try:
                return logs[0].read_text(errors="replace")
            except Exception:
                pass
    fallback = _ROOT / "output" / "scraper.log"
    if fallback.exists():
        try:
            return fallback.read_text(errors="replace")
        except Exception:
            pass
    return ""


def _parse_progress(log_content: str, enabled_platforms: list[str]) -> dict:
    """
    Parse log content to infer scraping progress.
    Returns dict with: phase, pct (0.0–1.0), platforms_done, current_platform,
    lead_counts, enabled_platforms, has_enrich_start, has_session_done.
    """
    lines = log_content.splitlines() if log_content else []

    has_scrape_start  = False
    has_enrich_start  = False
    has_enrich_done   = False
    has_session_done  = False

    platforms_done:   list[str]      = []
    lead_counts:      dict[str, int] = {}
    current_platform: str | None     = None

    for line in lines:
        ll = line.lower()
        # run_scrape.sh banner markers
        if "=== scraping start ===" in ll:
            has_scrape_start = True
        elif "=== enrichment start ===" in ll:
            has_enrich_start = True
        elif "=== enrichment completed ok ===" in ll:
            has_enrich_done = True
        elif "=== session done ===" in ll:
            has_session_done = True
        # Python logger markers (direct runs without run_scrape.sh)
        elif "network speed:" in ll or "scheduler plan" in ll:
            has_scrape_start = True
        elif "enrichment start" in ll or "enrich.py" in ll:
            has_enrich_start = True
        elif "enrichment completed" in ll or "==== lead generation summary ====" in ll:
            has_session_done = True

        # Detect platform completion: "[instagram] returned N raw leads"
        for plat in enabled_platforms:
            tag = f"[{plat}] returned"
            if tag in ll and plat not in platforms_done:
                platforms_done.append(plat)
                try:
                    part = ll.split(tag)[1].strip().split()[0]
                    lead_counts[plat] = int(part)
                except (IndexError, ValueError):
                    lead_counts[plat] = 0
            # Detect which platform is currently being scraped
            elif f"[{plat}]" in ll and plat not in platforms_done:
                current_platform = plat

    n       = len(enabled_platforms)
    n_done  = len(platforms_done)

    if has_session_done:
        pct, phase = 1.0, "done"
    elif has_enrich_done:
        pct, phase = 0.95, "enrichment"
    elif has_enrich_start:
        pct, phase = 0.72, "enrichment"
    elif has_scrape_start and n > 0:
        pct   = 0.05 + (n_done / n) * 0.62
        phase = "scraping"
    elif has_scrape_start:
        pct, phase = 0.05, "scraping"
    else:
        pct, phase = 0.02, "starting"

    return {
        "phase":             phase,
        "pct":               pct,
        "platforms_done":    platforms_done,
        "current_platform":  current_platform if not has_enrich_start else None,
        "lead_counts":       lead_counts,
        "enabled_platforms": enabled_platforms,
        "has_enrich_start":  has_enrich_start,
        "has_session_done":  has_session_done,
    }

# ── Constants ──────────────────────────────────────────────────────────────────
_STATUSES = ["nuevo", "contactado", "respondió", "cerrado", "descartado"]

_LEAD_TYPE_LABELS: dict[str, str] = {
    # ── English keys (legacy / enriched profiles) ──────────────────────────────
    "interior_designer":     "Interiorista",
    "architect":             "Arquitecto/a",
    "art_consultant":        "Consultor/a de Arte",
    "gallery_director":      "Director/a de Galería",
    "gallery":               "Galería",
    "real_estate_developer": "Promotor Inmobiliario",
    "hospitality_designer":  "Diseñador/a de Hospitalidad",
    "furniture_designer":    "Diseñador/a de Mobiliario",
    "collector":             "Coleccionista",
    "curator":               "Curador/a",
    "art_director":          "Director/a Artístico/a",
    "design_studio":         "Estudio de Diseño",
    "hospitality":           "Hospitalidad",
    "unknown":               "Sin clasificar",
    # ── Spanish keys from classifiers.py (actual scraper output) ───────────────
    "coleccionista":         "Coleccionista",
    "arquitecto":            "Arquitecto/a",
    "interiorista":          "Interiorista",
    "galeria":               "Galería",
    "curador":               "Curador/a",
    "diseñador":             "Diseñador/a",
    "estudio":               "Estudio de Diseño",
    "hotel":                 "Hotel / Resort",
    "restaurante":           "Restaurante / Gastronomía",
    "tienda decoracion":     "Tienda de Decoración",
    "artista":               "Artista",
    "maker":                 "Maker / Artesano",
    "marca premium":         "Marca Premium",
    "desarrollador":         "Desarrollador Inmobiliario",
}

_RANKING_MODES: dict[str, tuple[str, str]] = {
    "outreach_priority":    ("⚡ Outreach",         "Equilibrio contactabilidad + relevancia + intención. Ideal para cold outreach."),
    "authority_first":      ("👑 Autoridad",         "Prioriza alcance e influencia. Ideal para colaboraciones de marca."),
    "premium_fit_first":    ("💎 Premium",           "Prioriza coleccionistas y compradores premium de alto valor."),
    "contactability_first": ("📬 Contactabilidad",   "Los más fáciles de contactar hoy — tienen email o web disponible."),
    "brand_relevance":      ("🎨 Relevancia",        "Prioriza la afinidad temática con arte, diseño e interiorismo de lujo."),
    "specifier_network":    ("🏛 Especificadores",   "Arquitectos, diseñadores e interioristas que prescriben compras."),
    "hot_project_detection": ("🔥 Proyectos activos", "Oportunidades con señales de proyecto activo o intención inmediata."),
}

_LEAD_PROFILES: dict[str, dict] = {
    "project_actor": {
        "label": "🔥 Proyecto activo",
        "description": "Involucrado en un proyecto en curso — timing real, oportunidad inmediata",
        "priority": 1,
    },
    "buyer": {
        "label": "💰 Comprador directo",
        "description": "Puede comprar piezas para sí mismo o su espacio — venta directa potencial",
        "priority": 2,
    },
    "specifier": {
        "label": "🏛 Prescriptor",
        "description": "Decide qué arte/diseño se usa en proyectos de clientes — ventas recurrentes indirectas",
        "priority": 3,
    },
    "influencer": {
        "label": "👑 Autoridad",
        "description": "Amplifica visibilidad y abre puertas en el ecosistema — no compra directo",
        "priority": 4,
    },
    "gallery_node": {
        "label": "🖼 Nodo del ecosistema",
        "description": "Galería, plataforma o actor de distribución — referencia, no comprador",
        "priority": 5,
    },
    "aspirational": {
        "label": "✨ Ecosistema afín",
        "description": "Habita el mundo del arte/diseño sin señal de compra o prescripción clara",
        "priority": 6,
    },
}


def _profile_label(profile_key: str) -> str:
    return _LEAD_PROFILES.get(profile_key or "aspirational", _LEAD_PROFILES["aspirational"])["label"]


def _profile_description(profile_key: str) -> str:
    return _LEAD_PROFILES.get(profile_key or "aspirational", _LEAD_PROFILES["aspirational"])["description"]


_OPP_CLASS_LABELS: dict[str, str] = {
    "active_project":    "🔥 Proyecto activo — oportunidad inmediata",
    "direct_buyer":      "💰 Comprador directo potencial",
    "specifier_network": "🏛 Especificador — prescribe compras",
    "strategic_partner": "🤝 Socio estratégico — influencia a largo plazo",
    "low_signal":        "📌 Señal baja — potencial sin confirmar",
}

# ── Helper functions ───────────────────────────────────────────────────────────

def _score_label(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "· Mínima"
    if s >= 50:
        return "🔥 Top"
    if s >= 38:
        return "⚡ Alta"
    if s >= 25:
        return "📌 Media"
    if s >= 10:
        return "○ Baja"
    return "· Mínima"


def _confidence_dots(conf: float) -> str:
    try:
        c = float(conf)
    except (TypeError, ValueError):
        c = 0.0
    filled = round(c * 5)
    filled = max(0, min(5, filled))
    return "●" * filled + "○" * (5 - filled)


def _lead_type_label(lt: str) -> str:
    if not lt:
        return "Sin clasificar"
    return _LEAD_TYPE_LABELS.get(lt, lt.replace("_", " ").title())


def _confidence_from_row(row: pd.Series) -> float:
    score = 0.0
    bio = str(row.get("bio") or "")
    if len(bio) > 20:
        score += 0.25
    followers = row.get("followers")
    if followers is not None and str(followers).strip() not in ("", "None", "nan", "0"):
        score += 0.20
    email = str(row.get("email") or "")
    website = str(row.get("website") or "")
    if email.strip() or website.strip():
        score += 0.25
    name = str(row.get("name") or "")
    handle = str(row.get("social_handle") or "")
    if name.strip() and handle.strip() and name.strip().lower() != handle.strip().lower():
        score += 0.15
    lead_type = str(row.get("lead_type") or "")
    if lead_type.strip() and lead_type.strip() != "unknown":
        score += 0.10
    country = str(row.get("country") or "")
    if country.strip():
        score += 0.05
    return min(score, 1.0)


def _row_to_lead_json(row: pd.Series) -> str:
    d = row.to_dict()
    for key in ["interest_signals", "raw_data"]:
        val = d.get(key)
        if isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                d[key] = [] if key == "interest_signals" else {}
        elif val is None:
            d[key] = [] if key == "interest_signals" else {}
    # Convert non-serialisable types
    for k, v in list(d.items()):
        if pd.isna(v) if not isinstance(v, (list, dict)) else False:
            d[k] = None
    return json.dumps(d, sort_keys=True, default=str)


@st.cache_data(ttl=600, show_spinner=False)
def _compute_score_breakdown(lead_json: str, mode_value: str) -> dict:
    try:
        d = json.loads(lead_json)
        signals = d.get("interest_signals") or []
        if isinstance(signals, str):
            try:
                signals = json.loads(signals)
            except Exception:
                signals = []

        lead = Lead(
            source_platform=d.get("source_platform") or "",
            search_term=d.get("search_term") or "",
            name=d.get("name") or "",
            social_handle=d.get("social_handle") or "",
            profile_url=d.get("profile_url") or "",
            email=d.get("email") or "",
            phone=d.get("phone") or "",
            website=d.get("website") or "",
            city=d.get("city") or "",
            country=d.get("country") or "",
            bio=d.get("bio") or "",
            category=d.get("category") or "",
            lead_type=d.get("lead_type") or "",
            interest_signals=signals if isinstance(signals, list) else [],
            followers=d.get("followers"),
            engagement_hint=d.get("engagement_hint") or "",
            score=int(d.get("score") or 0),
            raw_data=d.get("raw_data") or {},
        )
        engine = ScoreEngine(mode=RankingMode(mode_value))
        result = engine.score(lead)
        return {
            "final_score": result.final_score,
            "contactability_score": result.contactability_score,
            "relevance_score": result.relevance_score,
            "authority_score": result.authority_score,
            "commercial_intent_score": result.commercial_intent_score,
            "premium_fit_score": result.premium_fit_score,
            "platform_specific_score": result.platform_specific_score,
            "data_quality_score": result.data_quality_score,
            "buying_power_score": result.buying_power_score,
            "specifier_score": result.specifier_score,
            "project_signal_score": result.project_signal_score,
            "opportunity_score": result.opportunity_score,
            "lead_classification": result.lead_classification,
            "opportunity_classification": result.opportunity_classification,
            "signal_density": result.signal_density,
            "spam_risk": result.spam_risk,
            "reasons": result.reasons,
            "warnings": result.warnings,
            "confidence": result.confidence,
            "ranking_mode": result.ranking_mode,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _action_suggestion(result: dict) -> str:
    spam = float(result.get("spam_risk") or 0)
    conf = float(result.get("confidence") or 0)
    score = int(result.get("final_score") or 0)
    opp = result.get("opportunity_classification") or ""

    if spam >= 60:
        return "🚨 Verificar autenticidad antes de contactar — señales de cuenta no auténtica."
    if conf < 0.3:
        return "🔍 Enriquecer primero — poco contexto para evaluar. Usar 'Completar perfiles'."
    if opp == "active_project":
        return "🔥 Prioridad máxima — señales de proyecto activo. Contactar esta semana."
    if opp == "direct_buyer" and score >= 45:
        return "💰 Comprador directo potencial. Proponer reunión o presentar portfolio."
    if opp == "specifier_network":
        return "🏛 Especificador de compras. Enviar portfolio con fichas técnicas."
    if score >= 50:
        return "⚡ Alta prioridad. Contactar por email o web esta semana."
    if score >= 38:
        return "📬 Buena oportunidad. Preparar propuesta personalizada."
    if score >= 25:
        return "📌 Observar — enriquecer antes de contactar."
    return "○ Señal baja. Monitorear si aparecen más datos."


def _reason_label(r: str) -> str:
    r = r.strip()
    if r.startswith("core: "):
        term = r[len("core: "):]
        return f"✓ Menciona '{term}' — nicho core del producto"
    if r.startswith("adjacent: "):
        term = r[len("adjacent: "):]
        return f"✓ Relacionado con '{term}' — sector afín"
    if r.startswith("classified as: "):
        lt = r[len("classified as: "):]
        return f"✓ Clasificado como: {_lead_type_label(lt)}"
    if r.startswith("target country: "):
        country = r[len("target country: "):]
        return f"✓ País objetivo: {country}"
    if r == "email available":
        return "✓ Email disponible — contactable directamente"
    if r == "website available":
        return "✓ Tiene sitio web propio"
    if r == "phone available":
        return "✓ Teléfono disponible"
    if r == "linkedin profile referenced":
        return "✓ Perfil de LinkedIn referenciado"
    if r == "professional domain detected":
        return "✓ Dominio profesional (.studio, .design, .gallery…)"
    if r.startswith("followers: "):
        n = r[len("followers: "):]
        return f"✓ Audiencia: {n}"
    if r == "engagement data present":
        return "✓ Datos de engagement disponibles"
    if r.startswith("intent: "):
        term = r[len("intent: "):]
        return f"✓ Señal de intención: '{term}'"
    if r.startswith("premium: "):
        term = r[len("premium: "):]
        return f"✓ Indicador premium: '{term}'"
    if r.startswith("semantic similarity: "):
        val = r[len("semantic similarity: "):]
        return f"✓ Alta similitud semántica con perfil ideal ({val})"
    return f"✓ {r}"


def _warning_label(w: str) -> str:
    w = w.strip()
    _WARN_MAP = {
        "no contact info":            "⚠ Sin información de contacto disponible",
        "no bio":                      "⚠ Perfil sin bio — difícil de evaluar",
        "low follower count":          "⚠ Audiencia reducida",
        "spam signals detected":       "⚠ Señales de spam detectadas — verificar autenticidad",
        "generic account name":        "⚠ Nombre de cuenta genérico",
        "no location data":            "⚠ Sin datos de ubicación",
        "possible bot":                "⚠ Posible cuenta automatizada",
        "low engagement":              "⚠ Engagement bajo en relación a seguidores",
        "unclassified lead type":      "⚠ Tipo de profesional no identificado",
        "no interest signals":         "⚠ Sin señales de interés detectadas",
    }
    return _WARN_MAP.get(w.lower(), f"⚠ {w}")


def _fmt_signals(v) -> str:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return v
    if isinstance(v, list):
        return ", ".join(str(x) for x in v[:5])
    return str(v) if v else ""


# ── Lead detail modal ─────────────────────────────────────────────────────────

def _safe_str(v) -> str:
    """Return empty string for None/NaN/nan, otherwise str(v)."""
    if v is None:
        return ""
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    s = str(v)
    return "" if s in ("nan", "None", "NaT") else s


# ── Plotly Rare & Magic theme + geo helpers ────────────────────────────────────

def _rm_layout(height: int = 360) -> dict:
    """Return Plotly layout kwargs matching the Rare & Magic dark theme."""
    _axis = dict(
        gridcolor="rgba(245,240,230,0.06)", linecolor="rgba(245,240,230,0.10)",
        tickfont=dict(color="rgba(245,240,230,0.60)", size=11),
        zerolinecolor="rgba(245,240,230,0.08)",
    )
    return dict(
        paper_bgcolor="#141210", plot_bgcolor="#0F0E0C",
        font=dict(family="Inter, sans-serif", color="#F5F0E6", size=12),
        title=dict(font=dict(family="Gilda Display, serif", color="#F5F0E6", size=14), x=0.02),
        xaxis=_axis, yaxis=_axis, height=height,
        margin=dict(l=16, r=16, t=44, b=16),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(245,240,230,0.10)",
            font=dict(color="rgba(245,240,230,0.75)", size=11),
        ),
    )


def _rm_chart_header(title: str, eyebrow: str = "") -> None:
    _eb = (
        f'<p style="font:500 11px/1 Inter,sans-serif;letter-spacing:.22em;'
        f'text-transform:uppercase;color:#C4A35A;margin:0 0 .4rem">{eyebrow}</p>'
        if eyebrow else ""
    )
    st.markdown(
        f'<div style="margin:1.25rem 0 .6rem">{_eb}'
        f'<h3 style="font:400 1.05rem/1.2 \'Gilda Display\',serif;color:#F5F0E6;margin:0">{title}</h3>'
        f'</div>',
        unsafe_allow_html=True,
    )


_CITY_COORDS: dict = {
    "miami": (25.77, -80.19), "new york": (40.71, -74.00), "los angeles": (34.05, -118.24),
    "london": (51.51, -0.13), "paris": (48.85, 2.35), "milan": (45.46, 9.19),
    "barcelona": (41.38, 2.17), "madrid": (40.42, -3.70), "dubai": (25.20, 55.27),
    "singapore": (1.35, 103.82), "hong kong": (22.32, 114.17), "tokyo": (35.68, 139.69),
    "sydney": (-33.87, 151.21), "toronto": (43.65, -79.38),
    "mexico city": (19.43, -99.13), "ciudad de mexico": (19.43, -99.13),
    "buenos aires": (-34.60, -58.38), "são paulo": (-23.55, -46.63),
    "sao paulo": (-23.55, -46.63), "rio de janeiro": (-22.91, -43.17),
    "bogotá": (4.71, -74.07), "bogota": (4.71, -74.07),
    "santiago": (-33.46, -70.65), "lima": (-12.05, -77.04),
    "amsterdam": (52.37, 4.90), "berlin": (52.52, 13.40),
    "vienna": (48.21, 16.37), "rome": (41.90, 12.50),
    "florence": (43.77, 11.26), "lisbon": (38.72, -9.14),
    "cape town": (-33.93, 18.42), "tel aviv": (32.08, 34.78),
    "istanbul": (41.01, 28.95), "doha": (25.29, 51.53),
    "tulum": (20.21, -87.46), "punta del este": (-34.97, -54.95),
    "miami beach": (25.79, -80.13), "guadalajara": (20.66, -103.35),
    "montevideo": (-34.90, -56.19), "medellin": (6.24, -75.58),
    "monterrey": (25.67, -100.31), "ibiza": (38.91, 1.43),
    "zurich": (47.38, 8.54), "geneva": (46.20, 6.15),
}


@st.dialog("🔍 Detalle del lead", width="large")
def _lead_detail_modal(row: pd.Series, selected_mode: str, db_path) -> None:
    name     = _safe_str(row.get("name")) or "Sin nombre"
    handle   = _safe_str(row.get("social_handle"))
    platform = _safe_str(row.get("source_platform"))
    lt       = _lead_type_label(_safe_str(row.get("lead_type")))
    score    = int(row.get("score") or 0)
    country  = _safe_str(row.get("country"))
    city     = _safe_str(row.get("city"))

    # Header
    _loc_parts = [p for p in [city, country] if p]
    st.markdown(f"## {name}")
    _caption_parts = [p for p in [f"@{handle}" if handle else None, lt, platform,
                                   ", ".join(_loc_parts) if _loc_parts else None] if p]
    st.caption(" · ".join(_caption_parts))

    # Perfil de negocio
    _lead_profile_key = _safe_str(row.get("lead_profile")) or "aspirational"
    _prof_label = _profile_label(_lead_profile_key)
    _prof_desc  = _profile_description(_lead_profile_key)
    st.info(f"**{_prof_label}** — {_prof_desc}")

    # Score metrics row
    _lead_json = _row_to_lead_json(row)
    _result    = _compute_score_breakdown(_lead_json, selected_mode)

    if "error" not in _result:
        m1, m2, m3, m4 = st.columns(4)
        _mode_label = _RANKING_MODES.get(selected_mode, ("Score", ""))[0]
        m1.metric(f"Score · {_mode_label}", _result.get("final_score", score))
        m2.metric("Oportunidad",  _result.get("opportunity_score", 0))
        m3.metric("Confianza",    _confidence_dots(float(_result.get("confidence") or 0)))
        m4.metric("Spam risk",    f"{float(_result.get('spam_risk') or 0):.0f}")

        _opp = _result.get("opportunity_classification") or ""
        st.info(f"**Clasificación:** {_OPP_CLASS_LABELS.get(_opp, _opp)}   |   "
                f"**Acción:** {_action_suggestion(_result)}")
    else:
        st.warning(f"No se pudo calcular el scoring: {_result['error']}")

    # Contact info
    _email = _safe_str(row.get("email"))
    _phone = _safe_str(row.get("phone"))
    _web   = _safe_str(row.get("website"))
    _url   = _safe_str(row.get("profile_url"))
    if any([_email, _phone, _web, _url]):
        st.divider()
        st.markdown("**Contacto**")
        _cc = st.columns(4)
        if _email: _cc[0].markdown(f"📧 {_email}")
        if _phone: _cc[1].markdown(f"📞 {_phone}")
        if _web:   _cc[2].markdown(f"🌐 [{_web}]({_web})")
        if _url:   _cc[3].markdown(f"🔗 [Ver perfil]({_url})")

    # Bio
    _bio = _safe_str(row.get("bio"))
    if _bio:
        st.divider()
        st.markdown("**Bio**")
        st.markdown(f"_{_bio}_")

    # Estado — editable with explicit save button
    st.divider()
    _cur_status = _safe_str(row.get("status")) or "nuevo"
    if _cur_status not in _STATUSES:
        _cur_status = "nuevo"
    _sc1, _sc2 = st.columns([3, 1])
    _new_status = _sc1.selectbox(
        "Estado del lead",
        options=_STATUSES,
        index=_STATUSES.index(_cur_status),
        key=f"modal_status_{_url or name}",
    )
    if _sc2.button("Guardar", type="primary", key=f"save_status_{_url or name}"):
        if _url:
            update_lead_status(db_path, _url, _new_status)
            st.session_state["_leads_tbl_prev_sel"] = None  # allow reopening on next click
            st.success(f"Estado actualizado a **{_new_status}**.")
            st.rerun()

    if "error" in _result:
        return

    # Dimension chart
    st.divider()
    _dims = [
        ("Contactabilidad",     _result.get("contactability_score",   0)),
        ("Relevancia",          _result.get("relevance_score",        0)),
        ("Autoridad",           _result.get("authority_score",        0)),
        ("Intención comercial", _result.get("commercial_intent_score",0)),
        ("Premium fit",         _result.get("premium_fit_score",      0)),
        ("Poder adquisitivo",   _result.get("buying_power_score",     0)),
        ("Especificador",       _result.get("specifier_score",        0)),
        ("Señal de proyecto",   _result.get("project_signal_score",   0)),
    ]
    _dv = [float(d[1] or 0) for d in _dims]
    _dc = ["#1a6b3c" if v >= 60 else "#f0a500" if v >= 30 else "#9ca3af" for v in _dv]
    _fig = go.Figure(go.Bar(
        x=_dv, y=[d[0] for d in _dims], orientation="h",
        marker_color=_dc,
        text=[f"{v:.0f}" for v in _dv], textposition="outside",
    ))
    _fig.update_layout(
        title="Dimensiones de scoring",
        xaxis=dict(range=[0, 115], title="Puntuación (0–100)"),
        height=280, margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(_fig, use_container_width=True)

    # Reasons + warnings
    _rc, _wc = st.columns(2)
    with _rc:
        st.markdown("**Señales positivas**")
        for r in (_result.get("reasons") or [])[:10]:
            st.markdown(_reason_label(r))
    with _wc:
        st.markdown("**Advertencias**")
        _warns = _result.get("warnings") or []
        if _warns:
            for w in _warns:
                st.markdown(_warning_label(w))
        else:
            st.markdown("_Sin advertencias_")


# ── Export function ────────────────────────────────────────────────────────────

def _build_export(df: pd.DataFrame, profile: str) -> tuple[bytes, str, str]:
    def _safe_col(frame: pd.DataFrame, old: str, new: str) -> dict:
        if old in frame.columns:
            return {old: new}
        return {}

    if profile == "outreach":
        mask = pd.Series([True] * len(df), index=df.index)
        if "email" in df.columns and "website" in df.columns:
            mask = (df["email"].fillna("").str.strip() != "") | (df["website"].fillna("").str.strip() != "")
        if "score" in df.columns:
            mask = mask & (df["score"].fillna(0) >= 50)  # umbral "Top" (antes 60, muy restrictivo)
        sub = df[mask].copy()
        col_map = {}
        col_map.update(_safe_col(sub, "name", "nombre"))
        col_map.update(_safe_col(sub, "phone", "telefono"))
        col_map.update(_safe_col(sub, "website", "sitio_web"))
        col_map.update(_safe_col(sub, "lead_type", "tipo_de_profesional"))
        col_map.update(_safe_col(sub, "source_platform", "red_social"))
        col_map.update(_safe_col(sub, "profile_url", "enlace_perfil"))
        col_map.update(_safe_col(sub, "country", "pais"))
        col_map.update(_safe_col(sub, "city", "ciudad"))
        sub = sub.rename(columns=col_map)
        if "tipo_de_profesional" in sub.columns:
            sub["tipo_de_profesional"] = sub["tipo_de_profesional"].apply(_lead_type_label)
        want = [v for v in ["nombre", "email", "telefono", "sitio_web", "tipo_de_profesional",
                             "red_social", "enlace_perfil", "score", "pais", "ciudad"] if v in sub.columns]
        out = sub[want]
        return out.to_csv(index=False).encode("utf-8"), "outreach_leads.csv", "text/csv"

    if profile == "crm":
        col_map = {}
        col_map.update(_safe_col(df, "name", "Nombre"))
        col_map.update(_safe_col(df, "email", "Email"))
        col_map.update(_safe_col(df, "phone", "Telefono"))
        col_map.update(_safe_col(df, "website", "Web"))
        col_map.update(_safe_col(df, "source_platform", "Red Social"))
        col_map.update(_safe_col(df, "social_handle", "Handle"))
        col_map.update(_safe_col(df, "profile_url", "URL Perfil"))
        col_map.update(_safe_col(df, "lead_type", "Tipo"))
        col_map.update(_safe_col(df, "country", "Pais"))
        col_map.update(_safe_col(df, "city", "Ciudad"))
        col_map.update(_safe_col(df, "score", "Score"))
        col_map.update(_safe_col(df, "followers", "Seguidores"))
        col_map.update(_safe_col(df, "bio", "Bio"))
        sub = df.rename(columns=col_map)
        want = [v for v in ["Nombre", "Email", "Telefono", "Web", "Red Social", "Handle",
                             "URL Perfil", "Tipo", "Pais", "Ciudad", "Score", "Seguidores", "Bio"]
                if v in sub.columns]
        return sub[want].to_csv(index=False).encode("utf-8"), "leads_crm.csv", "text/csv"

    if profile == "research":
        col_map = {}
        col_map.update(_safe_col(df, "name", "nombre"))
        col_map.update(_safe_col(df, "social_handle", "handle"))
        col_map.update(_safe_col(df, "source_platform", "plataforma"))
        col_map.update(_safe_col(df, "profile_url", "url_perfil"))
        col_map.update(_safe_col(df, "lead_type", "tipo"))
        col_map.update(_safe_col(df, "score", "score"))
        col_map.update(_safe_col(df, "followers", "seguidores"))
        col_map.update(_safe_col(df, "bio", "bio"))
        col_map.update(_safe_col(df, "interest_signals", "señales"))
        col_map.update(_safe_col(df, "country", "pais"))
        col_map.update(_safe_col(df, "city", "ciudad"))
        col_map.update(_safe_col(df, "website", "sitio_web"))
        col_map.update(_safe_col(df, "email", "email"))
        col_map.update(_safe_col(df, "scrape_count", "veces_visto"))
        col_map.update(_safe_col(df, "created_at", "creado_en"))
        sub = df.rename(columns=col_map)
        want = [v for v in ["nombre", "handle", "plataforma", "url_perfil", "tipo", "score",
                             "seguidores", "bio", "señales", "pais", "ciudad", "sitio_web",
                             "email", "veces_visto", "creado_en"] if v in sub.columns]
        return sub[want].to_csv(index=False).encode("utf-8"), "leads_investigacion.csv", "text/csv"

    if profile == "executive":
        top20 = df.nlargest(20, "score").reset_index(drop=True) if "score" in df.columns else df.head(20).reset_index(drop=True)
        top20.insert(0, "Ranking", range(1, len(top20) + 1))
        if "score" in top20.columns:
            top20["Prioridad"] = top20["score"].apply(_score_label)
        else:
            top20["Prioridad"] = ""
        if "email" in top20.columns and "website" in top20.columns:
            def _contacto(r):
                if str(r.get("email") or "").strip():
                    return "Email"
                if str(r.get("website") or "").strip():
                    return "Web"
                return "Solo red social"
            top20["Contacto"] = top20.apply(_contacto, axis=1)
        else:
            top20["Contacto"] = ""
        col_map = {}
        col_map.update(_safe_col(top20, "name", "Nombre"))
        col_map.update(_safe_col(top20, "lead_type", "Tipo"))
        col_map.update(_safe_col(top20, "source_platform", "Plataforma"))
        col_map.update(_safe_col(top20, "score", "Score"))
        col_map.update(_safe_col(top20, "status", "Estado"))
        col_map.update(_safe_col(top20, "country", "Pais"))
        sub = top20.rename(columns=col_map)
        if "Tipo" in sub.columns:
            sub["Tipo"] = sub["Tipo"].apply(_lead_type_label)
        want = [v for v in ["Ranking", "Nombre", "Tipo", "Plataforma", "Score",
                             "Prioridad", "Estado", "Contacto", "Pais"] if v in sub.columns]
        return sub[want].to_csv(index=False).encode("utf-8"), "leads_ejecutivo_top20.csv", "text/csv"

    if profile == "full":
        records = df.to_dict(orient="records")
        data = json.dumps(records, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        return data, "leads_completo.json", "application/json"

    return b"", "leads.csv", "text/csv"


# ══════════════════════════════════════════════════════════════════════════════
# TAB: 🎯 Oportunidades
# ══════════════════════════════════════════════════════════════════════════════
with tab_opp:

    # ── Action row ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔄 Actualizar vista", width="stretch"):
            st.rerun()

    with col2:
        if st.button("🚀 Ejecutar scraping", width="stretch"):
            _script_abs = Path(__file__).parent / "run_scrape.sh"
            if not _script_abs.exists():
                st.error(f"No se encontró run_scrape.sh. Ve a **⏰ Programación** para ejecutar manualmente.")
            else:
                try:
                    subprocess.Popen(
                        ["bash", str(_script_abs)],
                        cwd=str(Path(__file__).parent),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    time.sleep(2)
                    st.success("✅ Scraping iniciado en segundo plano. Ve a **⏰ Programación** para ver el progreso.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al iniciar el proceso: {exc}")

    with col3:
        if st.button("🔬 Completar perfiles", width="stretch",
                     help="Visita los perfiles top para extraer followers, bio real, email y web. Mejora el ranking."):
            _script_abs = Path(__file__).parent / "run_scrape.sh"
            if not _script_abs.exists():
                st.error("No se encontró run_scrape.sh.")
            else:
                try:
                    subprocess.Popen(
                        ["bash", str(_script_abs), "--enrich-only"],
                        cwd=str(Path(__file__).parent),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    time.sleep(2)
                    st.success("✅ Enriquecimiento iniciado en segundo plano. Ve a **⏰ Programación** para ver el progreso.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al iniciar: {exc}")

    with col4:
        _runs_info = get_runs_df(config.sqlite_db_path)
        if not _runs_info.empty:
            _last_run = _runs_info.iloc[-1]
            _last_time = _last_run.get("finished_at") or _last_run.get("started_at") or "?"
            _last_count = _last_run.get("total_deduped_leads") or _last_run.get("total_raw_leads") or "?"
            st.info(f"Última ejecución: **{_last_time}**\nLeads: **{_last_count}**")
        else:
            st.info("Aún no hay ejecuciones registradas.")

    st.divider()

    # ── Load data ──────────────────────────────────────────────────────────────
    leads_df = get_leads_df(config.sqlite_db_path)

    if leads_df.empty:
        st.warning(
            "**No hay leads en la base de datos todavía.**\n\n"
            "Para empezar:\n"
            "1. Ve a **⚙️ Configuración** y activa las plataformas que quieres usar.\n"
            "2. Añade keywords relevantes (ej: `#interiordesign`, `luxury interiors`).\n"
            "3. Pulsa **🚀 Ejecutar scraping** aquí arriba.\n\n"
            "El proceso tarda entre 10 y 30 minutos según las plataformas seleccionadas."
        )

    for _col in ["interest_signals", "raw_data"]:
        if _col in leads_df.columns:
            leads_df[_col] = leads_df[_col].fillna("[]" if _col == "interest_signals" else "{}")

    if "status" not in leads_df.columns:
        leads_df["status"] = "nuevo"
    else:
        leads_df["status"] = leads_df["status"].fillna("nuevo")

    leads_df["_confidence"] = leads_df.apply(_confidence_from_row, axis=1)

    # ── Ranking mode selector ──────────────────────────────────────────────────
    st.subheader("Modo de ranking")
    _mode_options = list(_RANKING_MODES.keys())
    _mode_labels = [_RANKING_MODES[m][0] for m in _mode_options]
    _selected_mode_idx = st.selectbox(
        "¿Qué te importa más ahora?",
        options=range(len(_mode_options)),
        format_func=lambda i: _mode_labels[i],
        index=0,
    )
    selected_mode = _mode_options[_selected_mode_idx]
    st.caption(_RANKING_MODES[selected_mode][1])

    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────────
    st.subheader("Filtros y búsqueda")
    f1, f2, f3, f4, f5 = st.columns(5)

    _platforms = sorted([p for p in leads_df["source_platform"].dropna().unique().tolist() if p])
    _lead_types = sorted([p for p in leads_df["lead_type"].dropna().unique().tolist() if p])
    _profile_keys = [k for k in _LEAD_PROFILES.keys()
                     if k in leads_df.get("lead_profile", pd.Series(dtype=str)).unique().tolist()]
    _profile_keys_sorted = sorted(_profile_keys, key=lambda k: _LEAD_PROFILES[k]["priority"])

    # Empty multiselect = no filter (show all)
    selected_platforms = f1.multiselect("Plataformas", _platforms, default=[],
                                         placeholder="Todas las plataformas")
    selected_profiles = f2.multiselect(
        "Perfil de negocio",
        _profile_keys_sorted,
        default=[],
        format_func=_profile_label,
        placeholder="Todos los perfiles",
    )
    selected_types = f3.multiselect(
        "Tipo de profesional",
        _lead_types,
        default=[],
        format_func=_lead_type_label,
        placeholder="Todos los tipos",
    )
    min_score = int(f4.slider(
        "Score mínimo",
        0, 100, 0,
        help="0–9: mínima · 10–24: baja · 25–37: media · 38–49: alta · 50+: top",
    ))
    selected_statuses = f5.multiselect(
        "Estado",
        _STATUSES,
        default=[],
        placeholder="Todos los estados",
    )

    # Quick filter row
    qf1, qf2, qf3, qf4, qf5 = st.columns(5)
    filter_email = qf1.checkbox("📬 Con email")
    filter_website = qf2.checkbox("🌐 Con website")
    filter_enriched = qf3.checkbox("🔬 Enriquecidos")
    filter_recurrent = qf4.checkbox("🔁 Recurrentes")
    search_text = qf5.text_input("🔍 Buscar", placeholder="nombre, bio, email…")

    # Apply filters — empty multiselect means "show all" (no filter applied)
    filtered = leads_df.copy()

    if selected_platforms:
        filtered = filtered[filtered["source_platform"].isin(selected_platforms)]
    if selected_profiles and "lead_profile" in filtered.columns:
        filtered = filtered[filtered["lead_profile"].fillna("aspirational").isin(selected_profiles)]
    if selected_types:
        # Include leads whose lead_type matches OR is null/empty (unclassified)
        _type_mask = filtered["lead_type"].isin(selected_types)
        filtered = filtered[_type_mask]
    if selected_statuses:
        filtered = filtered[filtered["status"].isin(selected_statuses)]
    if min_score > 0:
        filtered = filtered[filtered["score"].fillna(0) >= min_score]

    if filter_email and "email" in filtered.columns:
        filtered = filtered[filtered["email"].fillna("").str.strip() != ""]
    if filter_website and "website" in filtered.columns:
        filtered = filtered[filtered["website"].fillna("").str.strip() != ""]
    if filter_enriched and "enriched_at" in filtered.columns:
        filtered = filtered[filtered["enriched_at"].fillna("").str.strip() != ""]
    if filter_recurrent and "scrape_count" in filtered.columns:
        filtered = filtered[filtered["scrape_count"].fillna(1) > 1]

    if search_text.strip():
        q = search_text.strip().lower()
        _search_cols = ["name", "social_handle", "bio", "email", "website", "lead_type"]
        _masks = [
            filtered[c].fillna("").str.lower().str.contains(q, regex=False)
            for c in _search_cols if c in filtered.columns
        ]
        if _masks:
            combined = _masks[0]
            for m in _masks[1:]:
                combined = combined | m
            filtered = filtered[combined]

    filtered = filtered.sort_values("score", ascending=False).reset_index(drop=True)

    st.divider()

    # ── Priority zones ─────────────────────────────────────────────────────────
    st.subheader("Zonas de prioridad")
    pz1, pz2, pz3, pz4, pz5 = st.columns(5)
    _sc = filtered["score"].fillna(0)
    _top_count   = int((_sc >= 50).sum())
    _alta_count  = int(((_sc >= 38) & (_sc < 50)).sum())
    _media_count = int(((_sc >= 25) & (_sc < 38)).sum())
    _baja_count  = int(((_sc >= 10) & (_sc < 25)).sum())
    _contact_count = 0
    if "email" in filtered.columns and "website" in filtered.columns:
        _contact_count = int(
            ((filtered["email"].fillna("").str.strip() != "") |
             (filtered["website"].fillna("").str.strip() != "")).sum()
        )
    pz1.metric("🟢 Top",           _top_count,     help="Score ≥ 50. Contactar esta semana.")
    pz2.metric("🟡 Alta",          _alta_count,    help="Score 38–49. Preparar propuesta personalizada.")
    pz3.metric("📌 Media",         _media_count,   help="Score 25–37. Enriquecer antes de contactar.")
    pz4.metric("○ Baja",           _baja_count,    help="Score 10–24. Monitorear si aparecen más datos.")
    pz5.metric("📬 Contacto directo", _contact_count, help="Tienen email o web disponible — contactables hoy.")

    st.divider()

    # ── Lead table (compact) ───────────────────────────────────────────────────
    # Drop rows with no usable identity
    _id_cols = [c for c in ["name", "social_handle", "profile_url"] if c in filtered.columns]
    if _id_cols:
        filtered = filtered[
            filtered[_id_cols].fillna("").apply(lambda r: any(v.strip() for v in r), axis=1)
        ]

    st.subheader(f"Leads detectados ({len(filtered)})")
    st.caption("Haz clic en una fila para abrir el detalle completo.")

    def _score_badge(s: int) -> str:
        if s >= 50: return "🟢 Top"
        if s >= 38: return "🟡 Alta"
        if s >= 25: return "📌 Media"
        if s >= 10: return "○ Baja"
        return             "· Mínima"

    # Compact display table — only the columns useful for quick scanning
    _cdf = filtered[
        [c for c in ["score", "status", "name", "social_handle", "lead_profile",
                     "lead_type", "source_platform", "email", "website", "country", "_confidence"]
         if c in filtered.columns]
    ].copy().reset_index(drop=True)

    _cdf.insert(0, "#", range(1, len(_cdf) + 1))

    if "score" in _cdf.columns:
        _cdf.insert(2, "Prioridad", _cdf["score"].apply(_score_badge))

    # Contacto: muestra icono si hay email o web
    def _contacto_icon(r):
        icons = []
        if str(r.get("email") or "").strip(): icons.append("📧")
        if str(r.get("website") or "").strip(): icons.append("🌐")
        return " ".join(icons) if icons else "—"

    _cdf["Contacto"] = _cdf.apply(_contacto_icon, axis=1)
    _cdf["_confidence"] = _cdf["_confidence"].apply(_confidence_dots) if "_confidence" in _cdf.columns else "—"

    # Lead type → label legible
    if "lead_type" in _cdf.columns:
        _cdf["lead_type"] = _cdf["lead_type"].apply(lambda x: _lead_type_label(str(x or "")))

    # Lead profile → label con emoji
    if "lead_profile" in _cdf.columns:
        _cdf["lead_profile"] = _cdf["lead_profile"].apply(
            lambda x: _profile_label(str(x or "aspirational"))
        )

    _cdf_cols_final = [c for c in
        ["#", "score", "Prioridad", "status", "name", "social_handle",
         "lead_profile", "lead_type", "source_platform", "Contacto", "country", "_confidence"]
        if c in _cdf.columns]
    _cdf = _cdf[_cdf_cols_final]

    _compact_cfg = {
        "#":               st.column_config.NumberColumn("#",            format="%d",  width="small"),
        "score":           st.column_config.NumberColumn("Score ★",     format="%d",  width="small"),
        "Prioridad":       st.column_config.TextColumn(  "Prioridad",                 width="small"),
        "status":          st.column_config.TextColumn(  "Estado",                    width="small"),
        "name":            st.column_config.TextColumn(  "Nombre",                    width="medium"),
        "social_handle":   st.column_config.TextColumn(  "Handle",                    width="medium"),
        "lead_profile":    st.column_config.TextColumn(  "Perfil",                    width="medium"),
        "lead_type":       st.column_config.TextColumn(  "Tipo",                      width="medium"),
        "source_platform": st.column_config.TextColumn(  "Red",                       width="small"),
        "Contacto":        st.column_config.TextColumn(  "Contacto",                  width="small"),
        "country":         st.column_config.TextColumn(  "País",                      width="small"),
        "_confidence":     st.column_config.TextColumn(  "Confianza",                 width="small"),
    }
    _compact_cfg = {k: v for k, v in _compact_cfg.items() if k in _cdf.columns}

    _tbl_sel = st.dataframe(
        _cdf,
        column_config=_compact_cfg,
        hide_index=True,
        use_container_width=True,
        height=460,
        on_select="rerun",
        selection_mode="single-row",
        key="leads_table_opp",
    )

    # Open modal when a NEW row is selected.
    # We track the previously-seen selection in session state so that closing
    # the dialog (X button) doesn't immediately reopen it on the next rerun.
    _sel_rows = _tbl_sel.selection.rows if hasattr(_tbl_sel, "selection") else []
    _curr_sel = _sel_rows[0] if _sel_rows else None
    _prev_sel = st.session_state.get("_leads_tbl_prev_sel")

    if _curr_sel is not None and _curr_sel != _prev_sel:
        # New row clicked → remember it and open modal
        st.session_state["_leads_tbl_prev_sel"] = _curr_sel
        if _curr_sel < len(filtered):
            _lead_detail_modal(filtered.iloc[_curr_sel], selected_mode, config.sqlite_db_path)
    elif _curr_sel is None:
        # Selection cleared (user clicked away) → reset so next click on same row works
        st.session_state["_leads_tbl_prev_sel"] = None

    st.divider()

    # ── Export section ─────────────────────────────────────────────────────────
    st.subheader("📤 Exportar leads")
    st.caption("Cada exportación está optimizada para un uso distinto.")

    # Pre-compute exports
    _exp_outreach = _build_export(filtered, "outreach")
    _exp_crm      = _build_export(filtered, "crm")
    _exp_research  = _build_export(filtered, "research")
    _exp_executive = _build_export(filtered, "executive")
    _exp_full      = _build_export(filtered, "full")

    # Count leads in outreach export for visibility
    import io as _io
    _outreach_count = len(pd.read_csv(_io.BytesIO(_exp_outreach[0]))) if _exp_outreach[0] else 0

    ec1, ec2, ec3, ec4, ec5 = st.columns(5)
    ec1.download_button(
        f"📤 Outreach ({_outreach_count})",
        data=_exp_outreach[0], file_name=_exp_outreach[1], mime=_exp_outreach[2],
        help="Leads con email o web y score ≥ 50 (prioridad Top). Listos para contactar.",
        width="stretch",
    )
    ec2.download_button(
        "🗂 CRM",
        data=_exp_crm[0], file_name=_exp_crm[1], mime=_exp_crm[2],
        help="Campos limpios para HubSpot, Notion, Airtable o Salesforce.",
        width="stretch",
    )
    ec3.download_button(
        "🔍 Investigación",
        data=_exp_research[0], file_name=_exp_research[1], mime=_exp_research[2],
        help="Lista completa con bio y señales para análisis manual.",
        width="stretch",
    )
    ec4.download_button(
        "📊 Ejecutivo",
        data=_exp_executive[0], file_name=_exp_executive[1], mime=_exp_executive[2],
        help="Top 20 leads. Sin datos técnicos. Para compartir con el equipo.",
        width="stretch",
    )
    ec5.download_button(
        "🛠 Completo (JSON)",
        data=_exp_full[0], file_name=_exp_full[1], mime=_exp_full[2],
        help="Todos los campos. Para análisis técnico.",
        width="stretch",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: 📊 Análisis
# ══════════════════════════════════════════════════════════════════════════════
with tab_analisis:
    _all_leads = get_leads_df(config.sqlite_db_path)

    # Para métricas de calidad solo usamos leads ya enriquecidos (score fiable).
    # Los no enriquecidos tienen score ~2 pre-enriquecimiento y distorsionan
    # promedios, medianas y distribuciones.
    if "enriched_at" in _all_leads.columns:
        _enriched_leads = _all_leads[_all_leads["enriched_at"].fillna("").str.strip() != ""]
    else:
        _enriched_leads = _all_leads
    _enriched_all = len(_enriched_leads)

    _scores_all = _enriched_leads["score"].fillna(0)  # solo scores post-enriquecimiento

    if _all_leads.empty:
        st.warning(
            "**No hay leads para analizar todavía.**\n\n"
            "Ejecuta el scraping desde la pestaña **🎯 Oportunidades** para empezar a recopilar datos."
        )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    if not _all_leads.empty:
        st.subheader("Métricas generales del universo de leads")
        _email_web_count = 0
        if "email" in _enriched_leads.columns and "website" in _enriched_leads.columns:
            _email_web_count = int(
                ((_enriched_leads["email"].fillna("").str.strip() != "") |
                 (_enriched_leads["website"].fillna("").str.strip() != "")).sum()
            )

        _pending_enrichment = len(_all_leads) - _enriched_all
        ka1, ka2, ka3, ka4, ka5, ka6 = st.columns(6)
        ka1.metric("Total leads detectados", len(_all_leads),
                   delta=f"{_pending_enrichment} pendientes de enriquecer" if _pending_enrichment else None,
                   delta_color="off")
        ka2.metric("Score promedio ✓", f"{_scores_all.mean():.1f}" if not _scores_all.empty else "—")
        ka3.metric("Score mediano ✓", int(_scores_all.median()) if not _scores_all.empty else 0)
        ka4.metric("Leads 🔥 Top (≥ 50)", int((_scores_all >= 50).sum()))
        ka5.metric("Con email o web", _email_web_count)
        ka6.metric("Perfiles enriquecidos", _enriched_all)

    st.divider()

    # ── Platform quality chart ─────────────────────────────────────────────────
    st.subheader("Calidad por plataforma")
    _plat_quality = (
        _enriched_leads.groupby("source_platform")["score"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_score", "count": "n_leads"})
        .sort_values("avg_score", ascending=False)
    )
    if not _plat_quality.empty:
        fig_pq = px.bar(
            _plat_quality,
            x="source_platform",
            y="avg_score",
            text="n_leads",
            title="Calidad por plataforma — score promedio (n = leads totales)",
            labels={"avg_score": "Score promedio", "source_platform": "Plataforma"},
            color="avg_score",
            color_continuous_scale="Blues",
        )
        fig_pq.update_traces(texttemplate="%{text} leads", textposition="outside")
        fig_pq.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_pq, width="stretch")
        st.caption("Las plataformas con mayor score promedio generan leads de mejor calidad.")

    st.divider()

    # ── Lead type ranking ──────────────────────────────────────────────────────
    st.subheader("Tipos de profesional detectados")
    if "lead_type" in _enriched_leads.columns:
        _lt_quality = (
            _enriched_leads[_enriched_leads["lead_type"].fillna("") != ""]
            .groupby("lead_type")["score"]
            .agg(["count", "mean"])
            .reset_index()
            .rename(columns={"count": "n", "mean": "avg_score"})
            .sort_values("avg_score", ascending=True)
        )
        if not _lt_quality.empty:
            _lt_quality["label"] = _lt_quality["lead_type"].apply(_lead_type_label)
            fig_lt = px.bar(
                _lt_quality,
                x="avg_score",
                y="label",
                orientation="h",
                text="n",
                title="Tipos de profesional detectados — ordenados por calidad media",
                labels={"avg_score": "Score promedio", "label": "Tipo"},
                color="avg_score",
                color_continuous_scale="Greens",
            )
            fig_lt.update_traces(texttemplate="%{text} leads", textposition="outside")
            fig_lt.update_layout(coloraxis_showscale=False, height=400)
            st.plotly_chart(fig_lt, width="stretch")

    st.divider()

    # ── Score distribution with zones ─────────────────────────────────────────
    st.subheader("Distribución de scores")
    fig_hist = px.histogram(
        _enriched_leads,
        x="score",
        nbins=20,
        title="Distribución de scores — cómo está el universo de leads",
        labels={"score": "Score", "count": "Cantidad de leads"},
        color_discrete_sequence=["#636EFA"],
    )
    fig_hist.add_vline(x=38, line_dash="dash", line_color="orange", annotation_text="Alta")
    fig_hist.add_vline(x=50, line_dash="dash", line_color="darkgreen", annotation_text="Top")
    # Colored zone background rectangles — thresholds match _score_label() / _score_badge()
    fig_hist.add_vrect(x0=0,  x1=10,  fillcolor="lightgray",   opacity=0.15, line_width=0,
                       annotation_text="Mínima", annotation_position="top left")
    fig_hist.add_vrect(x0=10, x1=25,  fillcolor="lightsalmon",  opacity=0.10, line_width=0,
                       annotation_text="Baja",   annotation_position="top left")
    fig_hist.add_vrect(x0=25, x1=38,  fillcolor="lightyellow",  opacity=0.14, line_width=0,
                       annotation_text="Media",  annotation_position="top left")
    fig_hist.add_vrect(x0=38, x1=50,  fillcolor="lightblue",    opacity=0.14, line_width=0,
                       annotation_text="Alta",   annotation_position="top left")
    fig_hist.add_vrect(x0=50, x1=100, fillcolor="lightgreen",   opacity=0.14, line_width=0,
                       annotation_text="Top",    annotation_position="top left")
    st.plotly_chart(fig_hist, width="stretch")
    _pct_alta = round(100 * float((_scores_all >= 50).sum()) / max(len(_scores_all), 1), 1)
    st.caption(
        f"El {_pct_alta}% de los leads tiene score ≥ 50 (prioridad Top). "
        "Los leads bajo 25 requieren enriquecimiento antes de contactar."
    )

    st.divider()

    # ── Country chart ──────────────────────────────────────────────────────────
    st.subheader("Distribución geográfica")
    _TARGET_COUNTRIES = {
        "argentina", "españa", "spain", "méxico", "mexico", "chile", "uruguay",
        "colombia", "perú", "peru", "brasil", "brazil", "usa", "france",
        "italia", "uk",
    }
    if "country" in _all_leads.columns:
        _country_df = (
            _all_leads[_all_leads["country"].fillna("") != ""]
            .groupby("country")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .head(10)
        )
        if not _country_df.empty:
            _country_df["target"] = _country_df["country"].str.lower().isin(_TARGET_COUNTRIES)
            _country_df["color"] = _country_df["target"].map({True: "#1a6b3c", False: "#aec6f0"})
            fig_ctry = px.bar(
                _country_df,
                x="country",
                y="count",
                title="Distribución geográfica — top 10 países",
                labels={"count": "Leads", "country": "País"},
                color="target",
                color_discrete_map={True: "#1a6b3c", False: "#aec6f0"},
            )
            fig_ctry.update_layout(showlegend=False)
            st.plotly_chart(fig_ctry, width="stretch")

    st.divider()

    # ── Recurrence panel ───────────────────────────────────────────────────────
    if "scrape_count" in _all_leads.columns:
        _recurrent = _all_leads[_all_leads["scrape_count"].fillna(1) > 1].copy()
        if not _recurrent.empty:
            with st.expander(f"🔁 Perfiles recurrentes ({len(_recurrent)} cuentas vistas más de una vez)", expanded=False):
                st.caption(
                    "Estos perfiles aparecen sistemáticamente en las búsquedas — "
                    "son señal consistente de relevancia."
                )
                _rec_cols = [c for c in ["source_platform", "name", "social_handle", "scrape_count", "score", "profile_url"]
                             if c in _recurrent.columns]
                st.dataframe(
                    _recurrent[_rec_cols].sort_values("scrape_count", ascending=False).head(30),
                    hide_index=True,
                    width="stretch",
                )

    st.divider()

    # ── Pipeline / funnel de estado de leads ───────────────────────────────────
    if "status" in _all_leads.columns and not _all_leads.empty:
        _pipeline_order = ["nuevo", "contactado", "respondió", "cerrado", "descartado"]
        _pipeline_counts = _all_leads["status"].fillna("nuevo").value_counts()
        _funnel_data = []
        for _st in _pipeline_order:
            _cnt = int(_pipeline_counts.get(_st, 0))
            _funnel_data.append({"Estado": _st.capitalize(), "Leads": _cnt})
        _funnel_df = pd.DataFrame(_funnel_data)

        _fc1, _fc2 = st.columns([2, 1])
        with _fc1:
            st.subheader("Pipeline de leads")
            _funnel_colors = ["#636EFA", "#00CC96", "#AB63FA", "#1a6b3c", "#EF553B"]
            fig_funnel = go.Figure(go.Funnel(
                y=_funnel_df["Estado"],
                x=_funnel_df["Leads"],
                textinfo="value+percent initial",
                marker=dict(color=_funnel_colors[:len(_funnel_df)]),
            ))
            fig_funnel.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig_funnel, use_container_width=True)
        with _fc2:
            st.subheader("Conversión")
            _total = len(_all_leads)
            _contactados = int(_pipeline_counts.get("contactado", 0)) + int(_pipeline_counts.get("respondió", 0)) + int(_pipeline_counts.get("cerrado", 0))
            _respondieron = int(_pipeline_counts.get("respondió", 0)) + int(_pipeline_counts.get("cerrado", 0))
            _cerrados = int(_pipeline_counts.get("cerrado", 0))
            st.metric("Tasa contacto", f"{100 * _contactados / max(_total, 1):.1f}%")
            st.metric("Tasa respuesta", f"{100 * _respondieron / max(_contactados, 1):.1f}%" if _contactados else "—")
            st.metric("Tasa cierre", f"{100 * _cerrados / max(_respondieron, 1):.1f}%" if _respondieron else "—")
            st.caption("Registra estados en el detalle de cada lead (🎯 Oportunidades) para ver el embudo evolucionar.")

        st.divider()

    # ── Keyword performance (UCB ranker) ───────────────────────────────────────
    st.subheader("Rendimiento de keywords")
    try:
        from utils.database import get_keyword_stats_df as _get_kw_df
        _kw_df = _get_kw_df(config.sqlite_db_path)
    except Exception:
        _kw_df = None

    if _kw_df is None or _kw_df.empty:
        st.info("Todavía no hay estadísticas de keywords. Se generan automáticamente tras cada ejecución de scraping.")
    else:
        _kw_platforms = _kw_df["platform"].unique().tolist() if "platform" in _kw_df.columns else []
        _kw_plat_sel = st.selectbox("Plataforma", ["Todas"] + _kw_platforms, key="kw_plat_sel")
        _kw_show = _kw_df if _kw_plat_sel == "Todas" else _kw_df[_kw_df["platform"] == _kw_plat_sel]
        _kw_show = _kw_show.copy()
        # Flag de-prioritised keywords
        _kw_show["estado"] = _kw_show.apply(
            lambda r: "⚠ baja prioridad" if (
                r.get("run_count", 0) >= 3 and r.get("avg_score", 0) < 8.0 and r.get("high_leads", 0) == 0
            ) else "✓ activo",
            axis=1,
        )
        _kw_col_map = {
            "platform": "Plataforma", "keyword": "Keyword",
            "run_count": "Ejecuciones", "total_leads": "Leads totales",
            "high_leads": "Leads alto (≥35)", "warm_leads": "Leads tibios (≥15)",
            "avg_score": "Score prom.", "last_run_at": "Última ejecución",
            "estado": "Estado UCB",
        }
        _kw_show_cols = [c for c in _kw_col_map if c in _kw_show.columns or c == "estado"]
        st.dataframe(
            _kw_show[_kw_show_cols].rename(columns=_kw_col_map).sort_values("Score prom.", ascending=False),
            hide_index=True,
            width="stretch",
        )

        # ── Keyword evolution chart ────────────────────────────────────────────
        st.markdown("#### Evolución de keywords por corrida")
        try:
            from utils.database import get_keyword_run_history_df as _get_kw_hist
            _kw_hist_plat = None if _kw_plat_sel == "Todas" else _kw_plat_sel
            _kw_hist_df = _get_kw_hist(config.sqlite_db_path, platform=_kw_hist_plat)
        except Exception:
            _kw_hist_df = pd.DataFrame()

        if _kw_hist_df.empty:
            st.info("El historial por corrida estará disponible a partir de la próxima ejecución de scraping.")
        else:
            # Build run label: "#ID YYYY-MM-DD"
            _kw_hist_df["run_label"] = (
                "#" + _kw_hist_df["run_id"].astype(str) + " "
                + _kw_hist_df["started_at"].str[:10].fillna("")
            )

            # Filter: only show keywords that ran in ≥2 corridas (more interesting to chart)
            _kw_counts = _kw_hist_df.groupby("keyword")["run_id"].nunique()
            _multi_run_kws = _kw_counts[_kw_counts >= 2].index.tolist()
            _kw_hist_plot = _kw_hist_df[_kw_hist_df["keyword"].isin(_multi_run_kws)] if _multi_run_kws else _kw_hist_df

            # Keyword selector (limit clutter)
            _all_kws_in_hist = sorted(_kw_hist_plot["keyword"].unique().tolist())
            _kw_sel = st.multiselect(
                "Filtrar keywords (vacío = todas)",
                options=_all_kws_in_hist,
                default=[],
                key="kw_evo_sel",
            )
            if _kw_sel:
                _kw_hist_plot = _kw_hist_plot[_kw_hist_plot["keyword"].isin(_kw_sel)]

            if not _kw_hist_plot.empty:
                fig_kw_evo = px.line(
                    _kw_hist_plot.sort_values("run_id"),
                    x="run_label",
                    y="avg_score",
                    color="keyword",
                    markers=True,
                    title="Score promedio por keyword a lo largo de las corridas",
                    labels={
                        "run_label": "Corrida",
                        "avg_score": "Score promedio",
                        "keyword": "Keyword",
                    },
                )
                fig_kw_evo.add_hrect(
                    y0=35, y1=999, fillcolor="lightgreen", opacity=0.06, line_width=0,
                    annotation_text="zona buena (≥35)", annotation_position="top right",
                )
                fig_kw_evo.add_hrect(
                    y0=0, y1=8, fillcolor="lightsalmon", opacity=0.10, line_width=0,
                    annotation_text="zona muerta (<8)", annotation_position="bottom right",
                )
                fig_kw_evo.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig_kw_evo, width="stretch")

                # Secondary: leads count per keyword per run (bar chart)
                with st.expander("Ver cantidad de leads por keyword por corrida", expanded=False):
                    fig_kw_leads = px.bar(
                        _kw_hist_plot.sort_values("run_id"),
                        x="run_label",
                        y="n_leads",
                        color="keyword",
                        barmode="group",
                        title="Leads capturados por keyword por corrida",
                        labels={"run_label": "Corrida", "n_leads": "Leads", "keyword": "Keyword"},
                    )
                    fig_kw_leads.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
                    st.plotly_chart(fig_kw_leads, width="stretch")

                st.caption(
                    "Keywords con tendencia ascendente son candidatos a aumentar su cuota de corridas. "
                    "Keywords planas o decrecientes son candidatas a ser reemplazadas por hashtags descubiertos."
                )

    st.divider()

    # ── Run history ────────────────────────────────────────────────────────────
    st.subheader("Histórico de ejecuciones")
    _runs_df = get_runs_df(config.sqlite_db_path)
    if _runs_df.empty:
        st.info("Aún no hay ejecuciones registradas. Ejecuta el scraping para comenzar.")
    else:
        _runs_rename = {}
        for _old, _new in [
            ("id", "ID"), ("started_at", "Inicio"), ("finished_at", "Fin"),
            ("status", "Estado"), ("total_raw_leads", "Leads crudos"),
            ("total_deduped_leads", "Leads únicos"), ("notes", "Notas"),
        ]:
            if _old in _runs_df.columns:
                _runs_rename[_old] = _new
        st.dataframe(_runs_df.rename(columns=_runs_rename), hide_index=True, width="stretch")

    st.divider()

    # ── Score evolution across runs ────────────────────────────────────────────
    st.subheader("📈 Evolución de calidad por corrida")

    _evo_rows = []
    if not _runs_df.empty and "score_histogram" in _runs_df.columns:
        for _, _row in _runs_df.iterrows():
            _raw_hist = _row.get("score_histogram")
            if not _raw_hist:
                continue
            try:
                _h = json.loads(_raw_hist)
            except Exception:
                continue
            _run_label = f"#{int(_row['id'])} {str(_row.get('started_at', ''))[:10]}"
            _evo_rows.append({
                "run": _run_label,
                "run_id": int(_row["id"]),
                "avg_score": _h.get("avg", 0),
                **{f"bin_{k}": v for k, v in _h.get("bins", {}).items()},
                "by_platform": _h.get("by_platform", {}),
            })

    if not _evo_rows:
        st.info(
            "Los gráficos de evolución aparecerán aquí después de la primera "
            "ejecución de scraping (se guardan desde esta versión en adelante)."
        )
    else:
        _evo_df = pd.DataFrame(_evo_rows).sort_values("run_id")

        # ── Line chart: avg_score per run ──────────────────────────────────
        fig_evo_avg = px.line(
            _evo_df,
            x="run",
            y="avg_score",
            markers=True,
            title="Score promedio por corrida — ¿está mejorando el sistema?",
            labels={"run": "Corrida", "avg_score": "Score promedio"},
        )
        fig_evo_avg.add_hrect(
            y0=38, y1=999, fillcolor="lightgreen", opacity=0.08, line_width=0,
            annotation_text="zona alta", annotation_position="top right",
        )
        fig_evo_avg.add_hrect(
            y0=0, y1=25, fillcolor="lightsalmon", opacity=0.10, line_width=0,
            annotation_text="zona baja", annotation_position="bottom right",
        )
        fig_evo_avg.update_traces(line_color="#636EFA", line_width=2.5)
        st.plotly_chart(fig_evo_avg, width="stretch")

        st.caption(
            "Una tendencia ascendente indica que el ranking UCB está priorizando "
            "keywords más rentables y los hashtags descubiertos generan leads de mayor calidad."
        )

        st.divider()

        # ── Stacked bar: score distribution per run ────────────────────────
        _BIN_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60+"]
        _BIN_COLORS = ["#d9534f", "#e8955c", "#f0c040", "#80c77a", "#4caf77", "#1e7d45", "#0d5230"]

        _stack_rows = []
        for _r in _evo_rows:
            for _b in _BIN_LABELS:
                _stack_rows.append({
                    "run": _r["run"],
                    "run_id": _r["run_id"],
                    "rango": _b,
                    "leads": _r.get(f"bin_{_b}", 0),
                })
        _stack_df = pd.DataFrame(_stack_rows).sort_values("run_id")

        fig_stack = px.bar(
            _stack_df,
            x="run",
            y="leads",
            color="rango",
            title="Distribución de scores por corrida — histograma apilado",
            labels={"run": "Corrida", "leads": "Cantidad de leads", "rango": "Rango de score"},
            color_discrete_sequence=_BIN_COLORS,
            category_orders={"rango": _BIN_LABELS},
        )
        fig_stack.update_layout(barmode="stack", legend_title_text="Score")
        st.plotly_chart(fig_stack, width="stretch")
        st.caption(
            "Verde oscuro = leads de alta calidad (50-60+). Rojo = leads descartables (0-10). "
            "Idealmente las barras verdes crecen con el tiempo mientras las rojas se reducen."
        )

        st.divider()

        # ── Per-platform avg_score evolution ──────────────────────────────
        _plat_rows = []
        for _r in _evo_rows:
            for _plat, _pdata in _r.get("by_platform", {}).items():
                _plat_rows.append({
                    "run": _r["run"],
                    "run_id": _r["run_id"],
                    "plataforma": _plat,
                    "avg": _pdata.get("avg", 0),
                    "leads": _pdata.get("count", 0),
                })
        if _plat_rows:
            _plat_evo_df = pd.DataFrame(_plat_rows).sort_values("run_id")
            fig_plat_evo = px.line(
                _plat_evo_df,
                x="run",
                y="avg",
                color="plataforma",
                markers=True,
                title="Score promedio por plataforma a lo largo del tiempo",
                labels={"run": "Corrida", "avg": "Score promedio", "plataforma": "Plataforma"},
            )
            st.plotly_chart(fig_plat_evo, width="stretch")
            st.caption(
                "Permite detectar si una plataforma empieza a degradarse "
                "(bot-detection, cambio de algoritmo) o si mejora con los nuevos keywords."
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: 🗺️ Mapa — Geographic distribution of leads & projects (Plotly)
# ══════════════════════════════════════════════════════════════════════════════
with tab_mapa:
    try:
        import plotly.express as px
        import plotly.graph_objects as go

        _mapa_df = get_leads_df(config.sqlite_db_path)

        _rm_chart_header("Distribución Geográfica de Leads", "Inteligencia territorial")

        if _mapa_df.empty:
            st.info("Sin datos de leads todavía. Ejecuta un scrape para poblar el mapa.")
        else:
            # ── Build city-level summary ───────────────────────────────────────
            _city_col = "city" if "city" in _mapa_df.columns else None
            _score_col = "score" if "score" in _mapa_df.columns else None

            if _city_col:
                _geo_df = (
                    _mapa_df[_mapa_df[_city_col].notna() & (_mapa_df[_city_col] != "")]
                    .copy()
                )
                _geo_df["_city_key"] = _geo_df[_city_col].str.lower().str.strip()

                _city_agg = (
                    _geo_df.groupby("_city_key")
                    .agg(
                        city_display=(  _city_col, "first"),
                        leads=(_city_col, "count"),
                        avg_score=(_score_col, "mean") if _score_col else (_city_col, "count"),
                    )
                    .reset_index()
                )
                _city_agg["avg_score"] = _city_agg["avg_score"].round(1)

                # Geocode
                _city_agg["lat"] = _city_agg["_city_key"].map(lambda c: _CITY_COORDS.get(c, (None, None))[0])
                _city_agg["lon"] = _city_agg["_city_key"].map(lambda c: _CITY_COORDS.get(c, (None, None))[1])
                _city_agg = _city_agg.dropna(subset=["lat", "lon"])

                # ── Summary KPIs ───────────────────────────────────────────────
                _mc1, _mc2, _mc3, _mc4 = st.columns(4)
                _mc1.metric("Ciudades mapeadas", len(_city_agg))
                _mc2.metric("Leads georef.", int(_city_agg["leads"].sum()))
                _mc3.metric("Score promedio", f"{_city_agg['avg_score'].mean():.1f}" if not _city_agg.empty else "—")
                _top_city = _city_agg.sort_values("leads", ascending=False).iloc[0]["city_display"] if not _city_agg.empty else "—"
                _mc4.metric("Ciudad líder", _top_city)

                if not _city_agg.empty:
                    # ── Scatter geo map ────────────────────────────────────────
                    _map_fig = px.scatter_geo(
                        _city_agg,
                        lat="lat", lon="lon",
                        size="leads",
                        color="avg_score",
                        hover_name="city_display",
                        hover_data={"leads": True, "avg_score": True, "lat": False, "lon": False},
                        color_continuous_scale=[
                            [0.0, "rgba(196,163,90,0.25)"],
                            [0.5, "#C4A35A"],
                            [1.0, "#F5F0E6"],
                        ],
                        size_max=48,
                        labels={"avg_score": "Score", "leads": "Leads"},
                    )
                    _map_fig.update_layout(
                        **_rm_layout(height=460),
                        geo=dict(
                            bgcolor="#0F0E0C",
                            landcolor="#1C1A17",
                            oceancolor="#0F0E0C",
                            lakecolor="#0F0E0C",
                            coastlinecolor="rgba(245,240,230,0.12)",
                            countrycolor="rgba(245,240,230,0.08)",
                            showland=True, showocean=True, showlakes=True,
                            showcountries=True, showcoastlines=True,
                            projection_type="natural earth",
                        ),
                        coloraxis_colorbar=dict(
                            title=dict(text="Score", font=dict(color="rgba(245,240,230,0.65)", size=11)),
                            tickfont=dict(color="rgba(245,240,230,0.65)", size=10),
                            bgcolor="rgba(0,0,0,0)",
                            bordercolor="rgba(245,240,230,0.10)",
                            len=0.6,
                        ),
                    )
                    _map_fig.update_layout(margin=dict(l=0, r=0, t=20, b=0))
                    _map_fig.update_traces(marker=dict(line=dict(width=0.5, color="rgba(196,163,90,0.4)")))
                    st.plotly_chart(_map_fig, use_container_width=True)

                    # ── City ranking table + bar chart ─────────────────────────
                    _col_map_l, _col_map_r = st.columns([3, 2])

                    with _col_map_l:
                        _rm_chart_header("Ranking de ciudades", "Por volumen de leads")
                        _rank_df = (
                            _city_agg.sort_values("leads", ascending=False)
                            .head(15)
                            .rename(columns={"city_display": "Ciudad", "leads": "Leads", "avg_score": "Score Prom."})
                            [["Ciudad", "Leads", "Score Prom."]]
                        )
                        st.dataframe(_rank_df, use_container_width=True, hide_index=True)

                    with _col_map_r:
                        _rm_chart_header("Score por ciudad", "Top 10")
                        _bar_df = _city_agg.sort_values("avg_score", ascending=False).head(10)
                        _bar_fig = go.Figure(go.Bar(
                            x=_bar_df["avg_score"],
                            y=_bar_df["city_display"],
                            orientation="h",
                            marker_color="#C4A35A",
                            marker_line_width=0,
                            text=_bar_df["avg_score"].apply(lambda v: f"{v:.0f}"),
                            textposition="outside",
                            textfont=dict(color="rgba(245,240,230,0.7)", size=11),
                        ))
                        _bar_fig.update_layout(
                            **_rm_layout(height=320),
                            xaxis_range=[0, max(_bar_df["avg_score"].max() * 1.2, 10)],
                        )
                        _bar_fig.update_yaxes(
                            autorange="reversed",
                            gridcolor="rgba(245,240,230,0.06)",
                            tickfont=dict(color="rgba(245,240,230,0.65)", size=11),
                        )
                        st.plotly_chart(_bar_fig, use_container_width=True)
                else:
                    st.info("Ciudades detectadas pero sin coordenadas conocidas. Agrega más ciudades al diccionario _CITY_COORDS.")
            else:
                st.info("Los leads no tienen campo 'city'. Enriquece los datos para activar el mapa.")

    except Exception as _e:
        st.warning(f"Mapa no disponible: {_e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
# TAB: 🕸️ Red — Network analysis: actor rankings + relationship chart + graph
# ══════════════════════════════════════════════════════════════════════════════
with tab_red:
    try:
        import plotly.graph_objects as _go_red
        from visualization.network_renderer import render_network_html
        from visualization.export_graph import export_graph
        from network_engine import parse_mentions, build_graph, compute_graph_metrics

        _red_df = get_leads_df(config.sqlite_db_path)

        _rm_chart_header("Análisis de Red de Relaciones", "Influencia & colaboración")

        if _red_df.empty:
            st.info("Sin leads todavía. Ejecuta un scrape para construir la red.")
        else:
            # Build Lead objects + graph
            _net_leads = []
            for _, _r in _red_df.iterrows():
                try:
                    _raw = json.loads(_r.get("raw_data") or "{}")
                except Exception:
                    _raw = {}
                _net_leads.append(Lead(
                    source_platform=str(_r.get("source_platform") or ""),
                    search_term=str(_r.get("search_term") or ""),
                    name=str(_r.get("name") or ""),
                    social_handle=str(_r.get("social_handle") or ""),
                    bio=str(_r.get("bio") or ""),
                    lead_type=str(_r.get("lead_type") or ""),
                    lead_profile=str(_r.get("lead_profile") or "aspirational"),
                    city=str(_r.get("city") or ""),
                    country=str(_r.get("country") or ""),
                    followers=str(_r.get("followers") or ""),
                    score=int(_r.get("score") or 0),
                    raw_data=_raw,
                ))

            with st.spinner("Construyendo grafo de relaciones…"):
                _mentions = []
                for _l in _net_leads:
                    _mentions.extend(parse_mentions(_l))
                _graph = build_graph(_net_leads, _mentions)
                _metrics = compute_graph_metrics(_graph)

            # ── Network signal quality KPIs ───────────────────────────────────
            _density_pct = (
                round(_graph.edge_count / max(_graph.node_count, 1) * 100, 1)
                if _graph.node_count else 0
            )
            _mention_rate = round(len(_mentions) / max(len(_net_leads), 1) * 100, 1)
            _rn1, _rn2, _rn3, _rn4 = st.columns(4)
            _rn1.metric("Actores en red", _graph.node_count)
            _rn2.metric("Conexiones detectadas", _graph.edge_count)
            _rn3.metric("Menciones encontradas", len(_mentions))
            _rn4.metric("Tasa mención/lead", f"{_mention_rate:.1f}%")

            st.markdown('<div style="height:.75rem"></div>', unsafe_allow_html=True)

            # ── Primary view: actor table + relation type chart ────────────────
            _col_rn_l, _col_rn_r = st.columns([3, 2])

            with _col_rn_l:
                _rm_chart_header("Actores por Influencia de Red", "Ranking")
                if _metrics:
                    _met_rows = sorted(
                        _metrics.values(), key=lambda m: m.network_influence_score, reverse=True
                    )[:20]
                    _met_data = [{
                        "Handle": f"@{m.handle}",
                        "Influencia": round(m.network_influence_score, 1),
                        "Centralidad": round(m.actor_centrality_score, 1),
                        "PageRank": round(m.pagerank_score, 1),
                        "Grado": round(m.degree_score, 1),
                    } for m in _met_rows]
                    st.dataframe(
                        pd.DataFrame(_met_data),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Influencia": st.column_config.ProgressColumn("Influencia", min_value=0, max_value=100, format="%.1f"),
                            "Centralidad": st.column_config.ProgressColumn("Centralidad", min_value=0, max_value=100, format="%.1f"),
                        },
                    )
                else:
                    st.caption("No hay menciones detectadas — la red está vacía. Las bios con @handles activan el análisis.")

            with _col_rn_r:
                _rm_chart_header("Tipos de Relación", "Distribución")
                if _mentions:
                    from collections import Counter as _Counter
                    _rel_counts = _Counter(m.relation_type for m in _mentions)
                    _rel_labels = {
                        "COLLABORATES_WITH": "Colabora con",
                        "DESIGNED_BY": "Diseñado por",
                        "WORKS_ON": "Trabaja en",
                        "MENTIONS": "Menciona",
                    }
                    _rl = [_rel_labels.get(k, k) for k in _rel_counts.keys()]
                    _rv = list(_rel_counts.values())
                    _rel_fig = _go_red.Figure(_go_red.Bar(
                        x=_rv, y=_rl, orientation="h",
                        marker_color=["#C4A35A", "#8B7355", "#6B5B3E", "#4A3F2F"][:len(_rl)],
                        marker_line_width=0,
                        text=_rv, textposition="outside",
                        textfont=dict(color="rgba(245,240,230,0.7)", size=11),
                    ))
                    _rel_fig.update_layout(
                        **_rm_layout(height=260),
                        xaxis_range=[0, max(_rv) * 1.3 if _rv else 10],
                    )
                    _rel_fig.update_yaxes(
                        autorange="reversed",
                        gridcolor="rgba(245,240,230,0.04)",
                        tickfont=dict(color="rgba(245,240,230,0.65)", size=11),
                    )
                    st.plotly_chart(_rel_fig, use_container_width=True)

                    # Influence leaders per relation type
                    st.markdown(
                        '<p style="font:500 11px/1 Inter,sans-serif;letter-spacing:.18em;'
                        'text-transform:uppercase;color:#C4A35A;margin:1rem 0 .4rem">Conexiones más fuertes</p>',
                        unsafe_allow_html=True,
                    )
                    _strong = sorted(_mentions, key=lambda m: m.confidence, reverse=True)[:6]
                    for _mn in _strong:
                        _rel_short = _rel_labels.get(_mn.relation_type, _mn.relation_type)
                        st.markdown(
                            f'<p style="font:400 12px/1.5 Inter,sans-serif;color:rgba(245,240,230,0.7);margin:.2rem 0">'
                            f'<span style="color:#C4A35A">@{_mn.source_handle}</span>'
                            f' <span style="color:rgba(245,240,230,0.35)">→</span> '
                            f'@{_mn.target_handle}'
                            f' <span style="color:rgba(245,240,230,0.4);font-size:11px"> {_rel_short} · {_mn.confidence:.0%}</span>'
                            f'</p>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Sin menciones detectadas. Enriquece las bios con @handles para activar el análisis de relaciones.")

            st.markdown('<hr style="border:none;border-top:1px solid rgba(245,240,230,0.07);margin:1.5rem 0">', unsafe_allow_html=True)

            # ── Secondary: interactive Pyvis graph (on-demand) ─────────────────
            _col_tog, _col_exp = st.columns([3, 2])
            with _col_tog:
                _show_graph = st.checkbox(
                    "Mostrar grafo interactivo (Pyvis)",
                    value=False,
                    help="Visualización fuerza-dirigida. Útil cuando hay ≥ 10 conexiones.",
                )
            with _col_exp:
                _export_fmt = st.selectbox("Exportar grafo como", ["gexf", "graphml", "json", "csv"], label_visibility="collapsed")
                _exp_bytes, _exp_name, _exp_mime = export_graph(_graph, fmt=_export_fmt)
                if _exp_bytes:
                    st.download_button(f"⬇️ Descargar ({_export_fmt.upper()})", _exp_bytes, _exp_name, _exp_mime)

            if _show_graph:
                _col_gconf1, _col_gconf2 = st.columns(2)
                with _col_gconf1:
                    _min_conf = st.slider("Confianza mínima de arista", 0.0, 1.0, 0.3, 0.05)
                with _col_gconf2:
                    _max_nodes = st.slider("Máx. nodos visibles", 20, 300, 120, 10)

                with st.spinner("Renderizando grafo…"):
                    _net_html = render_network_html(_graph, min_confidence=_min_conf, max_nodes=_max_nodes)
                st.components.v1.html(_net_html, height=560, scrolling=False)
                st.markdown(
                    '<p style="font:400 11px/1.6 Inter,sans-serif;color:rgba(245,240,230,0.4);margin:.5rem 0 0">'
                    '🟣 Specifier &nbsp;·&nbsp; 🔴 Buyer &nbsp;·&nbsp; 🟠 Project actor &nbsp;·&nbsp;'
                    '🔵 Influencer &nbsp;·&nbsp; 🟢 Proyecto &nbsp;·&nbsp; 🟡 Evento &nbsp;·&nbsp; ⬜ Aspirational'
                    '</p>',
                    unsafe_allow_html=True,
                )

    except Exception as _e:
        st.warning(f"Red no disponible: {_e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
# TAB: 🔍 Discovery — Opportunity heatmap + project clusters + BI queries
# ══════════════════════════════════════════════════════════════════════════════
with tab_discovery:
    try:
        from visualization.opportunity_heatmap import render_opportunity_heatmap
        from project_engine import detect_project, cluster_leads, rank_clusters
        from project_engine.project_ranker import enrich_cluster_scores
        from ai_engine import analyse_project_cluster

        _disc_df = get_leads_df(config.sqlite_db_path)

        _rm_chart_header("Opportunity Discovery", "Inteligencia comercial")

        if _disc_df.empty:
            st.info("Sin datos. Ejecuta un scrape para activar el discovery.")
        else:
            # ── Quick stats bar ───────────────────────────────────────────────
            _dq1, _dq2, _dq3, _dq4 = st.columns(4)
            _spec_count = int((_disc_df["specifier_score"] >= 40).sum()) if "specifier_score" in _disc_df.columns else 0
            _proj_count = int((_disc_df["project_signal_score"] >= 30).sum()) if "project_signal_score" in _disc_df.columns else 0
            _evt_count  = int((_disc_df["event_signal_score"] >= 30).sum()) if "event_signal_score" in _disc_df.columns else 0
            _bp_count   = int((_disc_df["buying_power_score"] >= 40).sum()) if "buying_power_score" in _disc_df.columns else 0
            _dq1.metric("Especificadores activos", _spec_count)
            _dq2.metric("Señales de proyecto", _proj_count)
            _dq3.metric("Señales de evento", _evt_count)
            _dq4.metric("Alto poder adquisitivo", _bp_count)

            st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

            # ── Heatmap + cluster cards (2 columns) ───────────────────────────
            _col_hm, _col_cl = st.columns([3, 2])

            with _col_hm:
                _rm_chart_header("Opportunity Score · Ciudad × Tipo", "Heatmap")
                _hm_fig = render_opportunity_heatmap(_disc_df)
                # Apply RM theme to heatmap
                _hm_fig.update_layout(
                    paper_bgcolor="#141210", plot_bgcolor="#0F0E0C",
                    font=dict(family="Inter, sans-serif", color="#F5F0E6", size=11),
                    height=340,
                    margin=dict(l=8, r=8, t=32, b=8),
                )
                st.plotly_chart(_hm_fig, use_container_width=True)

            with _col_cl:
                _rm_chart_header("Clusters de proyectos detectados", "En tiempo real")

                # Build detections
                _disc_leads_list = []
                for _, _r in _disc_df.iterrows():
                    try:
                        _raw2 = json.loads(_r.get("raw_data") or "{}")
                    except Exception:
                        _raw2 = {}
                    _disc_leads_list.append((Lead(
                        source_platform=str(_r.get("source_platform") or ""),
                        search_term=str(_r.get("search_term") or ""),
                        name=str(_r.get("name") or ""),
                        social_handle=str(_r.get("social_handle") or ""),
                        bio=str(_r.get("bio") or ""),
                        lead_type=str(_r.get("lead_type") or ""),
                        lead_profile=str(_r.get("lead_profile") or "aspirational"),
                        city=str(_r.get("city") or ""),
                        country=str(_r.get("country") or ""),
                        followers=str(_r.get("followers") or ""),
                        score=int(_r.get("score") or 0),
                        raw_data=_raw2,
                    ), _raw2, int(_r.get("id") or 0)))

                with st.spinner("Detectando proyectos…"):
                    _det_inputs = []
                    for _l, _raw2, _lid in _disc_leads_list:
                        _proj_score = float(_raw2.get("project_signal_score", 0))
                        _det = detect_project(_l, _proj_score)
                        if _det:
                            _det_inputs.append((_l, _det, _lid))
                    _clusters = cluster_leads(_det_inputs)
                    for _c in _clusters:
                        _c_raw_list = [_r2 for _, _r2, _lid in _disc_leads_list if _lid in _c.actor_ids]
                        enrich_cluster_scores(_c, _c_raw_list)
                    _clusters = rank_clusters(_clusters)

                if _clusters:
                    st.caption(f"**{len(_clusters)}** cluster(s) · ordenados por densidad de oportunidad")
                    for _ci, _c in enumerate(_clusters[:8]):
                        _status_icon = "🔴" if _c.status == "active" else "🟣" if _c.status == "emerging" else "⚪"
                        _c_label = (
                            f"{_status_icon} **{_c.project_type.replace('_',' ').title()}**"
                            f" — {_c.location_city or '?'} · {_c.confidence:.0%} conf."
                        )
                        with st.expander(_c_label, expanded=_ci == 0):
                            _ca, _cb = st.columns(2)
                            _ca.metric("Status", _c.status.title())
                            _cb.metric("Budget", _c.budget_tier.title())
                            _cc, _cd = st.columns(2)
                            _cc.metric("Density", f"{_c.opportunity_density:.2f}")
                            _cd.metric("Actores", _c.actor_count)
                            if _c.timeline_hint:
                                st.caption(f"Timeline: {_c.timeline_hint}")
                            if _c.actor_handles:
                                st.caption(", ".join(f"@{h}" for h in _c.actor_handles[:5]))
                            if _c.evidence_texts:
                                st.caption(f"_{_c.evidence_texts[0][:100]}_")
                            if st.button("🤖 Analizar con IA", key=f"ai_cluster_{_ci}"):
                                with st.spinner("Analizando con Ollama…"):
                                    _ai_proj = analyse_project_cluster(_c)
                                st.markdown(f"**{_ai_proj.project_name}** — {_ai_proj.urgency.replace('_',' ').title()}")
                                st.markdown(f"_{_ai_proj.summary}_")
                                st.caption(f"Budget: {_ai_proj.estimated_budget_range} · Approach: {_ai_proj.recommended_approach}")
                                if _ai_proj.flags:
                                    st.warning(" · ".join(_ai_proj.flags))
                else:
                    st.caption("Sin clusters detectados. Las bios con señales de proyecto activan la detección.")

            st.markdown('<hr style="border:none;border-top:1px solid rgba(245,240,230,0.07);margin:1.5rem 0">', unsafe_allow_html=True)

            # ── Intelligence queries (3-col) ──────────────────────────────────
            _rm_chart_header("Preguntas de Inteligencia Comercial", "Quién contactar primero")
            _qi1, _qi2, _qi3 = st.columns(3)

            with _qi1:
                st.markdown(
                    '<p style="font:500 12px/1.5 Inter,sans-serif;color:#C4A35A;margin:0 0 .5rem">¿Especificadores clave?</p>',
                    unsafe_allow_html=True,
                )
                if "specifier_score" in _disc_df.columns:
                    _top_spec = _disc_df[_disc_df["specifier_score"] >= 40].copy()
                    if not _top_spec.empty:
                        _cols_spec = [c for c in ["name", "city", "lead_type", "specifier_score"] if c in _top_spec.columns]
                        st.dataframe(
                            _top_spec[_cols_spec].sort_values("specifier_score", ascending=False).head(8),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("Enriquece leads para ver especificadores.")
                else:
                    st.caption("Requiere enriquecimiento de leads.")

            with _qi2:
                st.markdown(
                    '<p style="font:500 12px/1.5 Inter,sans-serif;color:#C4A35A;margin:0 0 .5rem">¿Actores con proyecto activo?</p>',
                    unsafe_allow_html=True,
                )
                if "project_signal_score" in _disc_df.columns:
                    _top_proj = _disc_df[_disc_df["project_signal_score"] >= 30].copy()
                    if not _top_proj.empty:
                        _cols_proj = [c for c in ["name", "city", "lead_type", "project_signal_score"] if c in _top_proj.columns]
                        st.dataframe(
                            _top_proj[_cols_proj].sort_values("project_signal_score", ascending=False).head(8),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("Enriquece leads para ver actores de proyecto.")
                else:
                    st.caption("Requiere enriquecimiento de leads.")

            with _qi3:
                st.markdown(
                    '<p style="font:500 12px/1.5 Inter,sans-serif;color:#C4A35A;margin:0 0 .5rem">¿Alto poder adquisitivo?</p>',
                    unsafe_allow_html=True,
                )
                if "buying_power_score" in _disc_df.columns:
                    _top_bp = _disc_df[_disc_df["buying_power_score"] >= 40].copy()
                    if not _top_bp.empty:
                        _cols_bp = [c for c in ["name", "city", "lead_type", "buying_power_score", "opportunity_classification"] if c in _top_bp.columns]
                        st.dataframe(
                            _top_bp[_cols_bp].sort_values("buying_power_score", ascending=False).head(8),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("Enriquece leads para ver poder adquisitivo.")
                else:
                    st.caption("Requiere enriquecimiento de leads.")

    except Exception as _e:
        st.warning(f"Discovery no disponible: {_e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
# TAB: 🔄 Feedback
# ══════════════════════════════════════════════════════════════════════════════
with tab_feedback:
    st.subheader("🔄 Registro de resultados reales")
    st.caption(
        "Marcar leads como convertidos o descartados permite que el sistema aprenda qué perfiles "
        "funcionan en la práctica. Con 5+ registros de cada tipo, el análisis de calibración se activa."
    )

    _store = FeedbackStore(config.sqlite_db_path)

    # ── Outcome form ───────────────────────────────────────────────────────────
    with st.expander("➕ Registrar resultado de un lead", expanded=False):
        with st.form("feedback_outcome_form"):
            _fb_url = st.text_input("URL del perfil (de la tabla de leads)")
            _fb_outcome = st.selectbox(
                "Resultado",
                options=["converted", "disqualified"],
                format_func=lambda x: (
                    "✅ Convirtió — fue cliente o generó negocio"
                    if x == "converted"
                    else "❌ Descartado — no era el perfil correcto"
                ),
            )
            _fb_notes = st.text_input("Notas (opcional)")
            _fb_submit = st.form_submit_button("Guardar resultado")

        if _fb_submit and _fb_url.strip():
            # Validate URL exists in leads table before saving
            _fb_leads_df = get_leads_df(config.sqlite_db_path)
            _fb_match = _fb_leads_df[
                _fb_leads_df["profile_url"].fillna("").str.strip() == _fb_url.strip()
            ]
            if _fb_match.empty:
                st.error(
                    f"No se encontró ningún lead con esa URL en la base de datos. "
                    "Copiá la URL exacta desde la columna **profile_url** de la tabla de leads."
                )
            else:
                _store.mark_outcome(_fb_url.strip(), _fb_outcome, _fb_notes.strip())
                _fb_name = _fb_match.iloc[0].get("name", _fb_url.strip())
                st.success(f"Resultado '{_fb_outcome}' guardado para **{_fb_name}**.")
                st.rerun()

    st.divider()

    # ── Outcomes table ─────────────────────────────────────────────────────────
    _outcomes = _store.get_outcomes()
    if _outcomes:
        _out_df = pd.DataFrame(_outcomes)
        if "outcome" in _out_df.columns:
            _out_df["outcome"] = _out_df["outcome"].map(
                {"converted": "✅ Convirtió", "disqualified": "❌ Descartado"}
            ).fillna(_out_df["outcome"])
        _out_cols = [c for c in ["profile_url", "outcome", "marked_at", "notes"] if c in _out_df.columns]
        st.dataframe(_out_df[_out_cols], hide_index=True, width="stretch")
    else:
        st.info(
            "Aún no hay resultados registrados. "
            "Cuando contactes un lead, registra aquí qué pasó para calibrar el modelo."
        )

    st.divider()

    # ── Calibration analysis ───────────────────────────────────────────────────
    st.subheader("📊 Análisis de calibración del scoring")
    _analysis = analyze_conversions(config.sqlite_db_path)

    if _analysis.get("insufficient_data"):
        _hints = _analysis.get("calibration_hints") or []
        if _hints:
            st.info(_hints[0])
        else:
            st.info(
                "Necesitamos al menos 5 conversiones y 5 descartados para activar el análisis de calibración. "
                "Registra resultados reales de tus contactos para habilitar esta función."
            )
    else:
        ca1, ca2, ca3, ca4 = st.columns(4)
        ca1.metric("Leads etiquetados", _analysis.get("sample_size", 0))
        ca2.metric("Convertidos", _analysis.get("converted_count", 0))
        ca3.metric("Descartados", _analysis.get("disqualified_count", 0))
        _sep = _analysis.get("score_separation")
        _sep_help = "Diferencia de score promedio entre convertidos y descartados. Más alto = modelo más preciso."
        ca4.metric(
            "Separación de score",
            f"{_sep} pts" if _sep is not None else "N/A",
            help=_sep_help,
        )

        cm1, cm2 = st.columns(2)
        cm1.metric("Score promedio convertidos", _analysis.get("avg_score_converted", "N/A"))
        cm2.metric("Score promedio descartados", _analysis.get("avg_score_disqualified", "N/A"))

        # Precision by score band
        _band_data = _analysis.get("precision_by_score_band") or {}
        if _band_data:
            _band_df = pd.DataFrame(
                [{"Banda": k, "Precisión": v} for k, v in _band_data.items()]
            )
            fig_band = px.bar(
                _band_df,
                x="Banda",
                y="Precisión",
                title="Precisión por banda de score (convertidos / total etiquetado)",
                color="Precisión",
                color_continuous_scale="RdYlGn",
                range_color=[0, 1],
            )
            st.plotly_chart(fig_band, width="stretch")

        # Calibration hints
        _cal_hints = _analysis.get("calibration_hints") or []
        if _cal_hints:
            st.subheader("Sugerencias de calibración")
            for _hint in _cal_hints:
                st.info(_hint)


# ══════════════════════════════════════════════════════════════════════════════
# TAB: 📡 Sistema
# ══════════════════════════════════════════════════════════════════════════════
with tab_sistema:
    st.subheader("📡 Salud del sistema de scoring")

    _all_leads = get_leads_df(config.sqlite_db_path)
    _store = FeedbackStore(config.sqlite_db_path)

    if _all_leads.empty:
        st.warning(
            "**No hay leads en la base de datos todavía.**\n\n"
            "Ejecuta el scraping desde la pestaña **🎯 Oportunidades** para comenzar."
        )
    else:
        # ── Score health KPIs ──────────────────────────────────────────────────
        _scores = _all_leads["score"].fillna(0)
        _enriched_count = 0
        if "enriched_at" in _all_leads.columns:
            _enriched_count = int((_all_leads["enriched_at"].fillna("").str.strip() != "").sum())

        sk1, sk2, sk3, sk4, sk5 = st.columns(5)
        sk1.metric("Total leads", len(_all_leads))
        sk2.metric("Score promedio", round(float(_scores.mean()), 1))
        sk3.metric("Score mediano", int(_scores.median()))
        sk4.metric("Leads score ≥ 50", int((_scores >= 50).sum()))
        sk5.metric("Enriquecidos", _enriched_count)

        st.divider()

        # ── Spam risk histogram ────────────────────────────────────────────────
        st.subheader("Autenticidad de perfiles — Spam Risk")
        _spam_data = []
        for _, _srow in _all_leads.iterrows():
            try:
                _rd = json.loads(_srow.get("raw_data") or "{}")
                _spam = _rd.get("spam_risk")
                if _spam is not None:
                    _spam_data.append({
                        "spam_risk": float(_spam),
                        "platform": _srow.get("source_platform", "?"),
                    })
            except Exception:
                pass

        if _spam_data:
            _spam_df = pd.DataFrame(_spam_data)
            fig_spam = px.histogram(
                _spam_df,
                x="spam_risk",
                nbins=20,
                title="Distribución de Spam Risk (0=auténtico, 100=sospechoso)",
                labels={"spam_risk": "Spam Risk (0–100)"},
                color_discrete_sequence=["#EF553B"],
            )
            fig_spam.add_vline(x=60, line_dash="dash", line_color="red", annotation_text="Riesgo alto")
            st.plotly_chart(fig_spam, width="stretch")
        else:
            st.info(
                "Para ver el análisis de autenticidad, actualiza los datos con 'Completar perfiles'. "
                "El spam risk se calcula durante el enriquecimiento de perfiles."
            )

        st.divider()

        # ── Platform avg score chart ───────────────────────────────────────────
        st.subheader("Score promedio por plataforma")
        _plat_score = (
            _all_leads.groupby("source_platform")["score"]
            .agg(["mean", "count"])
            .reset_index()
            .rename(columns={"mean": "avg_score", "count": "total"})
            .sort_values("avg_score", ascending=False)
        )
        fig_plat = px.bar(
            _plat_score,
            x="source_platform",
            y="avg_score",
            text="total",
            title="Score promedio por plataforma",
            labels={"avg_score": "Score promedio", "source_platform": "Plataforma"},
            color="avg_score",
            color_continuous_scale="Blues",
        )
        fig_plat.update_traces(texttemplate="%{text} leads", textposition="outside")
        fig_plat.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_plat, width="stretch")

        st.divider()

        # ── Lead type distribution ─────────────────────────────────────────────
        st.subheader("Distribución de tipos de profesional")
        if "lead_type" in _all_leads.columns:
            _lt_dist = (
                _all_leads[_all_leads["lead_type"].fillna("") != ""]
                .groupby("lead_type")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )
            if not _lt_dist.empty:
                _lt_dist["label"] = _lt_dist["lead_type"].apply(_lead_type_label)
                fig_lt_dist = px.bar(
                    _lt_dist,
                    x="label",
                    y="count",
                    title="Leads por tipo de profesional",
                    labels={"label": "Tipo", "count": "Cantidad"},
                    color_discrete_sequence=["#00CC96"],
                )
                st.plotly_chart(fig_lt_dist, width="stretch")

        st.divider()

        # ── Signal density histogram ───────────────────────────────────────────
        st.subheader("Densidad de señales")
        _signal_data = []
        for _, _srow in _all_leads.iterrows():
            try:
                _rd = json.loads(_srow.get("raw_data") or "{}")
                _sig = _rd.get("signal_density")
                if _sig is not None:
                    _signal_data.append({
                        "signal_density": int(_sig),
                        "platform": _srow.get("source_platform", "?"),
                    })
            except Exception:
                pass

        if _signal_data:
            _sig_df = pd.DataFrame(_signal_data)
            fig_sig = px.histogram(
                _sig_df,
                x="signal_density",
                color="platform",
                barmode="overlay",
                title="Densidad de señales (0 = ninguna, 5 = máxima)",
                nbins=6,
                labels={"signal_density": "Tipos de señal activos"},
            )
            st.plotly_chart(fig_sig, width="stretch")
        else:
            st.info(
                "La densidad de señales no está disponible todavía. "
                "Ejecuta 'Completar perfiles' para activar el análisis de señales con ScoreEngine."
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: ⚙️ Configuración
# ══════════════════════════════════════════════════════════════════════════════
with tab_config:
    st.subheader("⚙️ Configuración del pipeline")

    PLATFORMS = [
        ("instagram",  "Instagram",    "📸", "Usuario"),
        ("facebook",   "Facebook",     "📘", "Email"),
        ("linkedin",   "LinkedIn",     "💼", "Email"),
        ("twitter",    "Twitter / X",  "🐦", "Usuario"),
        ("pinterest",  "Pinterest",    "📌", "Email"),
        ("reddit",     "Reddit",       "🤖", "Usuario"),
        ("behance",    "Behance",      "🎨", "Email (Adobe)"),
    ]

    # ── Cookie status (must live OUTSIDE the form — buttons can't be in forms) ──
    st.markdown("#### 🍪 Sesiones guardadas (cookies)")
    _sess_col1, _sess_col2 = st.columns(2)

    with _sess_col1:
        st.caption("**📸 Instagram** — extrae cookies del Chrome activo. Las cookies duran ~25 días.")
        _cookie_file = Path(__file__).parent / "output" / "instagram_session.json"
        if _cookie_file.exists():
            _cookie_mtime = _cookie_file.stat().st_mtime
            import datetime as _dt
            _cookie_age_days = (time.time() - _cookie_mtime) / 86400
            _cookie_label = f"✅ Cookies activas ({_cookie_age_days:.0f} días)" if _cookie_age_days < 25 else f"⚠ Cookies antiguas ({_cookie_age_days:.0f} días) — recomendado renovar"
            st.caption(_cookie_label)
        else:
            st.caption("⚠ Sin cookies guardadas — el scraper de Instagram no podrá autenticarse.")

    with _sess_col2:
        st.caption("**🎨 Behance** — SSO Adobe. Las cookies se guardan automáticamente tras el primer login.")
        _beh_cookie_file = Path(__file__).parent / "output" / "behance_session.json"
        if _beh_cookie_file.exists():
            _beh_age_days = (time.time() - _beh_cookie_file.stat().st_mtime) / 86400
            _beh_label = f"✅ Cookies activas ({_beh_age_days:.0f} días)" if _beh_age_days < 25 else f"⚠ Cookies antiguas ({_beh_age_days:.0f} días)"
            st.caption(_beh_label)
            if st.button("🗑 Eliminar cookies Behance", key="del_beh_cookie", type="secondary"):
                try:
                    _beh_cookie_file.unlink()
                    st.success("Cookies de Behance eliminadas. Se realizará un nuevo login en la próxima ejecución.")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Error: {_e}")
        else:
            st.caption("⚠ Sin cookies guardadas — se hará login automático con las credenciales del .env.")

    st.divider()

    with st.form("config_form"):

        # ── General ──────────────────────────────────────────────────────────
        st.markdown("### 🔧 Configuración general")
        g1, g2 = st.columns(2)
        headless = g1.checkbox("Modo headless (sin ventana del navegador)", value=config.headless)
        save_debug = g2.checkbox("Guardar HTML de debug", value=config.save_debug_html)

        c1, c2, c3 = st.columns(3)
        max_profiles = c1.number_input(
            "Máx. perfiles / plataforma", min_value=5, max_value=500,
            value=config.max_profiles_per_platform, step=5,
        )
        max_results = c2.number_input(
            "Máx. resultados / búsqueda", min_value=5, max_value=200,
            value=config.max_results_per_query, step=5,
        )
        max_searches = c3.number_input(
            "Máx. búsquedas / plataforma / sesión",
            min_value=1, max_value=50,
            value=config.max_searches_per_session, step=1,
            help="Limita cuántas keywords se procesan por plataforma en cada ejecución. Reduce el riesgo de ban.",
        )
        d1, d2, d3 = st.columns(3)
        min_delay = d1.number_input(
            "Delay mínimo (seg)", min_value=0.5, max_value=30.0,
            value=config.min_delay, step=0.5,
        )
        max_delay = d2.number_input(
            "Delay máximo (seg)", min_value=1.0, max_value=60.0,
            value=config.max_delay, step=0.5,
        )
        cooldown_days = d3.number_input(
            "Cooldown re-scraping (días)",
            min_value=1, max_value=90,
            value=config.rescrape_cooldown_days, step=1,
            help="Perfiles vistos hace menos de N días se omiten automáticamente para evitar baneos.",
        )

        st.markdown("#### 🐢 Conexión lenta")
        n1, n2, n3 = st.columns(3)
        page_load_timeout = n1.number_input(
            "Timeout carga de página (seg)", min_value=15, max_value=300,
            value=config.page_load_timeout, step=5,
            help="Segundos máximos esperando que cargue una página. Aumentar en conexiones lentas.",
        )
        network_retries = n2.number_input(
            "Reintentos por keyword", min_value=1, max_value=10,
            value=config.network_retries, step=1,
            help="Si falla una keyword por error de red, reintenta N veces con backoff exponencial.",
        )
        block_images = n3.checkbox(
            "Bloquear imágenes y media",
            value=config.block_images,
            help="Ahorra 70-90% de ancho de banda. Recomendado para conexiones lentas.",
        )
        chrome_user_data = st.text_input(
            "Chrome User Data Dir",
            value=config.user_data_dir,
            placeholder="/home/usuario/.config/google-chrome",
        )
        chrome_profile = st.text_input(
            "Chrome Profile Path",
            value=config.chrome_profile_path,
            placeholder="Default",
        )

        st.markdown("### 🌐 Plataformas")

        platform_data: dict = {}
        for pid, plabel, icon, user_label in PLATFORMS:
            enabled_now = getattr(config, f"{pid}_enabled", True)
            username_now = getattr(config, f"{pid}_username", "")
            password_now = getattr(config, f"{pid}_password", "")
            kw_now = ", ".join(getattr(config, f"{pid}_keywords", []))
            status_badge = "✅ Activa" if enabled_now else "⛔ Inactiva"

            with st.expander(f"{icon} {plabel} — {status_badge}", expanded=False):
                t1, t2 = st.columns([1, 4])
                enabled = t1.toggle("Activar scraping", value=enabled_now, key=f"en_{pid}")
                t2.caption(f"Plataforma: **{plabel}** · Las credenciales se guardan en `.env` (local).")

                u1, u2 = st.columns(2)
                username = u1.text_input(user_label, value=username_now, key=f"usr_{pid}")
                password = u2.text_input("Contraseña", value=password_now, type="password", key=f"pwd_{pid}")

                keywords_raw = st.text_area(
                    "Keywords (separadas por coma)",
                    value=kw_now,
                    height=80,
                    key=f"kw_{pid}",
                    help="Ej: #interiordesign, luxury interiors, arquitectura",
                )

                platform_data[pid] = {
                    "enabled": enabled,
                    "username": username,
                    "password": password,
                    "keywords": keywords_raw,
                }

        st.divider()
        submitted = st.form_submit_button(
            "💾 Guardar configuración", width="stretch", type="primary"
        )

    if submitted:
        ENV_PATH.touch(exist_ok=True)
        # General
        set_key(str(ENV_PATH), "HEADLESS", "true" if headless else "false")
        set_key(str(ENV_PATH), "SAVE_DEBUG_HTML", "true" if save_debug else "false")
        set_key(str(ENV_PATH), "MAX_PROFILES_PER_PLATFORM", str(int(max_profiles)))
        set_key(str(ENV_PATH), "MAX_RESULTS_PER_QUERY", str(int(max_results)))
        set_key(str(ENV_PATH), "MAX_SEARCHES_PER_SESSION", str(int(max_searches)))
        set_key(str(ENV_PATH), "MIN_DELAY", str(min_delay))
        set_key(str(ENV_PATH), "MAX_DELAY", str(max_delay))
        set_key(str(ENV_PATH), "RESCRAPE_COOLDOWN_DAYS", str(int(cooldown_days)))
        set_key(str(ENV_PATH), "PAGE_LOAD_TIMEOUT", str(int(page_load_timeout)))
        set_key(str(ENV_PATH), "NETWORK_RETRIES", str(int(network_retries)))
        set_key(str(ENV_PATH), "BLOCK_IMAGES", "true" if block_images else "false")
        set_key(str(ENV_PATH), "USER_DATA_DIR", chrome_user_data)
        set_key(str(ENV_PATH), "CHROME_PROFILE_PATH", chrome_profile)
        # Per platform
        for pid, data in platform_data.items():
            P = pid.upper()
            set_key(str(ENV_PATH), f"{P}_ENABLED", "true" if data["enabled"] else "false")
            set_key(str(ENV_PATH), f"{P}_USERNAME", data["username"])
            set_key(str(ENV_PATH), f"{P}_PASSWORD", data["password"])
            set_key(str(ENV_PATH), f"{P}_KEYWORDS", data["keywords"])

        st.success("✅ Configuración guardada en `.env`. Reinicia el scraping para aplicar los cambios.")
        st.rerun()

    # ── Instagram cookie renewal (outside form — needs its own submit action) ──
    st.divider()
    st.markdown("#### 🍪 Renovar cookies de Instagram")
    st.caption("Requiere que Chrome esté abierto e Instagram activo. Las cookies se extraen en segundos.")
    _ck_col1, _ck_col2 = st.columns([1, 3])
    if _ck_col1.button("🔄 Extraer cookies ahora", type="secondary"):
        _cookie_script = Path(__file__).parent / "extract_chrome_cookies.py"
        if not _cookie_script.exists():
            st.error("No se encontró extract_chrome_cookies.py")
        else:
            _ck_result = subprocess.run(
                [sys.executable, str(_cookie_script)],
                capture_output=True, text=True, timeout=30,
                cwd=str(Path(__file__).parent),
            )
            if _ck_result.returncode == 0:
                _ck_lines = (_ck_result.stdout or "").strip().splitlines()
                _ck_msg = _ck_lines[-1] if _ck_lines else "Cookies renovadas correctamente."
                st.success(f"✅ {_ck_msg}")
            else:
                st.error(f"Error: {(_ck_result.stderr or _ck_result.stdout or '').strip()[-500:]}")
    _ck_col2.caption(
        "Si Chrome no tiene Instagram abierto o no está logueado, "
        "abre Chrome, navega a instagram.com e inicia sesión primero."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: ⏰ Programación
# ══════════════════════════════════════════════════════════════════════════════
with tab_prog:
    st.subheader("⏰ Programación y control del scraping")
    st.caption(
        "Monitorea el proceso en tiempo real, interrúmpelo si es necesario, "
        "configura el horario automático y revisa los logs de cada sesión."
    )

    # ── Section 1: Estado del proceso ─────────────────────────────────────────
    st.markdown("### Estado del proceso")

    is_running, scrape_pid, elapsed = _get_scrape_status()

    # Enabled platforms list (needed for progress parsing)
    _enabled_platforms = [
        p for p in ["instagram", "linkedin", "twitter", "facebook", "pinterest", "reddit", "behance"]
        if getattr(config, f"{p}_enabled", False)
    ]

    if is_running:
        elapsed_str = _fmt_elapsed(elapsed) if elapsed else "?"

        # ── Parse progress from log ────────────────────────────────────────────
        _full_log = _read_latest_log_full()
        _prog     = _parse_progress(_full_log, _enabled_platforms)
        _pct      = _prog["pct"]
        _phase    = _PHASE_LABELS.get(_prog["phase"], _prog["phase"])

        # ── Header row: status badge + elapsed + PID ──────────────────────────
        _hc1, _hc2, _hc3 = st.columns([3, 1, 1])
        _hc1.success(f"🟢 **Scraping en curso** — {_phase}")
        _hc2.metric("⏱ Tiempo", elapsed_str)
        _hc3.metric("PID", scrape_pid)

        # ── Progress bar ──────────────────────────────────────────────────────
        st.progress(_pct, text=f"{int(_pct * 100)}% completado")

        # ── Platform status badges ────────────────────────────────────────────
        if _enabled_platforms:
            _plat_cols = st.columns(len(_enabled_platforms))
            for _ci, _plat in enumerate(_enabled_platforms):
                _icon = _PLATFORM_ICONS.get(_plat, "🔵")
                if _plat in _prog["platforms_done"]:
                    _n    = _prog["lead_counts"].get(_plat, 0)
                    _plat_cols[_ci].success(f"{_icon} **{_plat.capitalize()}**\n\n✅ {_n} leads")
                elif _plat == _prog["current_platform"]:
                    _plat_cols[_ci].warning(f"{_icon} **{_plat.capitalize()}**\n\n🔄 En curso…")
                else:
                    _plat_cols[_ci].info(f"{_icon} **{_plat.capitalize()}**\n\n⏳ Pendiente")

        st.divider()

        # ── Controls ──────────────────────────────────────────────────────────
        _ctrl1, _ctrl2, _ctrl3 = st.columns([1, 1, 2])

        with _ctrl1:
            if st.button("🛑 Interrumpir", type="primary", use_container_width=True):
                if _kill_scrape(scrape_pid):
                    try:
                        _LOCK_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                    st.warning("Señal de interrupción enviada. El proceso terminará en unos segundos.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("No se pudo interrumpir el proceso.")

        with _ctrl2:
            if st.button("🔄 Actualizar", use_container_width=True):
                st.rerun()

        with _ctrl3:
            _auto_refresh = st.checkbox(
                "⏱ Auto-actualizar cada 15 s",
                value=False,
                help="Recarga automáticamente la página mientras el scraping esté en curso.",
            )

        st.caption(
            "⚠ La interrupción envía SIGTERM al proceso y a Chrome. "
            "Los leads ya recolectados **no se guardan** si el proceso no llegó a la fase de persistencia."
        )

        # Auto-refresh (executes last to avoid blocking UI render)
        if _auto_refresh:
            time.sleep(15)
            st.rerun()

    else:
        st.info("⚫ Sin actividad — el scraper está inactivo.")

        _run_opts = {
            "full":         ("▶ Completo (scrape + enriquecimiento)", ""),
            "scrape_only":  ("🔍 Solo scraping (sin visitar perfiles)", "--scrape-only"),
            "enrich_only":  ("🔬 Solo enriquecimiento (top perfiles)", "--enrich-only"),
        }
        _run_col1, _run_col2 = st.columns([2, 1])
        with _run_col1:
            _run_mode = st.selectbox(
                "Tipo de ejecución manual",
                options=list(_run_opts.keys()),
                format_func=lambda k: _run_opts[k][0],
                label_visibility="collapsed",
            )
        with _run_col2:
            if st.button("▶ Ejecutar ahora", type="primary", use_container_width=True):
                _script_abs = Path(__file__).parent / "run_scrape.sh"
                _cwd        = str(Path(__file__).parent)
                if not _script_abs.exists():
                    st.error(f"No se encontró run_scrape.sh en {_script_abs}")
                else:
                    _args = _run_opts[_run_mode][1]
                    _cmd  = ["bash", str(_script_abs)]
                    if _args:
                        _cmd.append(_args)
                    try:
                        proc = subprocess.Popen(
                            _cmd,
                            cwd=_cwd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                        )
                        # Wait briefly so the lock file has time to be created
                        time.sleep(2)
                        if _LOCK_FILE.exists():
                            st.success(f"✅ Proceso iniciado (PID {proc.pid}). Actualiza para ver el progreso.")
                        else:
                            st.warning(
                                "El proceso arrancó pero el lock file aún no existe. "
                                "Espera unos segundos y actualiza."
                            )
                        time.sleep(1)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error al iniciar el proceso: {exc}")

    st.divider()

    # ── Section 2: Log en vivo ─────────────────────────────────────────────────
    st.markdown("### 📋 Log de la última sesión")

    _log_col1, _log_col2, _log_col3 = st.columns([3, 1, 1])
    _log_filename, _log_content = _get_latest_log()
    _show_lines = _log_col3.selectbox("Últimas líneas", [30, 60, 80, 150], index=1, label_visibility="collapsed")

    if _log_filename:
        _log_col1.caption(f"Archivo: `logs/{_log_filename}`")
        if _log_col2.button("🔄 Actualizar log"):
            st.rerun()

        if is_running:
            st.info("🟢 Sesión en curso — actualiza para ver progreso reciente.")

        if _log_content:
            _log_lines = _log_content.splitlines()
            _visible = "\n".join(_log_lines[-_show_lines:])
            st.code(_visible, language="bash")
        else:
            st.warning("El archivo de log existe pero está vacío o no se pudo leer.")
    else:
        st.info("No hay logs todavía. Los logs aparecen después del primer scraping.")

    # Historial de sesiones
    if _LOG_DIR.exists():
        _all_logs = sorted(_LOG_DIR.glob("session_*.log"), reverse=True)
        if len(_all_logs) > 1:
            with st.expander(f"📁 Historial de sesiones ({len(_all_logs)} archivos)", expanded=False):
                for _lf in _all_logs[:15]:
                    _lsize = _lf.stat().st_size
                    _lname = _lf.stem.replace("session_", "")
                    _date = f"{_lname[:4]}-{_lname[4:6]}-{_lname[6:8]} {_lname[9:11]}:{_lname[11:13]}:{_lname[13:15]}" if len(_lname) >= 15 else _lname
                    st.caption(f"`{_date}` — {_lsize / 1024:.1f} KB")

    st.divider()

    # ── Section 3: Configuración del programador ───────────────────────────────
    st.markdown("### ⏰ Programación automática")
    st.caption(
        "El scraping corre vía `cron` mientras la PC está encendida. "
        "Recomendado: madrugada (3–5 AM) para no competir con otros programas."
    )

    _crontab_text = _read_crontab()
    _current_entries = _parse_scraper_crons(_crontab_text)

    # Show current schedule in human-readable form
    if _current_entries:
        st.markdown("**Programación actual:**")
        for _e in _current_entries:
            _day_indices = _dow_cron_to_idx(_e["dow"])
            _day_names = [_DAYS_ES[i] for i in _day_indices]
            _time_str = f"{_e['hour']:02d}:{_e['minute']:02d}"
            _args = _e["args"]
            if _args == "--scrape-only":
                _type = "Solo scraping"
            elif _args == "--enrich-only":
                _type = "Solo enriquecimiento"
            else:
                _type = "Completo (scrape + enriquecimiento)"
            _days_str = " · ".join(_day_names) if _day_names else _e["dow"]
            st.success(f"✅ **{_days_str}** a las **{_time_str}** — {_type}")
    else:
        st.warning("No hay ninguna ejecución automática programada actualmente.")

    st.markdown("---")

    # ── Cron editor ────────────────────────────────────────────────────────────
    with st.expander("✏️ Editar programación", expanded=not bool(_current_entries)):

        # Determine defaults from existing schedule or sensible fallback
        _default_days_idx  = [6]    # Sunday (index 6 in Mon-0 scheme)
        _default_hour      = 3
        _default_minute    = 0
        _default_run_type  = "full"
        _default_enrich_days_idx: list[int] = []
        _enable_enrich_midweek = False

        if _current_entries:
            # Derive defaults from first full entry (non --enrich-only)
            for _e in _current_entries:
                if _e["args"] != "--enrich-only":
                    _default_days_idx  = _dow_cron_to_idx(_e["dow"])
                    _default_hour      = _e["hour"]
                    _default_minute    = _e["minute"]
                    if _e["args"] == "--scrape-only":
                        _default_run_type = "scrape_only"
                    else:
                        _default_run_type = "full"
                    break
            # Look for a separate enrich-only entry
            for _e in _current_entries:
                if _e["args"] == "--enrich-only":
                    _enable_enrich_midweek = True
                    _default_enrich_days_idx = _dow_cron_to_idx(_e["dow"])
                    break

        st.markdown("**Sesión principal de scraping**")

        _ec1, _ec2, _ec3 = st.columns(3)

        _sel_days = _ec1.multiselect(
            "Días",
            options=list(range(7)),
            default=_default_days_idx,
            format_func=lambda i: _DAYS_ES[i],
        )

        _sel_hour = _ec2.number_input("Hora (0–23)", 0, 23, _default_hour)
        _sel_minute = _ec3.selectbox("Minuto", [0, 15, 30, 45], index=[0, 15, 30, 45].index(_default_minute) if _default_minute in [0, 15, 30, 45] else 0)

        _run_type_opts = {
            "full":        "Completo (scrape + enriquecimiento)",
            "scrape_only": "Solo scraping",
        }
        _sel_run_type = st.selectbox(
            "Tipo",
            options=list(_run_type_opts.keys()),
            format_func=lambda k: _run_type_opts[k],
            index=0 if _default_run_type == "full" else 1,
        )

        st.markdown("**Sesión adicional de enriquecimiento** (opcional)")
        st.caption("Visita top perfiles a mitad de semana para mejorar bio, followers y email sin scraping nuevo.")

        _enrich_toggle = st.checkbox("Agregar sesión de enriquecimiento adicional", value=_enable_enrich_midweek)

        _sel_enrich_days: list[int] = []
        if _enrich_toggle:
            _sel_enrich_days = st.multiselect(
                "Días para enriquecimiento",
                options=list(range(7)),
                default=_default_enrich_days_idx if _default_enrich_days_idx else [2],  # Wednesday
                format_func=lambda i: _DAYS_ES[i],
            )

        st.markdown("---")
        _save_col, _disable_col = st.columns(2)

        with _save_col:
            if st.button("💾 Guardar programación", type="primary"):
                if not _sel_days:
                    st.error("Selecciona al menos un día.")
                else:
                    _new_lines: list[str] = []

                    _main_args = "" if _sel_run_type == "full" else "--scrape-only"
                    _main_cron_days = [_DAY_TO_CRON[i] for i in _sel_days]
                    _new_lines.append(
                        f"# Sesión principal — {', '.join(_DAYS_ES[i] for i in _sel_days)} a las {_sel_hour:02d}:{_sel_minute:02d}"
                    )
                    _new_lines.append(_build_cron_line(int(_sel_hour), int(_sel_minute), _main_cron_days, _main_args))

                    if _enrich_toggle and _sel_enrich_days:
                        _enrich_cron_days = [_DAY_TO_CRON[i] for i in _sel_enrich_days]
                        _new_lines.append(
                            f"# Enriquecimiento — {', '.join(_DAYS_ES[i] for i in _sel_enrich_days)} a las {_sel_hour:02d}:{_sel_minute:02d}"
                        )
                        _new_lines.append(_build_cron_line(int(_sel_hour), int(_sel_minute), _enrich_cron_days, "--enrich-only"))

                    _new_crontab = _replace_scraper_crons(_crontab_text, _new_lines)
                    if _write_crontab(_new_crontab):
                        st.success("✅ Programación guardada correctamente.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Error al escribir el crontab. Verifica permisos.")

        with _disable_col:
            if _current_entries:
                if st.button("🗑 Eliminar toda la programación automática"):
                    _new_crontab = _replace_scraper_crons(_crontab_text, [])
                    if _write_crontab(_new_crontab):
                        st.warning("Programación automática eliminada. El scraper no correrá solo.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Error al escribir el crontab.")

    st.divider()

    # ── Section 4: Crontab raw view ────────────────────────────────────────────
    with st.expander("🔧 Ver crontab completo (avanzado)", expanded=False):
        st.caption("Vista de solo lectura del crontab actual del sistema.")
        if _crontab_text.strip():
            st.code(_crontab_text, language="bash")
        else:
            st.info("El crontab está vacío.")

# ── Tab: Documentación ─────────────────────────────────────────────────────────
with tab_docs:
    _docs_path = Path(__file__).parent / "docs" / "DOCUMENTATION.md"
    if _docs_path.exists():
        st.markdown(_docs_path.read_text(encoding="utf-8"), unsafe_allow_html=False)
    else:
        st.error(f"Archivo de documentación no encontrado: {_docs_path}")
