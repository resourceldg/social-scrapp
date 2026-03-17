"""
Conversion feedback store.

Persists outcome labels (converted / disqualified) for individual leads
in the same SQLite database used by the scraper pipeline.

Outcomes feed into feedback_analyzer.py which computes scoring calibration
suggestions by comparing signal patterns of converted vs rejected leads.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_VALID_OUTCOMES = frozenset({"converted", "disqualified"})


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


class FeedbackStore:
    """
    Thin wrapper around the ``conversions`` table in the leads SQLite database.

    Parameters
    ----------
    db_path : Path
        Path to the SQLite database (same as AppConfig.sqlite_db_path).
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_table()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_table(self) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversions (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_url TEXT NOT NULL UNIQUE,
                    outcome    TEXT NOT NULL,
                    marked_at  TEXT NOT NULL,
                    notes      TEXT
                )
                """
            )

    # ── Write ─────────────────────────────────────────────────────────────────

    def mark_outcome(
        self, profile_url: str, outcome: str, notes: str = ""
    ) -> None:
        """
        Record or update the outcome for a lead.

        Parameters
        ----------
        profile_url : str
            Unique identifier for the lead (must exist in ``leads`` table).
        outcome : str
            ``"converted"`` — lead became a customer / qualified opportunity.
            ``"disqualified"`` — lead was explicitly ruled out.
        notes : str
            Optional free-text note (e.g., "Bought sculpture set", "Wrong market").
        """
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {_VALID_OUTCOMES}, got {outcome!r}")
        now = datetime.now(timezone.utc).isoformat()
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversions (profile_url, outcome, marked_at, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_url) DO UPDATE SET
                    outcome   = excluded.outcome,
                    marked_at = excluded.marked_at,
                    notes     = excluded.notes
                """,
                (profile_url, outcome, now, notes),
            )

    def mark_converted(self, profile_url: str, notes: str = "") -> None:
        """Convenience wrapper — mark a lead as converted."""
        self.mark_outcome(profile_url, "converted", notes)

    def mark_disqualified(self, profile_url: str, notes: str = "") -> None:
        """Convenience wrapper — mark a lead as disqualified."""
        self.mark_outcome(profile_url, "disqualified", notes)

    def delete_outcome(self, profile_url: str) -> None:
        """Remove a previously recorded outcome (e.g., to correct a mistake)."""
        with _connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM conversions WHERE profile_url = ?", (profile_url,)
            )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_outcomes(self) -> list[dict]:
        """Return all recorded outcomes, newest first."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM conversions ORDER BY marked_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_converted(self) -> list[str]:
        """Return profile URLs of all converted leads."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT profile_url FROM conversions WHERE outcome = 'converted'"
            ).fetchall()
        return [r["profile_url"] for r in rows]

    def get_disqualified(self) -> list[str]:
        """Return profile URLs of all disqualified leads."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT profile_url FROM conversions WHERE outcome = 'disqualified'"
            ).fetchall()
        return [r["profile_url"] for r in rows]

    def outcome_counts(self) -> dict[str, int]:
        """Return {'converted': N, 'disqualified': M, 'total': N+M}."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT outcome, COUNT(*) as n FROM conversions GROUP BY outcome"
            ).fetchall()
        counts = {r["outcome"]: r["n"] for r in rows}
        counts["total"] = sum(counts.values())
        return counts
