"""
CircuitBreaker — per-platform failure isolation.

States:
  CLOSED   → normal operation
  OPEN     → platform failing, skip completely
  HALF_OPEN → timeout elapsed, allow one probe request

When a platform returns too many consecutive errors (auth walls, bot detection,
network errors), the circuit opens and the scheduler skips that platform.
After a cooldown period it goes HALF_OPEN to test recovery.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """
    Per-platform circuit breaker.

    Args:
        platform:           Name used in log messages.
        failure_threshold:  Consecutive failures before OPEN.
        success_threshold:  Consecutive successes in HALF_OPEN before CLOSED.
        open_timeout_s:     Seconds to stay OPEN before going HALF_OPEN.
    """

    platform: str
    failure_threshold: int = 5
    success_threshold: int = 2
    open_timeout_s: float = 300.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _consecutive_failures: int = field(default=0, init=False, repr=False)
    _consecutive_successes: int = field(default=0, init=False, repr=False)
    _last_failure_ts: float = field(default=0.0, init=False, repr=False)
    _total_failures: int = field(default=0, init=False, repr=False)
    _total_successes: int = field(default=0, init=False, repr=False)
    _opened_at: float | None = field(default=None, init=False, repr=False)

    # ── Public API ────────────────────────────────────────────────────────────

    def allow_request(self) -> bool:
        """Return True if the platform should be attempted."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            elapsed = time.time() - (self._opened_at or 0.0)
            if elapsed >= self.open_timeout_s:
                logger.info(
                    "[circuit:%s] timeout elapsed (%.0fs) → HALF_OPEN", self.platform, elapsed
                )
                self._state = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN: allow exactly one probe
        return True

    def record_success(self) -> None:
        self._total_successes += 1
        self._consecutive_failures = 0

        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                logger.info("[circuit:%s] HALF_OPEN → CLOSED (recovered)", self.platform)
                self._state = CircuitState.CLOSED
                self._consecutive_successes = 0
        elif self._state == CircuitState.CLOSED:
            pass  # nothing to do

    def record_failure(self, reason: str = "") -> None:
        self._total_failures += 1
        self._consecutive_successes = 0
        self._last_failure_ts = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning("[circuit:%s] HALF_OPEN → OPEN (probe failed: %s)", self.platform, reason)
            self._open()
            return

        self._consecutive_failures += 1
        logger.debug(
            "[circuit:%s] failure %d/%d%s",
            self.platform,
            self._consecutive_failures,
            self.failure_threshold,
            f" ({reason})" if reason else "",
        )

        if self._consecutive_failures >= self.failure_threshold:
            logger.warning(
                "[circuit:%s] CLOSED → OPEN (threshold %d reached, reason: %s)",
                self.platform,
                self.failure_threshold,
                reason or "unknown",
            )
            self._open()

    def reset(self) -> None:
        """Manually reset the circuit (e.g. after manual login fix)."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at = None
        logger.info("[circuit:%s] manually reset → CLOSED", self.platform)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return not self.allow_request()

    @property
    def status(self) -> dict:
        return {
            "platform": self.platform,
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "open_for_s": round(time.time() - self._opened_at, 1) if self._opened_at else None,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.time()
        self._consecutive_failures = 0
        self._consecutive_successes = 0
