from app.config import Settings
from app.judge0_client import Judge0Client


def test_submission_payload_disables_per_process_memory_limit_by_default():
    client = Judge0Client(
        Settings(
            enable_per_process_and_thread_memory_limit=False,
        )
    )

    payload = client._submission_payload(
        language_id=62,
        source_code="public class Main {}",
        stdin="",
        time_limit_ms=3000,
        memory_limit_mb=256,
    )

    assert payload["memory_limit"] == 256 * 1024
    assert payload["enable_per_process_and_thread_memory_limit"] is False


def test_submission_payload_allows_explicit_per_process_memory_override():
    client = Judge0Client(
        Settings(
            enable_per_process_and_thread_memory_limit=True,
        )
    )

    payload = client._submission_payload(
        language_id=62,
        source_code="public class Main {}",
        stdin="",
        time_limit_ms=3000,
        memory_limit_mb=256,
    )

    assert payload["enable_per_process_and_thread_memory_limit"] is True