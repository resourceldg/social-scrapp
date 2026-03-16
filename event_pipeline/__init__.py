"""
Event Intelligence Pipeline.

Detects, classifies, and scores industry events from lead signals.

Public API
----------
from event_pipeline import detect_events, score_event_signal

detect_events(lead) -> list[EventDetection]
score_event_signal(lead, detections) -> float  # 0–100
"""
from event_pipeline.event_detector import EventDetection, detect_events
from event_pipeline.event_scorer import score_event_signal

__all__ = ["EventDetection", "detect_events", "score_event_signal"]
