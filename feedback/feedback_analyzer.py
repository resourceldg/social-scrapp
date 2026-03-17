"""
Conversion feedback analyzer.

Compares scoring patterns of converted vs disqualified leads to surface
calibration hints — which score ranges, lead types, and platforms produce
the most true positives, and whether any dimension weights appear miscalibrated.

Results are returned as plain dicts so they can be displayed in the dashboard
or logged without any Streamlit / display dependency.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from statistics import mean, stdev

# Minimum sample size to make meaningful comparisons.
_MIN_SAMPLE = 3


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def analyze_conversions(db_path: Path) -> dict:
    """
    Join the ``conversions`` table with ``leads`` and compute calibration hints.

    Returns
    -------
    dict with keys:
        sample_size        : int  — total labelled leads
        converted_count    : int
        disqualified_count : int
        avg_score_converted   : float | None
        avg_score_disqualified: float | None
        score_separation      : float | None  — converted_avg - disqualified_avg
        recommended_min_score : int | None   — 10th-percentile score of converted leads
        top_lead_types_converted  : list[str]
        top_platforms_converted   : list[str]
        precision_by_score_band   : dict[str, float]  — "0-20", "21-40", etc.
        calibration_hints         : list[str]  — human-readable suggestions
        insufficient_data         : bool  — True when sample is too small
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                c.profile_url,
                c.outcome,
                l.score,
                l.lead_type,
                l.source_platform
            FROM conversions c
            LEFT JOIN leads l ON l.profile_url = c.profile_url
            """
        ).fetchall()

    if not rows:
        return {
            "insufficient_data": True,
            "sample_size": 0,
            "calibration_hints": ["No feedback data yet — mark some leads as converted or disqualified to enable calibration."],
        }

    converted = [dict(r) for r in rows if r["outcome"] == "converted"]
    disqualified = [dict(r) for r in rows if r["outcome"] == "disqualified"]
    total = len(converted) + len(disqualified)

    result: dict = {
        "sample_size": total,
        "converted_count": len(converted),
        "disqualified_count": len(disqualified),
        "insufficient_data": total < _MIN_SAMPLE,
    }

    if total < _MIN_SAMPLE:
        result["calibration_hints"] = [
            f"Only {total} labelled leads — need at least {_MIN_SAMPLE} to compute calibration hints."
        ]
        return result

    # ── Score statistics ───────────────────────────────────────────────────────
    conv_scores = [r["score"] for r in converted if r["score"] is not None]
    disq_scores = [r["score"] for r in disqualified if r["score"] is not None]

    avg_conv = mean(conv_scores) if conv_scores else None
    avg_disq = mean(disq_scores) if disq_scores else None
    separation = round(avg_conv - avg_disq, 1) if (avg_conv is not None and avg_disq is not None) else None

    result["avg_score_converted"] = round(avg_conv, 1) if avg_conv is not None else None
    result["avg_score_disqualified"] = round(avg_disq, 1) if avg_disq is not None else None
    result["score_separation"] = separation

    # Recommended minimum score: 10th percentile of converted (generous lower bound)
    if conv_scores:
        sorted_conv = sorted(conv_scores)
        p10_idx = max(0, int(len(sorted_conv) * 0.10) - 1)
        result["recommended_min_score"] = sorted_conv[p10_idx]
    else:
        result["recommended_min_score"] = None

    # ── Lead type breakdown ────────────────────────────────────────────────────
    conv_types: dict[str, int] = {}
    for r in converted:
        lt = r["lead_type"] or "unknown"
        conv_types[lt] = conv_types.get(lt, 0) + 1
    result["top_lead_types_converted"] = sorted(conv_types, key=conv_types.get, reverse=True)[:5]  # type: ignore[arg-type]

    # ── Platform breakdown ─────────────────────────────────────────────────────
    conv_platforms: dict[str, int] = {}
    for r in converted:
        plat = r["source_platform"] or "unknown"
        conv_platforms[plat] = conv_platforms.get(plat, 0) + 1
    result["top_platforms_converted"] = sorted(conv_platforms, key=conv_platforms.get, reverse=True)[:5]  # type: ignore[arg-type]

    # ── Precision by score band ────────────────────────────────────────────────
    bands = [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]
    precision_by_band: dict[str, float] = {}
    for lo, hi in bands:
        band_key = f"{lo}–{hi}"
        in_band_conv = sum(1 for r in converted if r["score"] is not None and lo <= r["score"] <= hi)
        in_band_disq = sum(1 for r in disqualified if r["score"] is not None and lo <= r["score"] <= hi)
        band_total = in_band_conv + in_band_disq
        precision_by_band[band_key] = round(in_band_conv / band_total, 2) if band_total else 0.0
    result["precision_by_score_band"] = precision_by_band

    # ── Calibration hints ─────────────────────────────────────────────────────
    hints: list[str] = []

    if separation is not None:
        if separation < 5:
            hints.append(
                f"Score separation is only {separation} pts. The model barely "
                "distinguishes converted from disqualified — consider reviewing "
                "dimension weights or enriching more leads before scoring."
            )
        elif separation >= 20:
            hints.append(
                f"Strong score separation ({separation} pts). Current thresholds "
                "appear well-calibrated."
            )
        else:
            hints.append(
                f"Moderate score separation ({separation} pts). "
                "Enriching more leads or tuning specifier/project weights may improve discrimination."
            )

    if result["recommended_min_score"] is not None:
        hints.append(
            f"Recommended min_score for enrichment: {result['recommended_min_score']} "
            f"(10th percentile of your converted leads)."
        )

    if conv_types:
        top_type = result["top_lead_types_converted"][0] if result["top_lead_types_converted"] else "unknown"
        hints.append(f"Best-converting lead type: '{top_type}'.")

    # Warn about high-scoring disqualified leads (false positives)
    high_score_disq = [r for r in disqualified if r["score"] is not None and r["score"] >= 60]
    if high_score_disq:
        hints.append(
            f"{len(high_score_disq)} disqualified lead(s) scored ≥60 — potential false positives. "
            "Check if 'spam_risk' or 'data_quality' dimensions need recalibration."
        )

    result["calibration_hints"] = hints
    return result
