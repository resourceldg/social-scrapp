from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
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
                notes TEXT,
                score_histogram TEXT  -- JSON: {avg, bins:{}, by_platform:{}}
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
                scrape_count INTEGER DEFAULT 1,
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(profile_url),
                UNIQUE(social_handle, source_platform),
                UNIQUE(email, source_platform),
                FOREIGN KEY(run_id) REFERENCES scraping_runs(id)
            )
            """
        )

        # Safe migrations for scraping_runs
        existing_run_cols = {row[1] for row in conn.execute("PRAGMA table_info(scraping_runs)")}
        if "score_histogram" not in existing_run_cols:
            conn.execute("ALTER TABLE scraping_runs ADD COLUMN score_histogram TEXT")

        # Safe migrations for existing databases that lack the new columns
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
        if "scrape_count" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN scrape_count INTEGER DEFAULT 1")
        if "last_seen_at" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN last_seen_at TEXT")
        if "status" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN status TEXT DEFAULT 'nuevo'")
        if "enriched_at" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN enriched_at TEXT")
        if "lead_profile" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN lead_profile TEXT DEFAULT 'aspirational'")
        for _bi_col in ("opportunity_score", "buying_power_score", "specifier_score", "project_signal_score"):
            if _bi_col not in existing_cols:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {_bi_col} REAL DEFAULT 0.0")
        if "opportunity_classification" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN opportunity_classification TEXT DEFAULT 'low_signal'")

        # Conversion feedback table (Fase 3 — R17)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_url TEXT NOT NULL UNIQUE,
                outcome     TEXT NOT NULL,
                marked_at   TEXT NOT NULL,
                notes       TEXT
            )
            """
        )

        # Keyword performance tracker — feeds the UCB keyword ranker
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_stats (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                platform      TEXT NOT NULL,
                keyword       TEXT NOT NULL,
                run_count     INTEGER DEFAULT 0,
                total_leads   INTEGER DEFAULT 0,
                high_leads    INTEGER DEFAULT 0,  -- score >= HIGH_THRESHOLD
                warm_leads    INTEGER DEFAULT 0,  -- score >= WARM_THRESHOLD
                avg_score     REAL DEFAULT 0.0,
                type_counts   TEXT DEFAULT '{}',  -- JSON: {lead_type: count}
                last_run_at   TEXT,
                UNIQUE(platform, keyword)
            )
            """
        )

        # Per-run keyword performance log — one row per (run, platform, keyword)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_run_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER NOT NULL,
                platform    TEXT NOT NULL,
                keyword     TEXT NOT NULL,
                n_leads     INTEGER DEFAULT 0,
                avg_score   REAL DEFAULT 0.0,
                high_leads  INTEGER DEFAULT 0,
                type_counts TEXT DEFAULT '{}',
                logged_at   TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES scraping_runs(id)
            )
            """
        )

        # Safe migrations for keyword_stats
        existing_kw_cols = {row[1] for row in conn.execute("PRAGMA table_info(keyword_stats)")}
        if "type_counts" not in existing_kw_cols:
            conn.execute("ALTER TABLE keyword_stats ADD COLUMN type_counts TEXT DEFAULT '{}'")

        # ── New entity tables (Phase 2 — Project-First Intelligence) ───────────

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                name                    TEXT NOT NULL,
                website                 TEXT DEFAULT '',
                city                    TEXT DEFAULT '',
                country                 TEXT DEFAULT '',
                account_type            TEXT DEFAULT 'unknown',
                buying_power_score      REAL DEFAULT 0.0,
                specifier_score         REAL DEFAULT 0.0,
                authority_rank          REAL DEFAULT 0.0,
                network_influence_score REAL DEFAULT 0.0,
                lead_count              INTEGER DEFAULT 0,
                raw_data                TEXT DEFAULT '{}',
                created_at              TEXT NOT NULL,
                updated_at              TEXT NOT NULL,
                UNIQUE(name, website)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                name                     TEXT NOT NULL,
                project_type             TEXT DEFAULT 'unknown',
                status                   TEXT DEFAULT 'emerging',
                location_city            TEXT DEFAULT '',
                location_country         TEXT DEFAULT '',
                lat                      REAL DEFAULT 0.0,
                lon                      REAL DEFAULT 0.0,
                inferred_start           TEXT DEFAULT '',
                inferred_end             TEXT DEFAULT '',
                budget_tier              TEXT DEFAULT 'unknown',
                confidence               REAL DEFAULT 0.0,
                source_lead_ids          TEXT DEFAULT '[]',
                account_id               INTEGER,
                opportunity_density      REAL DEFAULT 0.0,
                ai_summary               TEXT DEFAULT '',
                ai_recommended_approach  TEXT DEFAULT '',
                ai_key_actors            TEXT DEFAULT '[]',
                signal_sources           TEXT DEFAULT '[]',
                raw_data                 TEXT DEFAULT '{}',
                created_at               TEXT NOT NULL,
                updated_at               TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                name                    TEXT NOT NULL,
                event_type              TEXT DEFAULT 'unknown',
                prestige_tier           TEXT DEFAULT 'unknown',
                location_city           TEXT DEFAULT '',
                location_country        TEXT DEFAULT '',
                lat                     REAL DEFAULT 0.0,
                lon                     REAL DEFAULT 0.0,
                event_date              TEXT DEFAULT '',
                event_year              INTEGER DEFAULT 0,
                participant_lead_ids    TEXT DEFAULT '[]',
                participant_count       INTEGER DEFAULT 0,
                detected_from_lead_ids  TEXT DEFAULT '[]',
                evidence_texts          TEXT DEFAULT '[]',
                event_signal_score      REAL DEFAULT 0.0,
                raw_data                TEXT DEFAULT '{}',
                created_at              TEXT NOT NULL,
                UNIQUE(name, event_year)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS relationships (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id                INTEGER NOT NULL,
                source_type              TEXT NOT NULL,
                target_id                INTEGER NOT NULL,
                target_type              TEXT NOT NULL,
                relation_type            TEXT NOT NULL,
                confidence               REAL DEFAULT 0.5,
                source_platform          TEXT DEFAULT '',
                evidence_text            TEXT DEFAULT '',
                corroborating_platforms  TEXT DEFAULT '[]',
                raw_data                 TEXT DEFAULT '{}',
                detected_at              TEXT NOT NULL,
                UNIQUE(source_id, source_type, target_id, target_type, relation_type)
            )
            """
        )

        # ── New lead columns for event + network intelligence ───────────────────
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
        for _new_col, _defn in (
            ("event_signal_score",      "REAL DEFAULT 0.0"),
            ("network_influence_score", "REAL DEFAULT 0.0"),
            ("actor_centrality_score",  "REAL DEFAULT 0.0"),
            ("account_id",              "INTEGER"),
            ("project_ids",             "TEXT DEFAULT '[]'"),
            ("event_ids",               "TEXT DEFAULT '[]'"),
        ):
            if _new_col not in existing_cols:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {_new_col} {_defn}")


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


def save_run_histogram(db_path: Path, run_id: int, leads: list) -> None:
    """Compute and persist the score distribution snapshot for a completed run.

    Stored as JSON with three keys:
      avg       — overall average score for this run
      bins      — {"0-10": n, "10-20": n, ..., "60+": n}
      by_platform — {"instagram": {"count": n, "avg": f}, ...}
    """
    if not leads:
        return

    _BINS = [
        ("0-10",  0,  10),
        ("10-20", 10, 20),
        ("20-30", 20, 30),
        ("30-40", 30, 40),
        ("40-50", 40, 50),
        ("50-60", 50, 60),
        ("60+",   60, 9999),
    ]

    scores = [getattr(l, "score", 0) or 0 for l in leads]
    avg = round(sum(scores) / len(scores), 2)

    bins: dict[str, int] = {label: 0 for label, _, _ in _BINS}
    for s in scores:
        for label, lo, hi in _BINS:
            if lo <= s < hi:
                bins[label] += 1
                break

    by_platform: dict[str, dict] = {}
    for lead in leads:
        plat = getattr(lead, "source_platform", "") or "unknown"
        sc = getattr(lead, "score", 0) or 0
        if plat not in by_platform:
            by_platform[plat] = {"count": 0, "sum": 0}
        by_platform[plat]["count"] += 1
        by_platform[plat]["sum"] += sc
    by_platform_out = {
        plat: {"count": v["count"], "avg": round(v["sum"] / v["count"], 2)}
        for plat, v in by_platform.items()
    }

    payload = json.dumps({"avg": avg, "bins": bins, "by_platform": by_platform_out}, ensure_ascii=False)
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE scraping_runs SET score_histogram = ? WHERE id = ?",
            (payload, run_id),
        )


def get_recent_profile_urls(db_path: Path, platform: str, cooldown_days: int) -> frozenset[str]:
    """Return normalised profile URLs for `platform` seen within `cooldown_days`."""
    since = (datetime.utcnow() - timedelta(days=cooldown_days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT profile_url FROM leads
            WHERE source_platform = ?
              AND profile_url IS NOT NULL
              AND last_seen_at >= ?
            """,
            (platform, since),
        ).fetchall()
    return frozenset(row["profile_url"].rstrip("/").lower() for row in rows if row["profile_url"])


