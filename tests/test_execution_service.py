import pytest

from app.config import Settings
from app.execution_service import ExecutionService
from app.models import ExecuteRequest, RuntimeCapability


class FakeRegistry:
    def __init__(self, canonical_language: str = "python"):
        self.runtime = RuntimeCapability(
            runtime_id="judge0-999",
            judge0_language_id=999,
            canonical_language=canonical_language,
            display_name="Fake Runtime",
            judge0_name="Fake Runtime",
            editor_language=canonical_language,
            execution_modes=["stdin_stdout"],
        )

    async def resolve(self, *, runtime_id, language):
        return self.runtime


@pytest.mark.asyncio
async def test_visible_and_hidden_results_are_split():
    service = ExecutionService(Settings(), FakeRegistry())

    async def fake_execute_many(**kwargs):
        return [
            {
                "stdout": "3\n",
                "stderr": None,
                "compile_output": None,
                "time": "0.01",
                "memory": 1024,
                "status": {"id": 3, "description": "Accepted"},
            },
            {
                "stdout": "7\n",
                "stderr": None,
                "compile_output": None,
                "time": "0.02",
                "memory": 2048,
                "status": {"id": 3, "description": "Accepted"},
            },
        ]

    service.judge0.execute_many = fake_execute_many
    request = ExecuteRequest(
        language="python",
        code="a, b = map(int, input().split()); print(a + b)",
        tests=[
            {"stdin": "1 2\n", "expected_stdout": "3", "hidden": False},
            {"stdin": "3 4\n", "expected_stdout": "7", "hidden": True},
        ],
    )
    response = await service.execute(request)
    assert response.status == "passed"
    assert len(response.visible_test_results) == 1
    assert len(response.hidden_test_results) == 1


@pytest.mark.asyncio
async def test_sql_setup_is_prepended_to_candidate_query():
    service = ExecutionService(Settings(), FakeRegistry("sql"))
    captured = {}

    async def fake_execute_many(**kwargs):
        captured.update(kwargs)
        return [
            {
                "stdout": "2\n",
                "stderr": None,
                "compile_output": None,
                "time": "0.01",
                "memory": 1024,
                "status": {"id": 3, "description": "Accepted"},
            }
        ]

    service.judge0.execute_many = fake_execute_many
    request = ExecuteRequest(
        language="sql",
        code="SELECT COUNT(*) FROM employees;",
        tests=[
            {
                "stdin": "CREATE TABLE employees(id INTEGER); INSERT INTO employees VALUES (1), (2);",
                "expected_stdout": "2",
            }
        ],
    )
    response = await service.execute(request)
    assert response.status == "passed"
    assert captured["stdins"] == [""]
    assert "CREATE TABLE employees" in captured["source_codes"][0]
    assert "SELECT COUNT(*)" in captured["source_codes"][0]
