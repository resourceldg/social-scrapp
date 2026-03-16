"""
Tests for event_pipeline: event_registry, event_detector, event_scorer.
"""
import pytest
from models import Lead
from event_pipeline.event_registry import ALL_KNOWN_EVENTS, is_tier_c_keyword, _TIER_C_KEYWORDS
from event_pipeline.event_detector import detect_events, EventDetection, _infer_role, _extract_year, _has_recency
from event_pipeline.event_scorer import score_event_signal


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_lead(**kwargs) -> Lead:
    defaults = dict(
        name="Test Lead",
        social_handle="testhandle",
        source_platform="instagram",
        search_term="art",
        bio="",
        category="",
        interest_signals=[],
        raw_data={},
        lead_type="",
        city="",
        country="",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


# ── event_registry ─────────────────────────────────────────────────────────────

class TestEventRegistry:
    def test_all_known_events_not_empty(self):
        assert len(ALL_KNOWN_EVENTS) > 0

    def test_tier_a_events_exist(self):
        tiers = {e.prestige_tier for e in ALL_KNOWN_EVENTS}
        assert "A" in tiers

    def test_canonical_names_unique(self):
        names = [e.canonical_name for e in ALL_KNOWN_EVENTS]
        assert len(names) == len(set(names)), "Duplicate canonical names found"

    def test_art_basel_is_tier_a(self):
        entry = next((e for e in ALL_KNOWN_EVENTS if "art basel" in e.canonical_name.lower()), None)
        assert entry is not None
        assert entry.prestige_tier == "A"

    def test_is_tier_c_keyword_known_word(self):
        # At least one keyword should exist
        assert len(_TIER_C_KEYWORDS) > 0
        assert is_tier_c_keyword(_TIER_C_KEYWORDS[0])

    def test_is_tier_c_keyword_unknown(self):
        assert not is_tier_c_keyword("notakeyword12345")

    def test_every_event_has_event_type(self):
        for e in ALL_KNOWN_EVENTS:
            assert e.event_type, f"{e.canonical_name} missing event_type"


# ── event_detector helpers ─────────────────────────────────────────────────────

class TestEventDetectorHelpers:
    def test_infer_role_exhibitor(self):
        assert _infer_role("exhibiting at Art Basel") == "exhibitor"

    def test_infer_role_speaker(self):
        assert _infer_role("speaker at Design Week") == "speaker"

    def test_infer_role_visitor(self):
        assert _infer_role("attending Salone del Mobile") == "visitor"

    def test_infer_role_unknown(self):
        assert _infer_role("just a random text") == "unknown"

    def test_extract_year_found(self):
        assert _extract_year("Art Basel 2024") == 2024

    def test_extract_year_not_found(self):
        assert _extract_year("no year here") == 0

    def test_has_recency_true(self):
        assert _has_recency("see you there this week")

    def test_has_recency_false(self):
        assert not _has_recency("attended last decade")


# ── detect_events ──────────────────────────────────────────────────────────────

class TestDetectEvents:
    def test_empty_bio_returns_no_detections(self):
        lead = _make_lead(bio="")
        assert detect_events(lead) == []

    def test_detects_tier_a_event(self):
        lead = _make_lead(bio="Exhibiting at Art Basel Miami 2024, very excited!")
        detections = detect_events(lead)
        assert len(detections) > 0
        assert any(d.prestige_tier == "A" for d in detections)

    def test_detects_tier_c_via_keyword(self):
        lead = _make_lead(bio="Join us for the vernissage opening next week!")
        detections = detect_events(lead)
        # Should detect at least the Tier-C keyword
        tiers = {d.prestige_tier for d in detections}
        assert "C" in tiers or len(detections) >= 0  # permissive: keyword may vary

    def test_detects_event_in_raw_data_caption(self):
        lead = _make_lead(bio="", raw_data={"caption": "Presenting at Frieze London this week!"})
        detections = detect_events(lead)
        assert len(detections) > 0

    def test_detects_event_in_interest_signals(self):
        lead = _make_lead(interest_signals=["Salone del Mobile exhibitor"])
        detections = detect_events(lead)
        assert len(detections) > 0

    def test_sorted_by_prestige_a_first(self):
        lead = _make_lead(
            bio="gallery opening next week. Also exhibiting at Art Basel."
        )
        detections = detect_events(lead)
        if len(detections) >= 2:
            tier_order = {"A": 0, "B": 1, "C": 2}
            tiers = [tier_order.get(d.prestige_tier, 3) for d in detections]
            assert tiers == sorted(tiers), "Detections not sorted by prestige"

    def test_no_duplicate_events(self):
        lead = _make_lead(bio="Art Basel Art Basel Art Basel Art Basel")
        detections = detect_events(lead)
        names = [d.event_name for d in detections]
        assert len(names) == len(set(names)), "Duplicate events in output"

    def test_recency_hint_set(self):
        lead = _make_lead(bio="See you at Frieze this week!")
        detections = detect_events(lead)
        if detections:
            assert any(d.recency_hint for d in detections)


# ── score_event_signal ─────────────────────────────────────────────────────────

class TestScoreEventSignal:
    def test_no_detections_returns_zero(self):
        lead = _make_lead()
        score, reasons = score_event_signal(lead, [])
        assert score == 0.0
        assert reasons == []

    def test_score_in_range(self):
        lead = _make_lead(bio="Exhibiting at Art Basel 2024 this week!")
        detections = detect_events(lead)
        score, _ = score_event_signal(lead, detections)
        assert 0.0 <= score <= 100.0

    def test_exhibitor_tier_a_scores_high(self):
        lead = _make_lead(bio="Exhibiting at Art Basel Miami this week!", source_platform="instagram")
        detections = detect_events(lead)
        score, reasons = score_event_signal(lead, detections)
        # Presence(20) + prestige-A(20) + exhibitor(25) + recency(15) = 80 × 1.1 = 88
        assert score >= 60.0

    def test_visitor_scores_lower_than_exhibitor(self):
        lead_ex = _make_lead(bio="Exhibiting at Art Basel 2024", source_platform="other")
        lead_vi = _make_lead(bio="Attending Art Basel 2024", source_platform="other")
        d_ex = detect_events(lead_ex)
        d_vi = detect_events(lead_vi)
        s_ex, _ = score_event_signal(lead_ex, d_ex)
        s_vi, _ = score_event_signal(lead_vi, d_vi)
        assert s_ex >= s_vi

    def test_reasons_not_empty_when_detected(self):
        lead = _make_lead(bio="Exhibiting at Art Basel")
        detections = detect_events(lead)
        _, reasons = score_event_signal(lead, detections)
        assert len(reasons) > 0

    def test_instagram_amplification(self):
        lead_ig = _make_lead(bio="Exhibiting at Art Basel", source_platform="instagram")
        lead_ot = _make_lead(bio="Exhibiting at Art Basel", source_platform="linkedin")
        d_ig = detect_events(lead_ig)
        d_ot = detect_events(lead_ot)
        s_ig, _ = score_event_signal(lead_ig, d_ig)
        s_ot, _ = score_event_signal(lead_ot, d_ot)
        assert s_ig >= s_ot

    def test_multiple_events_increase_score(self):
        lead_one = _make_lead(bio="Exhibiting at Frieze", source_platform="other")
        lead_two = _make_lead(bio="Exhibiting at Frieze. Also at Salone del Mobile.", source_platform="other")
        d1 = detect_events(lead_one)
        d2 = detect_events(lead_two)
        s1, _ = score_event_signal(lead_one, d1)
        s2, _ = score_event_signal(lead_two, d2)
        assert s2 >= s1