def touch_seen_profiles(db_path: Path, profile_urls: Iterable[str]) -> None:
    """Increment scrape_count and refresh last_seen_at for profiles already in DB."""
    now = datetime.utcnow().isoformat()
    urls = list(profile_urls)
    if not urls:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            """
            UPDATE leads
            SET scrape_count = scrape_count + 1,
                last_seen_at = ?,
                updated_at = ?
            WHERE profile_url = ?
            """,
            [(now, now, url) for url in urls],
        )


def _lead_values(lead: Lead, run_id: int | None) -> tuple:
    now = datetime.utcnow().isoformat()
    lead_profile = getattr(lead, "lead_profile", None) or "aspirational"
    return (
        run_id,
        lead.source_platform,
        lead.search_term,
        lead.name,
        lead.social_handle or None,
        lead.profile_url or None,
        lead.email or None,
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
        lead_profile,
        1,    # scrape_count (initial; ON CONFLICT increments)
        now,  # last_seen_at
        now,  # created_at
        now,  # updated_at
    )


_UPSERT_SQL = """
    INSERT INTO leads (
        run_id, source_platform, search_term, name, social_handle, profile_url, email,
        phone, website, city, country, bio, category, lead_type, interest_signals,
        followers, engagement_hint, score, raw_data, lead_profile, scrape_count,
        last_seen_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        lead_profile=COALESCE(NULLIF(excluded.lead_profile, ''), leads.lead_profile),
        scrape_count=leads.scrape_count + 1,
        last_seen_at=excluded.last_seen_at,
        updated_at=excluded.updated_at
"""

