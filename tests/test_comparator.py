from app.comparator import compare_output, normalize_text
from app.models import ComparisonConfig


def test_normalized_text_ignores_trailing_spaces_and_line_endings():
    assert normalize_text("A  \r\nB\n") == "A\nB"
    assert compare_output("A  \r\nB\n", "A\nB", ComparisonConfig())


def test_exact_text_is_strict():
    assert not compare_output("1\n", "1", ComparisonConfig(mode="exact_text"))


def test_numeric_tolerance():
    config = ComparisonConfig(mode="numeric_tolerance", numeric_tolerance=0.01)
    assert compare_output("1.005", "1.0", config)
