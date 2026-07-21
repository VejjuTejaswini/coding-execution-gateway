from __future__ import annotations

from collections import Counter

from .models import ComparisonConfig


def normalize_text(value: str) -> str:
    normalized = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.strip().split("\n")]
    return "\n".join(lines)


def compare_output(actual: str, expected: str, config: ComparisonConfig) -> bool:
    mode = config.mode

    if mode == "exact_text":
        return (actual or "") == (expected or "")

    if mode == "case_insensitive":
        return normalize_text(actual).casefold() == normalize_text(expected).casefold()

    if mode == "unordered_lines":
        actual_lines = [line.strip() for line in normalize_text(actual).split("\n") if line.strip()]
        expected_lines = [line.strip() for line in normalize_text(expected).split("\n") if line.strip()]
        return Counter(actual_lines) == Counter(expected_lines)

    if mode == "numeric_tolerance":
        try:
            return abs(float(normalize_text(actual)) - float(normalize_text(expected))) <= config.numeric_tolerance
        except (TypeError, ValueError):
            return False

    return normalize_text(actual) == normalize_text(expected)
