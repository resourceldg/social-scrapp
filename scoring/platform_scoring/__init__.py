"""Platform-specific scoring modules.

Each module exposes a single function:

    score_platform_specific(lead: Lead) -> tuple[float, list[str]]

Returns a score in 0–100 and a list of human-readable reason strings.
"""
