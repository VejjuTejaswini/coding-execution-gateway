# Coding Execution Gateway

A private FastAPI service that exposes a stable application contract while dynamically using every normal single-file runtime installed in Judge0.

## Endpoints

- `GET /health`
- `GET /v1/capabilities`
- `POST /v1/execute`

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Example execution request

```json
{
  "request_id": "run-001",
  "question_id": "sum-001",
  "language": "python",
  "execution_mode": "stdin_stdout",
  "code": "a, b = map(int, input().split())\nprint(a + b)",
  "tests": [
    {
      "test_id": "visible-1",
      "stdin": "10 20\n",
      "expected_stdout": "30",
      "hidden": false
    }
  ],
  "time_limit_ms": 3000,
  "memory_limit_mb": 256
}
```

The gateway dynamically calls Judge0 `/languages`, picks the newest runtime for a canonical language, submits test runs, polls results, compares stdout, and returns the result shape already expected by the interview backend.