_UPDATE_BY_HANDLE_SQL = """
    UPDATE leads SET
        run_id=?, score=MAX(score, ?), scrape_count=scrape_count+1,
        last_seen_at=?, updated_at=?,
        name=COALESCE(NULLIF(?, ''), name),
        bio=COALESCE(NULLIF(?, ''), bio),
        email=COALESCE(NULLIF(?, ''), email),
        website=COALESCE(NULLIF(?, ''), website),
        lead_type=COALESCE(NULLIF(?, ''), lead_type),
        followers=COALESCE(NULLIF(?, ''), followers)
    WHERE social_handle=? AND source_platform=?
"""

import logging as _log
_upsert_logger = _log.getLogger(__name__)


def upsert_leads(db_path: Path, leads: Iterable[Lead], run_id: int | None = None) -> int:
    leads = list(leads)
    if not leads:
        return 0

    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        inserted = 0
        for lead in leads:
            try:
                conn.execute(_UPSERT_SQL, _lead_values(lead, run_id))
                inserted += 1
            except sqlite3.IntegrityError:
                # Conflict on UNIQUE(social_handle, source_platform) or UNIQUE(email, source_platform)
                # — happens when the same handle appears with a different profile_url.
                # Try to update the existing row by handle+platform instead of crashing.
                try:
                    conn.execute(
                        _UPDATE_BY_HANDLE_SQL,
                        (
                            run_id, lead.score or 0,
                            now, now,
                            lead.name or "", lead.bio or "",
                            lead.email or "", lead.website or "",
                            lead.lead_type or "", lead.followers or "",
                            lead.social_handle or "", lead.source_platform or "",
                        ),
                    )
                    _upsert_logger.debug(
                        "Duplicate handle '%s'/%s — updated existing row instead of insert.",
                        lead.social_handle, lead.source_platform,
                    )
                    inserted += 1
                except Exception as exc:
                    _upsert_logger.warning(
                        "Skipping lead '%s'/%s — could not upsert: %s",
                        lead.social_handle, lead.source_platform, exc,
                    )
        return inserted


