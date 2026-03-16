"""
AdaptiveScheduler — decides which platforms to run, in what order,
and with what resource limits for each session.

Decision factors:
  1. NetworkProfile → how much to scrape per platform
  2. CircuitBreaker states → skip broken platforms
  3. AppConfig → enabled flags + keyword lists
  4. Random shuffle of lower-priority platforms to vary coverage across runs

Output: an ordered list of PlatformTask objects, each carrying
adapted limits (max_profiles, max_keywords, scrolls_per_page).
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from core.circuit_breaker import CircuitBreaker
from core.metrics import MetricsCollector
from core.network_profiler import NetworkProfiler, NetworkSpeed

logger = logging.getLogger(__name__)

# Default priority order: most stable / highest lead quality first.
# LinkedIn and Reddit are less bot-sensitive and have richer public data.
_DEFAULT_PRIORITY: list[str] = [
    "linkedin",
    "reddit",
    "pinterest",
    "twitter",
    "facebook",
    "instagram",
]


@dataclass
class PlatformTask:
    """Adapted scraping task for one platform in this session."""

    name: str
    scraper: object            # concrete scraper instance (typed as object to avoid circular import)
    max_profiles: int
    max_keywords: int
    scrolls_per_page: int
    retry_base_delay: float
    priority: int              # 1 = run first


class AdaptiveScheduler:
    """
    Builds an execution plan for the session based on network quality
    and per-platform circuit breaker states.
    """

    def __init__(
        self,
        profiler: NetworkProfiler,
        breakers: dict[str, CircuitBreaker],
        config,                               # AppConfig (avoid circular import)
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.profiler = profiler
        self.breakers = breakers
        self.config = config
        self.metrics = metrics

    def build_plan(
        self,
        scrapers: list[tuple[str, object]],   # [(platform_name, scraper_instance), …]
    ) -> list[PlatformTask]:
        """
        Return an ordered list of PlatformTask objects for this session.
        Platforms are filtered, ordered, and resource-limited adaptively.
        """
        profile = self.profiler.profile
        strategy = self.profiler.recommended_strategy
        timeouts = self.profiler.recommended_timeouts

        logger.info(
            "Scheduler: network=%s  avg=%.0fms  p95=%.0fms  timeout_rate=%.0f%%",
            profile.speed.value,
            profile.avg_load_ms,
            profile.p95_load_ms,
            profile.timeout_rate * 100,
        )

        # ── Step 1: filter to enabled + circuit-not-open platforms ───────────
        available: list[tuple[str, object]] = []
        for name, scraper in scrapers:
            if not getattr(self.config, f"{name}_enabled", True):
                continue
            breaker = self.breakers.get(name)
            if breaker and not breaker.allow_request():
                logger.warning(
                    "Scheduler: [%s] circuit=%s → skipping",
                    name,
                    breaker.state.value,
                )
                if self.metrics:
                    self.metrics.record_circuit_break(name)
                continue
            available.append((name, scraper))

        # ── Step 2: sort by priority ─────────────────────────────────────────
        priority_map = {p: i for i, p in enumerate(_DEFAULT_PRIORITY)}
        available.sort(key=lambda t: priority_map.get(t[0], len(_DEFAULT_PRIORITY)))

        # ── Step 3: cap platforms for slow connections ────────────────────────
        max_platforms = int(strategy["max_platforms"])
        if len(available) > max_platforms:
            logger.info(
                "Scheduler: network=%s → capping %d/%d platforms",
                profile.speed.value,
                max_platforms,
                len(available),
            )
            # Keep the top-priority ones, shuffle the rest for variety
            top = available[:2]
            rest = available[2:]
            random.shuffle(rest)
            available = (top + rest)[:max_platforms]

        # ── Step 4: build task list ───────────────────────────────────────────
        tasks: list[PlatformTask] = []
        for idx, (name, scraper) in enumerate(available):
            kw_list = getattr(self.config, f"{name}_keywords", [])
            # Respect the global keyword session cap + per-task network reduction
            kw_cap = self.config.max_searches_per_session
            if profile.speed == NetworkSpeed.SLOW:
                kw_cap = max(2, kw_cap // 2)

            max_kw = min(len(kw_list), kw_cap)
            max_profiles = max(
                5,
                int(self.config.max_profiles_per_platform * strategy["profiles_multiplier"]),
            )
            scrolls = int(strategy["max_scrolls"])
            retry_delay = float(strategy["retry_base_delay"])

            tasks.append(
                PlatformTask(
                    name=name,
                    scraper=scraper,
                    max_profiles=max_profiles,
                    max_keywords=max_kw,
                    scrolls_per_page=scrolls,
                    retry_base_delay=retry_delay,
                    priority=idx + 1,
                )
            )

        # ── Step 5: log the plan ──────────────────────────────────────────────
        logger.info("Scheduler plan (%d platforms):", len(tasks))
        for t in tasks:
            logger.info(
                "  [%d] %-12s  kw=%d  profiles=%d  scrolls=%d  retry_delay=%.0fs",
                t.priority,
                t.name,
                t.max_keywords,
                t.max_profiles,
                t.scrolls_per_page,
                t.retry_base_delay,
            )

        return tasks
