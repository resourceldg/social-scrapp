from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from models import Lead


DB_NAME = "leads.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scraping_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                total_raw_leads INTEGER DEFAULT 0,
                total_deduped_leads INTEGER DEFAULT 0,
                notes TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                source_platform TEXT NOT NULL,
                search_term TEXT,
                name TEXT,
                social_handle TEXT,
                profile_url TEXT,
                email TEXT,
                phone TEXT,
                website TEXT,
                city TEXT,
                country TEXT,
                bio TEXT,
                category TEXT,
                lead_type TEXT,
                interest_signals TEXT,
                followers TEXT,
                engagement_hint TEXT,
                score INTEGER DEFAULT 0,
                raw_data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(profile_url),
                UNIQUE(social_handle, source_platform),
                UNIQUE(email, source_platform),
                FOREIGN KEY(run_id) REFERENCES scraping_runs(id)
            )
            """
        )


def start_run(db_path: Path, notes: str = "") -> int:
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO scraping_runs(started_at, status, notes) VALUES (?, 'running', ?)",
            (now, notes),
        )
        return int(cur.lastrowid)


def finish_run(db_path: Path, run_id: int, status: str, total_raw_leads: int, total_deduped_leads: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE scraping_runs
            SET finished_at = ?, status = ?, total_raw_leads = ?, total_deduped_leads = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), status, total_raw_leads, total_deduped_leads, run_id),
        )


def _lead_values(lead: Lead, run_id: int | None) -> tuple:
    now = datetime.utcnow().isoformat()
    return (
        run_id,
        lead.source_platform,
        lead.search_term,
        lead.name,
        lead.social_handle,
        lead.profile_url,
        lead.email,
        lead.phone,
        lead.website,
        lead.city,
        lead.country,
        lead.bio,
        lead.category,
        lead.lead_type,
        json.dumps(lead.interest_signals, ensure_ascii=False),
        lead.followers,
        lead.engagement_hint,
        lead.score,
        json.dumps(lead.raw_data, ensure_ascii=False),
        now,
        now,
    )


def upsert_leads(db_path: Path, leads: Iterable[Lead], run_id: int | None = None) -> int:
    leads = list(leads)
    if not leads:
        return 0

    with _connect(db_path) as conn:
        inserted = 0
        for lead in leads:
            conn.execute(
                """
                INSERT INTO leads (
                    run_id, source_platform, search_term, name, social_handle, profile_url, email,
                    phone, website, city, country, bio, category, lead_type, interest_signals,
                    followers, engagement_hint, score, raw_data, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_url) DO UPDATE SET
                    run_id=excluded.run_id,
                    search_term=COALESCE(excluded.search_term, leads.search_term),
                    name=COALESCE(NULLIF(excluded.name, ''), leads.name),
                    social_handle=COALESCE(NULLIF(excluded.social_handle, ''), leads.social_handle),
                    email=COALESCE(NULLIF(excluded.email, ''), leads.email),
                    phone=COALESCE(NULLIF(excluded.phone, ''), leads.phone),
                    website=COALESCE(NULLIF(excluded.website, ''), leads.website),
                    city=COALESCE(NULLIF(excluded.city, ''), leads.city),
                    country=COALESCE(NULLIF(excluded.country, ''), leads.country),
                    bio=COALESCE(NULLIF(excluded.bio, ''), leads.bio),
                    category=COALESCE(NULLIF(excluded.category, ''), leads.category),
                    lead_type=COALESCE(NULLIF(excluded.lead_type, ''), leads.lead_type),
                    interest_signals=CASE WHEN excluded.interest_signals='[]' THEN leads.interest_signals ELSE excluded.interest_signals END,
                    followers=COALESCE(NULLIF(excluded.followers, ''), leads.followers),
                    engagement_hint=COALESCE(NULLIF(excluded.engagement_hint, ''), leads.engagement_hint),
                    score=MAX(excluded.score, leads.score),
                    raw_data=COALESCE(NULLIF(excluded.raw_data, '{}'), leads.raw_data),
                    updated_at=excluded.updated_at
                """,
                _lead_values(lead, run_id),
            )
            inserted += 1
        return inserted


def get_leads_df(db_path: Path) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM leads ORDER BY score DESC, updated_at DESC", conn)


def get_runs_df(db_path: Path) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM scraping_runs ORDER BY id DESC", conn)
