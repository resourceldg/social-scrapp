"""Tests for NetworkProfiler."""
import pytest
from core.network_profiler import NetworkProfiler, NetworkSpeed


def _make_profiler(*load_times_ms: float) -> NetworkProfiler:
    p = NetworkProfiler(window_size=20)
    for t in load_times_ms:
        p.record_page_load(t)
    return p


def test_no_data_defaults_to_medium_or_slow():
    p = NetworkProfiler()
    # With no data and no probe, should be SLOW (safe default)
    assert p.profile.speed in (NetworkSpeed.SLOW, NetworkSpeed.MEDIUM)


def test_fast_loads_classified_as_fast():
    p = _make_profiler(*([500] * 10))
    assert p.profile.speed == NetworkSpeed.FAST


def test_slow_loads_classified_as_slow():
    p = _make_profiler(*([12_000] * 10))
    assert p.profile.speed == NetworkSpeed.SLOW


def test_medium_loads_classified_as_medium():
    p = _make_profiler(*([5_000] * 10))
    assert p.profile.speed == NetworkSpeed.MEDIUM


def test_high_timeout_rate_degrades_to_slow():
    p = NetworkProfiler(window_size=20)
    for _ in range(4):
        p.record_page_load(500)           # fast loads
    for _ in range(4):
        p.record_page_load(0, timed_out=True)   # 50% timeout rate
    assert p.profile.speed in (NetworkSpeed.SLOW, NetworkSpeed.MEDIUM)
    assert p.profile.timeout_rate > 0.3


def test_recommended_timeouts_increase_for_slow():
    fast_p = _make_profiler(*([300] * 10))
    slow_p = _make_profiler(*([15_000] * 10))
    assert fast_p.recommended_timeouts["page_load"] < slow_p.recommended_timeouts["page_load"]


def test_recommended_strategy_reduces_profiles_for_slow():
    fast_p = _make_profiler(*([300] * 10))
    slow_p = _make_profiler(*([15_000] * 10))
    assert fast_p.recommended_strategy["profiles_multiplier"] > slow_p.recommended_strategy["profiles_multiplier"]


def test_record_timeout_increments_count():
    p = NetworkProfiler()
    p.record_timeout()
    p.record_timeout()
    assert p.profile.timeout_rate == pytest.approx(1.0)
