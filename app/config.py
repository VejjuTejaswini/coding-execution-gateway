from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        os.environ[key] = value


_load_env_file(Path(__file__).resolve().parents[1] / ".env")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    judge0_url: str = os.getenv("JUDGE0_URL", "http://judge0-server:2358").rstrip("/")
    judge0_auth_header: str = os.getenv("JUDGE0_AUTH_HEADER", "").strip()
    judge0_auth_token: str = os.getenv("JUDGE0_AUTH_TOKEN", "").strip()
    adapter_api_key: str = os.getenv("CODING_ADAPTER_API_KEY", "").strip()
    request_timeout_sec: float = float(os.getenv("JUDGE0_REQUEST_TIMEOUT_SEC", "15") or "15")
    poll_interval_sec: float = float(os.getenv("JUDGE0_POLL_INTERVAL_SEC", "0.5") or "0.5")
    max_poll_sec: float = float(os.getenv("JUDGE0_MAX_POLL_SEC", "20") or "20")
    language_cache_ttl_sec: float = float(os.getenv("JUDGE0_LANGUAGE_CACHE_TTL_SEC", "300") or "300")
    max_code_chars: int = int(os.getenv("CODING_MAX_CODE_CHARS", "50000") or "50000")
    max_tests: int = int(os.getenv("CODING_MAX_TESTS", "50") or "50")
    max_output_chars: int = int(os.getenv("CODING_MAX_OUTPUT_CHARS", "20000") or "20000")
    default_time_limit_ms: int = int(os.getenv("CODING_DEFAULT_TIME_LIMIT_MS", "3000") or "3000")
    default_memory_limit_mb: int = int(os.getenv("CODING_DEFAULT_MEMORY_LIMIT_MB", "256") or "256")
    jvm_min_memory_limit_mb: int = int(os.getenv("CODING_JVM_MIN_MEMORY_LIMIT_MB", "500") or "500")
    dotnet_min_memory_limit_mb: int = int(os.getenv("CODING_DOTNET_MIN_MEMORY_LIMIT_MB", "256") or "256")
    enable_per_process_and_thread_memory_limit: bool = _bool_env(
        "JUDGE0_ENABLE_PER_PROCESS_AND_THREAD_MEMORY_LIMIT",
        True,
    )
    enable_network: bool = _bool_env("JUDGE0_ENABLE_NETWORK", False)
    use_batch_api: bool = _bool_env("JUDGE0_USE_BATCH_API", True)


settings = Settings()