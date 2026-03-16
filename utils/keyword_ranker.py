"""
Keyword ranker using Upper Confidence Bound (UCB1).

After each scraping run, per-keyword stats (avg_score, run_count, high_leads)
are written to `keyword_stats` in SQLite.  Before the next run this module
re-ranks the keyword list so the scraper tries the most promising keywords
first — and gradually de-prioritises or drops keywords that consistently
produce low-quality leads.

Scoring levels used:
  HIGH  score >= 8   — direct buyer / specifier
  WARM  score >= 4   — related professional, could convert
  COLD  score <  4   — off-niche, penalised

UCB formula (Thompson-like upper bound):
  ucb = avg_score + C * sqrt(ln(total_runs + 1) / (run_count + 1))

Where C controls exploration vs. exploitation.  Keywords with no history get
the maximum UCB so they are always tried at least once.

Pruning rule: after MIN_RUNS runs, if avg_score < PRUNE_BELOW and
high_leads == 0, the keyword is flagged as 'dead' and moved to the end
(it still runs so it can recover, but won't block good keywords).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from utils.database import get_keyword_stats_df

logger = logging.getLogger(__name__)

# Tuning knobs
UCB_C = 2.0          # exploration coefficient — higher = try unknowns more aggressively
MIN_RUNS = 3         # minimum runs before a keyword can be pruned
PRUNE_BELOW = 8.0    # avg_score below this after MIN_RUNS → de-prioritise
HIGH_THRESHOLD = 35  # mirrors update_keyword_stats (calibrated for 0-100 scoring scale)
WARM_THRESHOLD = 15

# Normalization constant — approximate observed max avg_score across keywords
_MAX_AVG_SCORE = 60.0

# Lead types relevant to the art/design/collectibles niche.
# Used to compute type_ratio bonus in the UCB reward function.
DESIRED_TYPES: frozenset[str] = frozenset([
    "galeria", "coleccionista", "arquitecto", "interiorista", "curador",
    "diseñador", "estudio", "artista", "maker", "marca premium",
    "hospitality", "tienda decoracion",
])


def rank_keywords(
    db_path: Path,
    platform: str,
    keywords: list[str],
) -> list[str]:
    """Return `keywords` sorted by UCB score (best first).

    Keywords with no history are placed after known-good but before known-dead,
    so new keywords always get at least MIN_RUNS attempts before judgement.
    """
    if not keywords:
        return keywords

    try:
        df = get_keyword_stats_df(db_path)
        stats = (
            df[df["platform"] == platform]
            .set_index("keyword")
            .to_dict("index")
        )
    except Exception as exc:
        logger.debug("keyword_ranker: could not read stats (%s) — using original order", exc)
        return keywords

    total_runs = sum(v.get("run_count", 0) for v in stats.values()) if stats else 0

    def ucb(kw: str) -> float:
        if kw not in stats:
            # Unknown keyword — assign maximum UCB to ensure it runs
            return float("inf")
        s = stats[kw]
        run_count = s.get("run_count", 0) or 0
        if run_count == 0:
            # Proposed candidate never yet run — always try before evaluated keywords
            return float("inf")
        avg = min(s.get("avg_score", 0.0) or 0.0, _MAX_AVG_SCORE)

        # Type affinity bonus (0–20 pts): fraction of leads that are desired types
        try:
            type_counts = json.loads(s.get("type_counts", "{}") or "{}")
            total_typed = sum(type_counts.values())
            desired = sum(v for k, v in type_counts.items() if k in DESIRED_TYPES)
            type_ratio = desired / total_typed if total_typed > 0 else 0.5
        except Exception:
            type_ratio = 0.5
        type_bonus = type_ratio * 20.0  # 0–20 pts

        # Conversion bonus (flat 15 pts if at least one confirmed conversion)
        conversion_count = s.get("conversion_count", 0) or 0
        conv_bonus = 15.0 if conversion_count > 0 else 0.0

        exploration = UCB_C * math.sqrt(math.log(total_runs + 1) / (run_count + 1))
        return avg + type_bonus + conv_bonus + exploration

    def is_dead(kw: str) -> bool:
        if kw not in stats:
            return False
        s = stats[kw]
        return (
            (s.get("run_count", 0) or 0) >= MIN_RUNS
            and (s.get("avg_score", 0.0) or 0.0) < PRUNE_BELOW
            and (s.get("high_leads", 0) or 0) == 0
        )

    alive = [kw for kw in keywords if not is_dead(kw)]
    dead  = [kw for kw in keywords if is_dead(kw)]

    alive_ranked = sorted(alive, key=ucb, reverse=True)
    dead_ranked  = sorted(dead,  key=ucb, reverse=True)

    if dead:
        logger.info(
            "keyword_ranker [%s]: %d active, %d de-prioritised: %s",
            platform, len(alive_ranked), len(dead_ranked),
            ", ".join(f"'{k}'" for k in dead_ranked),
        )

    ranked = alive_ranked + dead_ranked

    # Log top/bottom for visibility
    if stats:
        logger.info(
            "keyword_ranker [%s]: order → %s",
            platform,
            " | ".join(ranked[:5]) + (" …" if len(ranked) > 5 else ""),
        )

    return ranked


def summarise_keyword_performance(db_path: Path, platform: str) -> str:
    """Return a human-readable summary of keyword performance for logging."""
    try:
        df = get_keyword_stats_df(db_path)
        df = df[df["platform"] == platform]
    except Exception:
        return "(no keyword stats available)"

    if df.empty:
        return "(no data yet)"

    lines = []
    for _, row in df.iterrows():
        dead = (
            row["run_count"] >= MIN_RUNS
            and row["avg_score"] < PRUNE_BELOW
            and row["high_leads"] == 0
        )
        flag = " ⚠ de-prioritised" if dead else ""
        # Summarise type distribution
        try:
            tc = json.loads(row.get("type_counts", "{}") or "{}")
            desired = {k: v for k, v in tc.items() if k in DESIRED_TYPES}
            type_str = " types=[" + ",".join(f"{k}:{v}" for k, v in desired.items()) + "]" if desired else ""
        except Exception:
            type_str = ""
        conv = int(row.get("conversion_count", 0) or 0)
        conv_str = f" conv={conv}" if conv > 0 else ""
        lines.append(
            f"  {row['keyword'][:40]:<40} "
            f"runs={int(row['run_count'])} "
            f"leads={int(row['total_leads'])} "
            f"high={int(row['high_leads'])} "
            f"avg={row['avg_score']:.1f}"
            f"{type_str}{conv_str}{flag}"
        )

    return "\n".join(lines) if lines else "(empty)"
