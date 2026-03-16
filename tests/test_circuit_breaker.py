"""Tests for the per-platform circuit breaker."""
import time
import pytest
from core.circuit_breaker import CircuitBreaker, CircuitState


def test_starts_closed():
    cb = CircuitBreaker("test")
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_single_success_prevents_open():
    cb = CircuitBreaker("test", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()       # resets consecutive count
    cb.record_failure()       # only 1 consecutive failure now
    assert cb.state == CircuitState.CLOSED


def test_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker("test", failure_threshold=1, open_timeout_s=0.05)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.1)
    # allow_request() triggers the HALF_OPEN transition
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_closes_after_successes_in_half_open():
    cb = CircuitBreaker("test", failure_threshold=1, open_timeout_s=0.05, success_threshold=2)
    cb.record_failure()
    time.sleep(0.1)
    cb.allow_request()                 # move to HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN   # not yet (needs 2)
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens():
    cb = CircuitBreaker("test", failure_threshold=1, open_timeout_s=0.05)
    cb.record_failure()
    time.sleep(0.1)
    cb.allow_request()
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure("still failing")
    assert cb.state == CircuitState.OPEN


def test_manual_reset():
    cb = CircuitBreaker("test", failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_status_dict_shape():
    cb = CircuitBreaker("instagram")
    cb.record_failure("bot detected")
    s = cb.status
    assert s["platform"] == "instagram"
    assert s["total_failures"] == 1
    assert "state" in s
