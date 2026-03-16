"""
Shared pattern-matching utilities for signal extractors.

All extractors use left-word-boundary matching:
  \bpattern  — prevents "artisan" from matching "art", "partnership" from
               matching "partner", but allows plurals and compound suffixes
               ("architects" from "architect", "luxury" suffix in compounds).

Patterns are pre-compiled at module-import time to avoid repeated re.compile()
calls in tight loops.
"""
from __future__ import annotations

import re
from typing import Sequence


def compile_patterns(
    patterns: Sequence[tuple],
) -> list[tuple]:
    """
    Pre-compile a list of pattern tuples, prepending a left word boundary.

    Supports both 2-tuples (pattern, weight) and 3-tuples
    (pattern, weight, extra) used by the project extractor.

    Returns a new list where the pattern string is replaced by its compiled
    regex, keeping all other elements unchanged.

    Example
    -------
    Input:  [("architect", 1.0), ("interior design", 0.9)]
    Output: [(re.compile(r'\barchitect', ...), 1.0), ...]
    """
    compiled = []
    for entry in patterns:
        pat = entry[0]
        rest = entry[1:]
        compiled_re = re.compile(
            r"\b" + re.escape(pat),
            re.IGNORECASE | re.UNICODE,
        )
        compiled.append((pat, compiled_re, *rest))
    return compiled


def wb_search(compiled_entry: tuple, text: str) -> bool:
    """
    Return True if the pre-compiled regex in the entry matches *text*.

    Entry format: (original_pattern_str, compiled_re, *remaining_fields)
    """
    return bool(compiled_entry[1].search(text))
