from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionTest(BaseModel):
    model_config = ConfigDict(extra="allow")

    test_id: str | None = None
    stdin: str | None = None
    expected_stdout: str | None = None
    input: Any = None
    expected: Any = None
    hidden: bool = False

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "ExecutionTest":
        if self.stdin is None and self.input is not None:
            if isinstance(self.input, str):
                self.stdin = self.input
            else:
                import json

                self.stdin = json.dumps(self.input, ensure_ascii=False, default=str)
        if self.expected_stdout is None and self.expected is not None:
            if isinstance(self.expected, str):
                self.expected_stdout = self.expected
            else:
                import json

                self.expected_stdout = json.dumps(self.expected, ensure_ascii=False, default=str)
        self.stdin = self.stdin or ""
        self.expected_stdout = self.expected_stdout or ""
        return self


class ComparisonConfig(BaseModel):
    mode: Literal[
        "exact_text",
        "normalized_text",
        "case_insensitive",
        "unordered_lines",
        "numeric_tolerance",
    ] = "normalized_text"
    numeric_tolerance: float = 1e-6


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str | None = None
    question_id: str | None = None
    language: str | None = None
    runtime_id: str | None = None
    code: str | None = None
    source_code: str | None = None
    tests: list[ExecutionTest] = Field(default_factory=list)
    time_limit_ms: int = 3000
    memory_limit_mb: int = 256
    execution_mode: str = "stdin_stdout"
    comparison: ComparisonConfig = Field(default_factory=ComparisonConfig)
    function_name: str | None = None

    @model_validator(mode="after")
    def normalize_source(self) -> "ExecuteRequest":
        if self.source_code is None:
            self.source_code = self.code or ""
        if self.code is None:
            self.code = self.source_code or ""
        self.execution_mode = (self.execution_mode or "stdin_stdout").strip().lower()
        return self


class RuntimeCapability(BaseModel):
    runtime_id: str
    judge0_language_id: int
    canonical_language: str
    display_name: str
    judge0_name: str
    editor_language: str
    category: str = "programming_language"
    execution_modes: list[str] = Field(default_factory=lambda: ["stdin_stdout"])


class TestExecutionResult(BaseModel):
    index: int
    test_id: str | None = None
    passed: bool
    input: Any = None
    expected: Any = None
    output: Any = None
    error: str = ""
    status: str = "completed"
    execution_time_ms: int = 0
    memory_used_mb: float = 0


class ExecuteResponse(BaseModel):
    request_id: str | None = None
    status: str
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    visible_test_results: list[TestExecutionResult] = Field(default_factory=list)
    hidden_test_results: list[TestExecutionResult] = Field(default_factory=list)
    execution_time_ms: int = 0
    memory_used_mb: float = 0
    runtime: RuntimeCapability | None = None
    retryable: bool = False