def update_lead_status(db_path: Path, profile_url: str, status: str) -> None:
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE profile_url = ?",
            (status, now, profile_url),
        )


def get_unenriched_leads(
    db_path: Path,
    min_score: int = 20,
    limit: int = 30,
    reenrich_after_days: int = 30,
) -> list[dict]:
    """Return leads that have not been enriched yet (or were enriched long ago)."""
    since = (datetime.utcnow() - timedelta(days=reenrich_after_days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM leads
            WHERE score >= ?
              AND status != 'descartado'
              AND (enriched_at IS NULL OR enriched_at < ?)
            ORDER BY score DESC
            LIMIT ?
            """,
            (min_score, since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_leads_enriched(db_path: Path, profile_urls: list[str]) -> None:
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        conn.executemany(
            "UPDATE leads SET enriched_at = ?, updated_at = ? WHERE profile_url = ?",
            [(now, now, url) for url in profile_urls],
        )


def update_enriched_lead(db_path: Path, lead) -> None:
    """Persist enriched fields back to the DB for a single lead."""
    now = datetime.utcnow().isoformat()
    # Extract BI scores stored in raw_data by _re_enrich()
    raw = lead.raw_data if isinstance(lead.raw_data, dict) else {}
    if not raw and isinstance(lead.raw_data, str):
        try:
            raw = json.loads(lead.raw_data)
        except Exception:
            raw = {}
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE leads SET
                name = COALESCE(NULLIF(?, ''), name),
                bio  = COALESCE(NULLIF(?, ''), bio),
                followers = COALESCE(NULLIF(?, ''), followers),
                email   = COALESCE(NULLIF(?, ''), email),
                phone   = COALESCE(NULLIF(?, ''), phone),
                website = COALESCE(NULLIF(?, ''), website),
                city    = COALESCE(NULLIF(?, ''), city),
                country = COALESCE(NULLIF(?, ''), country),
                lead_type        = COALESCE(NULLIF(?, ''), lead_type),
                engagement_hint  = COALESCE(NULLIF(?, ''), engagement_hint),
                interest_signals = CASE WHEN ? = '[]' THEN interest_signals ELSE ? END,
                score      = MAX(?, score),
                opportunity_score        = COALESCE(?, opportunity_score),
                buying_power_score       = COALESCE(?, buying_power_score),
                specifier_score          = COALESCE(?, specifier_score),
                project_signal_score     = COALESCE(?, project_signal_score),
                event_signal_score       = COALESCE(?, event_signal_score),
                opportunity_classification = COALESCE(NULLIF(?, ''), opportunity_classification),
                enriched_at = ?,
                updated_at  = ?
            WHERE profile_url = ?
            """,
            (
                lead.name, lead.bio, lead.followers,
                lead.email, lead.phone, lead.website,
                lead.city, lead.country,
                lead.lead_type,
                getattr(lead, "engagement_hint", "") or "",
                json.dumps(lead.interest_signals, ensure_ascii=False),
                json.dumps(lead.interest_signals, ensure_ascii=False),
                lead.score,
                raw.get("opportunity_score"),
                raw.get("buying_power_score"),
                raw.get("specifier_score"),
                raw.get("project_signal_score"),
                raw.get("event_signal_score"),
                raw.get("opportunity_classification", ""),
                now, now,
                lead.profile_url,
            ),
        )


def _localize_timestamps(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Convert UTC ISO timestamp columns to America/Argentina/Buenos_Aires (UTC-3)."""
    tz = "America/Argentina/Buenos_Aires"
    for col in cols:
        if col in df.columns:
            df[col] = (
                pd.to_datetime(df[col], utc=True, errors="coerce")
                .dt.tz_convert(tz)
                .dt.strftime("%Y-%m-%d %H:%M")
            )
    return df


def get_leads_df(db_path: Path) -> pd.DataFrame:
    with _connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM leads ORDER BY score DESC, updated_at DESC", conn)
    df = _localize_timestamps(df, ["created_at", "updated_at", "last_seen_at"])
    # Coerce numeric columns — SQLite can return them as object when NULLs exist
    for col in ("score", "scrape_count"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def get_runs_df(db_path: Path) -> pd.DataFrame:
    with _connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM scraping_runs ORDER BY id DESC", conn)
    return _localize_timestamps(df, ["started_at", "finished_at"])


def get_platform_evolution_df(db_path: Path) -> pd.DataFrame:
    """Return cumulative avg score per platform at each completed run.

    For each completed run, computes the average score of ALL leads
    (not just new ones) that existed in the DB at run completion time.
    This gives a true picture of platform quality evolution over time.

    Returns a DataFrame with columns: run_id, run, plataforma, avg, count
    """
    query = """
        SELECT
            sr.id              AS run_id,
            '#' || sr.id || ' ' || SUBSTR(sr.started_at, 1, 10) AS run,
            l.source_platform  AS plataforma,
            COUNT(*)           AS count,
            ROUND(AVG(COALESCE(l.score, 0)), 2) AS avg
        FROM scraping_runs sr
        JOIN leads l
          ON l.created_at <= COALESCE(sr.finished_at, sr.started_at)
        WHERE sr.status = 'completed'
          AND l.source_platform IS NOT NULL
          AND l.source_platform != ''
        GROUP BY sr.id, l.source_platform
        ORDER BY sr.id, l.source_platform
    """
    with _connect(db_path) as conn:
        df = pd.read_sql_query(query, conn)
    return df


# ── Keyword performance tracking ──────────────────────────────────────────────

def update_keyword_stats(
    db_path: Path,
    platform: str,
    keyword: str,
    leads: list,  # list of Lead objects found via this keyword this run
    high_threshold: int = 35,
    warm_threshold: int = 15,
) -> None:
    """Record per-keyword run timing metadata after each scraping run.

    Only run_count and last_run_at are written here because lead scores at
    scrape time are pre-enrichment (~2-4) and unreliable for quality ranking.
    Quality metrics (avg_score, high_leads, warm_leads, total_leads) are
    rebuilt from enriched lead scores by recalculate_keyword_stats(), which
    runs at the start of each main.py invocation.
    """
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO keyword_stats (platform, keyword, run_count, last_run_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(platform, keyword) DO UPDATE SET
                run_count   = run_count + 1,
                last_run_at = excluded.last_run_at
            """,
            (platform, keyword, now),
        )


def recalculate_keyword_stats(db_path: Path, high_threshold: int = 35, warm_threshold: int = 15) -> int:
    """Recompute keyword_stats avg_score, high_leads, and warm_leads from current lead scores.

    Only considers leads that have been through profile enrichment (enriched_at IS NOT NULL).
    Pre-enrichment scores (~2-4) are meaningless for keyword quality ranking — a lead
    that scores 2 at scrape time but 45 after enrichment should count as a high-quality
    lead, not as a low-quality one.

    Preserves run_count and last_run_at (timing metadata, not quality metadata).

    Returns the number of (platform, keyword) rows updated.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_platform, search_term,
                   COUNT(*)                                          AS n_total,
                   SUM(CASE WHEN score >= ? THEN 1 ELSE 0 END)      AS n_high,
                   SUM(CASE WHEN score >= ? THEN 1 ELSE 0 END)      AS n_warm,
                   AVG(CAST(score AS REAL))                          AS avg_s
            FROM leads
            WHERE search_term IS NOT NULL AND search_term != ''
              AND enriched_at IS NOT NULL
            GROUP BY source_platform, search_term
            """,
            (high_threshold, warm_threshold),
        ).fetchall()

        # Also fetch lead_type distribution per keyword for UCB type_bonus
        type_rows = conn.execute(
            """
            SELECT source_platform, search_term, lead_type, COUNT(*) AS cnt
            FROM leads
            WHERE search_term IS NOT NULL AND search_term != ''
              AND enriched_at IS NOT NULL
              AND lead_type IS NOT NULL AND lead_type != '' AND lead_type != 'none'
            GROUP BY source_platform, search_term, lead_type
            """,
        ).fetchall()
        type_map: dict[tuple, dict] = {}
        for plat, kw, lt, cnt in type_rows:
            type_map.setdefault((plat, kw), {})[lt] = cnt

        updated = 0
        for r in rows:
            platform, keyword, n_total, n_high, n_warm, avg_s = r
            avg_s = round(avg_s or 0.0, 4)
            n_high = n_high or 0
            n_warm = n_warm or 0
            type_counts_json = json.dumps(
                type_map.get((platform, keyword), {}), ensure_ascii=False
            )
            cur = conn.execute(
                """
                UPDATE keyword_stats
                SET total_leads = ?, high_leads = ?, warm_leads = ?,
                    avg_score = ?, type_counts = ?
                WHERE platform = ? AND keyword = ?
                """,
                (n_total, n_high, n_warm, avg_s, type_counts_json, platform, keyword),
            )
            updated += cur.rowcount

    return updated


