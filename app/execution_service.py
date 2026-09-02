from __future__ import annotations

from typing import Any

import httpx

from .comparator import compare_output
from .config import Settings
from .judge0_client import Judge0Client
from .language_registry import LanguageRegistry
from .models import ExecuteRequest, ExecuteResponse, TestExecutionResult


_STATUS_MAP = {
    3: "executed",
    4: "wrong_answer",
    5: "time_limit_exceeded",
    6: "compilation_error",
    7: "runtime_error",
    8: "runtime_error",
    9: "runtime_error",
    10: "runtime_error",
    11: "runtime_error",
    12: "runtime_error",
    13: "infrastructure_error",
    14: "infrastructure_error",
}

_JVM_LANGUAGES = frozenset({"java", "kotlin", "scala"})
_DOTNET_LANGUAGES = frozenset({"csharp"})
_DEFAULT_JVM_MIN_MEMORY_MB = 500
_DEFAULT_DOTNET_MIN_MEMORY_MB = 256
_JVM_INFRASTRUCTURE_MARKERS = (
    "error occurred during initialization of vm",
    "could not reserve enough space",
    "could not create the java virtual machine",
    "native memory allocation",
    "os::commit_memory",
)


class ExecutionService:
    def __init__(self, settings: Settings, registry: LanguageRegistry):
        self.settings = settings
        self.registry = registry
        self.judge0 = Judge0Client(settings)

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    def _resolve_memory_limit_mb(
        self,
        *,
        canonical_language: str,
        requested_memory_mb: int | None,
    ) -> int:
        requested = max(
            16,
            int(requested_memory_mb or self.settings.default_memory_limit_mb),
        )

        if canonical_language in _JVM_LANGUAGES:
            jvm_min_memory_mb = int(
                getattr(
                    self.settings,
                    "jvm_min_memory_limit_mb",
                    _DEFAULT_JVM_MIN_MEMORY_MB,
                )
            )
            return max(requested, jvm_min_memory_mb)

        if canonical_language in _DOTNET_LANGUAGES:
            dotnet_min_memory_mb = int(
                getattr(
                    self.settings,
                    "dotnet_min_memory_limit_mb",
                    _DEFAULT_DOTNET_MIN_MEMORY_MB,
                )
            )
            return max(requested, dotnet_min_memory_mb)

        return requested

    @staticmethod
    def _is_runtime_infrastructure_failure(
        *,
        canonical_language: str,
        stderr: str,
        compile_output: str,
    ) -> bool:
        if canonical_language not in _JVM_LANGUAGES:
            return False

        text = f"{stderr} {compile_output}".lower()
        return any(marker in text for marker in _JVM_INFRASTRUCTURE_MARKERS)

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        if request.execution_mode != "stdin_stdout":
            return ExecuteResponse(
                request_id=request.request_id,
                status="unsupported_execution_mode",
                stderr="This gateway supports universal stdin_stdout execution only.",
            )

        source_code = request.source_code or ""
        if not source_code.strip():
            return ExecuteResponse(
                request_id=request.request_id,
                status="invalid_request",
                stderr="source_code is required.",
            )
        if len(source_code) > self.settings.max_code_chars:
            return ExecuteResponse(
                request_id=request.request_id,
                status="invalid_request",
                stderr=f"Source code exceeds {self.settings.max_code_chars} characters.",
            )
        if not request.tests:
            return ExecuteResponse(
                request_id=request.request_id,
                status="invalid_request",
                stderr="At least one test is required.",
            )
        if len(request.tests) > self.settings.max_tests:
            return ExecuteResponse(
                request_id=request.request_id,
                status="invalid_request",
                stderr=f"A maximum of {self.settings.max_tests} tests is allowed.",
            )

        runtime = await self.registry.resolve(runtime_id=request.runtime_id, language=request.language)
        if runtime is None:
            return ExecuteResponse(
                request_id=request.request_id,
                status="unsupported_language",
                stderr="The requested language/runtime is not available in Judge0.",
            )

        try:
            test_stdins = [test.stdin or "" for test in request.tests]
            source_codes: list[str] | None = None
            if runtime.canonical_language == "sql":
                # Judge0's SQL runtime executes a SQL script rather than reading
                # a conventional stdin stream. Treat each test's stdin field as
                # private SQLite setup SQL and append the candidate query.
                source_codes = [
                    setup_sql.rstrip() + "\n" + source_code.lstrip()
                    for setup_sql in test_stdins
                ]
                test_stdins = ["" for _ in request.tests]

            effective_memory_limit_mb = self._resolve_memory_limit_mb(
                canonical_language=runtime.canonical_language,
                requested_memory_mb=request.memory_limit_mb,
            )

            raw_results = await self.judge0.execute_many(
                language_id=runtime.judge0_language_id,
                source_code=source_code,
                source_codes=source_codes,
                stdins=test_stdins,
                time_limit_ms=max(100, request.time_limit_ms or self.settings.default_time_limit_ms),
                memory_limit_mb=effective_memory_limit_mb,
                force_sequential=runtime.canonical_language in _JVM_LANGUAGES,
            )
        except httpx.TimeoutException as exc:
            return ExecuteResponse(
                request_id=request.request_id,
                status="infrastructure_error",
                stderr=f"Judge0 request timed out: {exc}",
                runtime=runtime,
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ExecuteResponse(
                request_id=request.request_id,
                status="infrastructure_error",
                stderr=f"Judge0 request failed: {exc}",
                runtime=runtime,
                retryable=True,
            )
        except Exception as exc:
            return ExecuteResponse(
                request_id=request.request_id,
                status="infrastructure_error",
                stderr=f"Unexpected execution gateway error: {type(exc).__name__}: {exc}",
                runtime=runtime,
                retryable=True,
            )

        visible: list[TestExecutionResult] = []
        hidden: list[TestExecutionResult] = []
        aggregate_stderr: list[str] = []
        aggregate_compile: list[str] = []
        total_time_ms = 0
        max_memory_kb = 0.0

        for index, (test, result) in enumerate(zip(request.tests, raw_results)):
            status_obj = result.get("status") or {}
            judge0_status_id = int(status_obj.get("id") or 0)
            normalized_status = _STATUS_MAP.get(judge0_status_id, "infrastructure_error")
            stdout = self._text(result.get("stdout"))[: self.settings.max_output_chars]
            stderr = self._text(result.get("stderr") or result.get("message"))[: self.settings.max_output_chars]
            compile_output = self._text(result.get("compile_output"))[: self.settings.max_output_chars]
            if self._is_runtime_infrastructure_failure(
                canonical_language=runtime.canonical_language,
                stderr=stderr,
                compile_output=compile_output,
            ):
                normalized_status = "infrastructure_error"

            execution_time_ms = int(float(result.get("time") or 0) * 1000)
            memory_kb = float(result.get("memory") or 0)

            total_time_ms += execution_time_ms
            max_memory_kb = max(max_memory_kb, memory_kb)
            if stderr:
                aggregate_stderr.append(stderr)
            if compile_output:
                aggregate_compile.append(compile_output)

            passed = (
                judge0_status_id == 3
                and compare_output(stdout, test.expected_stdout or "", request.comparison)
            )
            if judge0_status_id == 3 and not passed:
                normalized_status = "wrong_answer"

            error = ""
            if not passed:
                error = compile_output or stderr or normalized_status.replace("_", " ").title()

            item = TestExecutionResult(
                index=index,
                test_id=test.test_id,
                passed=passed,
                input=test.stdin,
                expected=test.expected_stdout,
                output=stdout,
                error=error,
                status=normalized_status,
                execution_time_ms=execution_time_ms,
                memory_used_mb=round(memory_kb / 1024.0, 3),
            )
            (hidden if test.hidden else visible).append(item)

        all_results = visible + hidden
        if all_results and all(item.passed for item in all_results):
            overall_status = "passed"
        elif any(item.status == "infrastructure_error" for item in all_results):
            overall_status = "infrastructure_error"
        elif any(item.status == "compilation_error" for item in all_results):
            overall_status = "compilation_error"
        elif any(item.status == "time_limit_exceeded" for item in all_results):
            overall_status = "time_limit_exceeded"
        elif any(item.status == "runtime_error" for item in all_results):
            overall_status = "runtime_error"
        else:
            overall_status = "failed"

        return ExecuteResponse(
            request_id=request.request_id,
            status=overall_status,
            stdout="",
            stderr="\n".join(dict.fromkeys(filter(None, aggregate_stderr))),
            compile_output="\n".join(dict.fromkeys(filter(None, aggregate_compile))),
            visible_test_results=visible,
            hidden_test_results=hidden,
            execution_time_ms=total_time_ms,
            memory_used_mb=round(max_memory_kb / 1024.0, 3),
            runtime=runtime,
            retryable=overall_status == "infrastructure_error",
        )