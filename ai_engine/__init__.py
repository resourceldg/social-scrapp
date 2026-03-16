"""
AI Reasoning Engine — structured local AI analysis via Ollama.

Upgrade over utils/llm_classifier.py:
  - JSON-mode structured output (validated + typed)
  - Multi-field AILeadAnalysis (not just buying_intent + lead_type)
  - Project context inference
  - Network relationship inference
  - Graceful fallback on every path

Public API
----------
from ai_engine import AILeadAnalysis, analyse_lead, analyse_project_cluster
from ai_engine import is_ai_available
"""
from ai_engine.ollama_client import is_ai_available
from ai_engine.lead_analyst import AILeadAnalysis, analyse_lead
from ai_engine.project_analyst import AIProjectAnalysis, analyse_project_cluster

__all__ = [
    "AILeadAnalysis", "analyse_lead",
    "AIProjectAnalysis", "analyse_project_cluster",
    "is_ai_available",
]
