"""Business intelligence scoring modules.

Three independent, explainable scores that complement the base lead score:

- BuyingPowerScore  — economic capacity or budget authority
- SpecifierScore    — influence over purchasing decisions
- ProjectSignalScore — active project with purchase timing
"""
from scoring.business_scoring.buying_power import score_buying_power
from scoring.business_scoring.project_signal import score_project_signal
from scoring.business_scoring.specifier import score_specifier

__all__ = ["score_buying_power", "score_specifier", "score_project_signal"]
