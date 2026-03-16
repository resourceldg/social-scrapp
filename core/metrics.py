"""
MetricsCollector — lightweight observability for scraping sessions.

Tracks per-platform counters (loads, leads, errors, retries) and computes
derived KPIs (success rate, avg load time, cost-per-lead proxy).

After the session, call .save_report() to persist a JSON file and
.log_summary() to print a readable table via the logger.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PlatformMetrics:
    platform: str
    keywords_attempted: int = 0
    keywords_succeeded: int = 0
    keywords_failed: int = 0
    leads_found: int = 0
    total_load_ms: float = 0.0
    page_loads: int = 0
    timeouts: int = 0
    retries: int = 0
    circuit_breaks: int = 0
    route_failures: int = 0
    _start: float = field(default_factory=time.time, repr=False)

    # ── Derived ───────────────────────────────────────────────────────────────

    @property
    def avg_load_ms(self) -> float:
        return self.total_load_ms / self.page_loads if self.page_loads else 0.0

    @property
    def success_rate(self) -> float:
        return self.keywords_succeeded / self.keywords_attempted if self.keywords_attempted else 0.0

    @property
    def leads_per_keyword(self) -> float:
        return self.leads_found / self.keywords_succeeded if self.keywords_succeeded else 0.0

    @property
    def elapsed_s(self) -> float:
        return time.time() - self._start

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "leads_found": self.leads_found,
            "keywords_attempted": self.keywords_attempted,
            "keywords_succeeded": self.keywords_succeeded,
            "keywords_failed": self.keywords_failed,
            "success_rate": round(self.success_rate, 3),
            "leads_per_keyword": round(self.leads_per_keyword, 2),
            "avg_load_ms": round(self.avg_load_ms),
            "page_loads": self.page_loads,
            "timeouts": self.timeouts,
            "retries": self.retries,
            "circuit_breaks": self.circuit_breaks,
            "route_failures": self.route_failures,
            "elapsed_s": round(self.elapsed_s, 1),
        }


class MetricsCollector:
    """Collects and reports scraping session metrics."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._platforms: dict[str, PlatformMetrics] = {}
        self._session_start = time.time()

    def platform(self, name: str) -> PlatformMetrics:
        if name not in self._platforms:
            self._platforms[name] = PlatformMetrics(platform=name)
        return self._platforms[name]

    # ── Recording events ──────────────────────────────────────────────────────

    def record_page_load(
        self, platform: str, elapsed_ms: float, timed_out: bool = False
    ) -> None:
        m = self.platform(platform)
        m.page_loads += 1
        m.total_load_ms += elapsed_ms
        if timed_out:
            m.timeouts += 1

    def record_keyword(
        self,
        platform: str,
        *,
        leads: int,
        success: bool,
        retries: int = 0,
    ) -> None:
        m = self.platform(platform)
        m.keywords_attempted += 1
        m.retries += retries
        if success:
            m.keywords_succeeded += 1
            m.leads_found += leads
        else:
            m.keywords_failed += 1

    def record_circuit_break(self, platform: str) -> None:
        self.platform(platform).circuit_breaks += 1

    def record_route_failure(self, platform: str) -> None:
        self.platform(platform).route_failures += 1

    # ── Output ────────────────────────────────────────────────────────────────

    def session_summary(self) -> dict:
        elapsed = time.time() - self._session_start
        total_leads = sum(m.leads_found for m in self._platforms.values())
        return {
            "session_elapsed_s": round(elapsed, 1),
            "total_leads": total_leads,
            "platforms": {
                name: m.to_dict() for name, m in sorted(self._platforms.items())
            },
        }

    def log_summary(self) -> None:
        summary = self.session_summary()
        logger.info(
            "==== Session complete — %.0fs — %d leads total ====",
            summary["session_elapsed_s"],
            summary["total_leads"],
        )
        header = (
            f"  {'Platform':<12} {'Leads':>6} {'KW ok/tot':>10} "
            f"{'Rate':>6} {'AvgLoad':>8} {'T/O':>4} {'Retry':>6}"
        )
        logger.info(header)
        for name, s in summary["platforms"].items():
            logger.info(
                "  %-12s %6d   %4d/%-4d  %5.0f%%  %7.0fms  %3d  %5d",
                name,
                s["leads_found"],
                s["keywords_succeeded"],
                s["keywords_attempted"],
                s["success_rate"] * 100,
                s["avg_load_ms"],
                s["timeouts"],
                s["retries"],
            )

    def save_report(self, filename: str = "metrics.json") -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        path.write_text(
            json.dumps(self.session_summary(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Metrics saved → %s", path)
        return path