def get_keyword_stats_df(db_path: Path) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT ks.*,
                   COALESCE(conv.conversion_count, 0) AS conversion_count
            FROM keyword_stats ks
            LEFT JOIN (
                SELECT l.search_term, l.source_platform, COUNT(c.id) AS conversion_count
                FROM leads l
                JOIN conversions c ON c.profile_url = l.profile_url
                GROUP BY l.search_term, l.source_platform
            ) conv ON conv.search_term = ks.keyword AND conv.source_platform = ks.platform
            ORDER BY avg_score DESC
            """,
            conn,
        )


def propose_keyword_candidates(db_path: Path, platform: str, keywords: list[str]) -> int:
    """Store newly-discovered keyword candidates (run_count=0) for future runs.

    UCB1 assigns max priority (float('inf')) to keywords with no run history,
    so candidates will be tried before any already-evaluated keyword.
    Returns the number of new candidates inserted (existing ones are ignored).
    """
    now = datetime.utcnow().isoformat()
    inserted = 0
    with _connect(db_path) as conn:
        for kw in keywords:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO keyword_stats
                        (platform, keyword, run_count, total_leads, high_leads,
                         warm_leads, avg_score, type_counts, last_run_at)
                    VALUES (?, ?, 0, 0, 0, 0, 0.0, '{}', ?)
                    """,
                    (platform, kw, now),
                )
                inserted += 1
            except Exception:
                pass
    return inserted


