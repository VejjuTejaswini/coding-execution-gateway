from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException

from .config import settings
from .execution_service import ExecutionService
from .language_registry import LanguageRegistry
from .models import ExecuteRequest, ExecuteResponse


app = FastAPI(
    title="Coding Execution Gateway",
    version="1.0.0",
    description="Universal stdin/stdout execution gateway for Judge0.",
)
registry = LanguageRegistry(settings)
service = ExecutionService(settings, registry)


def authorize(authorization: str | None = Header(default=None)) -> None:
    if not settings.adapter_api_key:
        return
    expected = f"Bearer {settings.adapter_api_key}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid adapter API key.")


@app.get("/health")
async def health() -> dict:
    try:
        languages = await registry.refresh()
        return {
            "status": "ok",
            "judge0_url": settings.judge0_url,
            "language_count": len(languages),
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "judge0_url": settings.judge0_url,
            "error": f"{type(exc).__name__}: {exc}",
        }


@app.get("/v1/capabilities", dependencies=[Depends(authorize)])
async def capabilities() -> dict:
    languages = await registry.capabilities()
    return {
        "status": "available",
        "execution_modes": ["stdin_stdout"],
        "languages": [item.model_dump() for item in languages],
    }


@app.post("/v1/execute", response_model=ExecuteResponse, dependencies=[Depends(authorize)])
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    return await service.execute(request)
