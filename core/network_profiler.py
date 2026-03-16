"""
NetworkProfiler — detects connection quality in real time.

Two phases:
1. Pre-browser HTTP probe via urllib (fast, no Selenium overhead).
2. Continuous update from observed Selenium page-load times.

The resulting NetworkProfile drives the AdaptiveScheduler to decide
scroll depth, platform count, timeout values, and retry aggressiveness.
"""
from __future__ import annotations

import logging
import statistics
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Latency thresholds (ms) for the HTTP probe
_PROBE_SLOW_MS = 2500
_PROBE_MEDIUM_MS = 800

# Rolling-average thresholds for observed page loads (ms)
_PAGE_SLOW_MS = 9000
_PAGE_MEDIUM_MS = 4000

# Lightweight probe URL — Android connectivity check endpoint (returns HTTP 204, zero payload)
_PROBE_URL = "http://connectivitycheck.gstatic.com/generate_204"
_PROBE_TIMEOUT_S = 12


class NetworkSpeed(str, Enum):
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"


@dataclass
class NetworkProfile:
    speed: NetworkSpeed
    avg_load_ms: float
    p95_load_ms: float
    timeout_rate: float   # 0.0–1.0
    sample_count: int
    probe_latency_ms: float | None = None

    def __str__(self) -> str:
        return (
            f"NetworkProfile(speed={self.speed.value}, "
            f"avg={self.avg_load_ms:.0f}ms, "
            f"p95={self.p95_load_ms:.0f}ms, "
            f"timeouts={self.timeout_rate:.0%}, "
            f"n={self.sample_count})"
        )


class NetworkProfiler:
    """
    Tracks network quality and recommends scraping strategy.

    Usage:
        profiler = NetworkProfiler()
        speed = profiler.probe_initial_speed()   # before browser starts
        # … during scraping …
        profiler.record_page_load(elapsed_ms, timed_out=False)
        profile = profiler.profile
        timeouts = profiler.recommended_timeouts
    """

    def __init__(self, window_size: int = 15) -> None:
        self._load_times: deque[float] = deque(maxlen=window_size)
        self._total_attempts: int = 0
        self._timeout_count: int = 0
        self._probe_ms: float | None = None

    # ── Phase 1: pre-browser HTTP probe ──────────────────────────────────────

    def probe_initial_speed(self) -> NetworkSpeed:
        """
        Issue a single lightweight HTTP request and classify connection speed.
        Falls back to SLOW if anything fails (offline, DNS issue, etc.).
        """
        try:
            t0 = time.perf_counter()
            req = urllib.request.Request(
                _PROBE_URL,
                headers={"User-Agent": "Mozilla/5.0 (compatible; SpeedProbe/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT_S):
                pass
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._probe_ms = elapsed_ms

            if elapsed_ms > _PROBE_SLOW_MS:
                speed = NetworkSpeed.SLOW
            elif elapsed_ms > _PROBE_MEDIUM_MS:
                speed = NetworkSpeed.MEDIUM
            else:
                speed = NetworkSpeed.FAST

            logger.info("Network probe: %.0f ms → %s", elapsed_ms, speed.value)
            return speed

        except Exception as exc:
            logger.warning("Network probe failed (%s) — assuming SLOW", exc)
            self._probe_ms = None
            return NetworkSpeed.SLOW

    # ── Phase 2: continuous updates from page loads ───────────────────────────

    def record_page_load(self, elapsed_ms: float, timed_out: bool = False) -> None:
        """Call this after every driver.get() / WebDriverWait completes."""
        self._total_attempts += 1
        if timed_out:
            self._timeout_count += 1
        else:
            self._load_times.append(elapsed_ms)

    def record_timeout(self) -> None:
        """Convenience alias for a hard timeout."""
        self.record_page_load(0.0, timed_out=True)

    # ── Derived profile ───────────────────────────────────────────────────────

    @property
    def profile(self) -> NetworkProfile:
        timeout_rate = (
            self._timeout_count / self._total_attempts
            if self._total_attempts > 0
            else 0.0
        )

        if not self._load_times:
            # No page load data yet — use probe result or default to MEDIUM
            if self._probe_ms is None:
                speed = NetworkSpeed.SLOW
            elif self._probe_ms > _PROBE_SLOW_MS:
                speed = NetworkSpeed.SLOW
            elif self._probe_ms > _PROBE_MEDIUM_MS:
                speed = NetworkSpeed.MEDIUM
            else:
                speed = NetworkSpeed.FAST

            return NetworkProfile(
                speed=speed,
                avg_load_ms=self._probe_ms or 0.0,
                p95_load_ms=self._probe_ms or 0.0,
                timeout_rate=timeout_rate,
                sample_count=0,
                probe_latency_ms=self._probe_ms,
            )

        times_sorted = sorted(self._load_times)
        avg = statistics.mean(times_sorted)
        p95_idx = min(int(len(times_sorted) * 0.95), len(times_sorted) - 1)
        p95 = times_sorted[p95_idx]

        # Combine load-time signal and timeout rate
        if avg > _PAGE_SLOW_MS or timeout_rate > 0.30:
            speed = NetworkSpeed.SLOW
        elif avg > _PAGE_MEDIUM_MS or timeout_rate > 0.12:
            speed = NetworkSpeed.MEDIUM
        else:
            speed = NetworkSpeed.FAST

        # Probe says slow but no page loads yet? Respect probe.
        if (
            self._probe_ms
            and self._probe_ms > _PROBE_SLOW_MS
            and speed == NetworkSpeed.FAST
            and len(self._load_times) < 3
        ):
            speed = NetworkSpeed.MEDIUM

        return NetworkProfile(
            speed=speed,
            avg_load_ms=avg,
            p95_load_ms=p95,
            timeout_rate=timeout_rate,
            sample_count=len(self._load_times),
            probe_latency_ms=self._probe_ms,
        )

    # ── Strategy recommendations ──────────────────────────────────────────────

    @property
    def recommended_timeouts(self) -> dict[str, float]:
        """Selenium-friendly timeout values in seconds."""
        speed = self.profile.speed
        if speed == NetworkSpeed.SLOW:
            return {
                "page_load": 90.0,
                "element_wait": 45.0,
                "scroll_poll_interval": 0.6,
                "scroll_max_wait": 10.0,
            }
        if speed == NetworkSpeed.MEDIUM:
            return {
                "page_load": 60.0,
                "element_wait": 30.0,
                "scroll_poll_interval": 0.4,
                "scroll_max_wait": 6.0,
            }
        return {
            "page_load": 30.0,
            "element_wait": 15.0,
            "scroll_poll_interval": 0.3,
            "scroll_max_wait": 4.0,
        }

    @property
    def recommended_strategy(self) -> dict[str, float | int]:
        """High-level scraping strategy parameters."""
        speed = self.profile.speed
        if speed == NetworkSpeed.SLOW:
            return {
                "max_scrolls": 2,
                "profiles_multiplier": 0.50,
                "max_platforms": 2,
                "retry_base_delay": 10.0,
                "inter_keyword_delay_extra": 2.0,
            }
        if speed == NetworkSpeed.MEDIUM:
            return {
                "max_scrolls": 3,
                "profiles_multiplier": 0.75,
                "max_platforms": 4,
                "retry_base_delay": 6.0,
                "inter_keyword_delay_extra": 1.0,
            }
        return {
            "max_scrolls": 4,
            "profiles_multiplier": 1.00,
            "max_platforms": 6,
            "retry_base_delay": 4.0,
            "inter_keyword_delay_extra": 0.0,
        }