def get_keyword_candidates(db_path: Path, platform: str) -> list[str]:
    """Return keywords stored for this platform that have never been run (run_count=0).

    These are hashtag-derived or manually-added candidates waiting to be explored.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT keyword FROM keyword_stats WHERE platform=? AND run_count=0",
            (platform,),
        ).fetchall()
    return [row["keyword"] for row in rows]


def log_keyword_run(
    db_path: Path,
    run_id: int,
    platform: str,
    keyword: str,
    leads: list,
    high_threshold: int = 35,
) -> None:
    """Record per-run keyword performance in keyword_run_log.

    Called alongside update_keyword_stats so evolution can be charted
    in the dashboard (one row per run per keyword).
    """
    if not leads:
        n_leads = n_high = 0
        avg = 0.0
        type_counts_json = "{}"
    else:
        scores = [getattr(l, "score", 0) or 0 for l in leads]
        n_leads = len(scores)
        n_high = sum(1 for s in scores if s >= high_threshold)
        avg = round(sum(scores) / n_leads, 2)
        from collections import Counter as _Counter
        tc = dict(_Counter(
            (getattr(l, "lead_type", "") or "")
            for l in leads if getattr(l, "lead_type", "")
        ))
        type_counts_json = json.dumps(tc, ensure_ascii=False)

    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO keyword_run_log
                (run_id, platform, keyword, n_leads, avg_score, high_leads, type_counts, logged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, platform, keyword, n_leads, avg, n_high, type_counts_json, now),
        )


def get_keyword_run_history_df(db_path: Path, platform: str | None = None) -> pd.DataFrame:
    """Return per-run keyword performance history for charting.

    Joins with scraping_runs to get the run start date as label.
    """
    where = "WHERE krl.platform = ?" if platform else ""
    params = (platform,) if platform else ()
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                krl.run_id,
                sr.started_at,
                krl.platform,
                krl.keyword,
                krl.n_leads,
                krl.avg_score,
                krl.high_leads,
                krl.type_counts
            FROM keyword_run_log krl
            JOIN scraping_runs sr ON sr.id = krl.run_id
            {where}
            ORDER BY krl.run_id ASC, krl.keyword ASC
            """,
            conn,
            params=params,
        )
