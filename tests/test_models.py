from app.models import ExecuteRequest


def test_legacy_test_fields_are_normalized():
    request = ExecuteRequest(
        language="python",
        code="print(input())",
        tests=[{"input": "hello\n", "expected": "hello"}],
    )
    assert request.source_code == "print(input())"
    assert request.tests[0].stdin == "hello\n"
    assert request.tests[0].expected_stdout == "hello"
