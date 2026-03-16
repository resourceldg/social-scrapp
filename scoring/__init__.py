# Lazy-safe exports: avoid eager ScoreEngine import to prevent circular imports.
# (score_engine → opportunity_engine → scoring.weights_config → scoring → cycle)
# Import ScoreEngine directly: from scoring.score_engine import ScoreEngine
from scoring.score_result import LeadScoreResult
from scoring.weights_config import RankingMode

__all__ = ["LeadScoreResult", "RankingMode"]
