from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .models import RuntimeCapability


_INTERNAL_NAMES = {"plain text", "executable", "multi-file program"}


_EDITOR_MAP = {
    "assembly": "asm",
    "bash": "shell",
    "basic": "plaintext",
    "c": "c",
    "c++": "cpp",
    "c#": "csharp",
    "clojure": "clojure",
    "cobol": "cobol",
    "common lisp": "lisp",
    "dart": "dart",
    "d": "d",
    "elixir": "elixir",
    "erlang": "erlang",
    "f#": "fsharp",
    "fortran": "fortran",
    "go": "go",
    "groovy": "groovy",
    "haskell": "haskell",
    "java": "java",
    "javafx": "java",
    "javascript": "javascript",
    "kotlin": "kotlin",
    "lua": "lua",
    "objective-c": "objective-c",
    "ocaml": "ocaml",
    "octave": "matlab",
    "pascal": "pascal",
    "perl": "perl",
    "php": "php",
    "prolog": "prolog",
    "python": "python",
    "r": "r",
    "ruby": "ruby",
    "rust": "rust",
    "scala": "scala",
    "sql": "sql",
    "swift": "swift",
    "typescript": "typescript",
    "visual basic.net": "vb",
}


_ALIASES = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "ts": "typescript",
    "cpp": "c++",
    "cplusplus": "c++",
    "csharp": "c#",
    "cs": "c#",
    "golang": "go",
    "visualbasic": "visual basic.net",
    "vbnet": "visual basic.net",
}


def _base_name(judge0_name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", judge0_name or "").strip()


def _canonical(base_name: str) -> str:
    normalized = base_name.strip().lower()
    normalized = _ALIASES.get(normalized, normalized)
    return {
        "c++": "cpp",
        "c#": "csharp",
        "visual basic.net": "visual_basic",
        "objective-c": "objective_c",
        "common lisp": "common_lisp",
    }.get(normalized, normalized.replace(" ", "_"))


def _version_tuple(name: str) -> tuple[int, ...]:
    match = re.search(r"\((?:[^0-9]*)([0-9]+(?:\.[0-9]+)*)", name or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


@dataclass
class LanguageRegistry:
    settings: Settings

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()
        self._loaded_at = 0.0
        self._by_runtime_id: dict[str, RuntimeCapability] = {}
        self._defaults_by_canonical: dict[str, RuntimeCapability] = {}

    def _headers(self) -> dict[str, str]:
        if self.settings.judge0_auth_header and self.settings.judge0_auth_token:
            return {self.settings.judge0_auth_header: self.settings.judge0_auth_token}
        return {}

    async def refresh(self, *, force: bool = False) -> list[RuntimeCapability]:
        now = time.monotonic()
        if not force and self._by_runtime_id and now - self._loaded_at < self.settings.language_cache_ttl_sec:
            return list(self._by_runtime_id.values())

        async with self._lock:
            now = time.monotonic()
            if not force and self._by_runtime_id and now - self._loaded_at < self.settings.language_cache_ttl_sec:
                return list(self._by_runtime_id.values())

            async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
                response = await client.get(
                    f"{self.settings.judge0_url}/languages",
                    headers=self._headers(),
                )
                response.raise_for_status()
                raw_languages: list[dict[str, Any]] = response.json()

            by_runtime: dict[str, RuntimeCapability] = {}
            grouped: dict[str, list[RuntimeCapability]] = {}

            for item in raw_languages:
                language_id = int(item["id"])
                judge0_name = str(item["name"])
                base = _base_name(judge0_name)
                if base.strip().lower() in _INTERNAL_NAMES:
                    continue

                canonical = _canonical(base)
                category = "database_language" if canonical == "sql" else "programming_language"
                runtime = RuntimeCapability(
                    runtime_id=f"judge0-{language_id}",
                    judge0_language_id=language_id,
                    canonical_language=canonical,
                    display_name=judge0_name,
                    judge0_name=judge0_name,
                    editor_language=_EDITOR_MAP.get(base.strip().lower(), "plaintext"),
                    category=category,
                    execution_modes=["stdin_stdout"],
                )
                by_runtime[runtime.runtime_id] = runtime
                grouped.setdefault(canonical, []).append(runtime)

            defaults: dict[str, RuntimeCapability] = {}
            for canonical, runtimes in grouped.items():
                defaults[canonical] = max(
                    runtimes,
                    key=lambda runtime: (
                        _version_tuple(runtime.judge0_name),
                        runtime.judge0_language_id,
                    ),
                )

            self._by_runtime_id = by_runtime
            self._defaults_by_canonical = defaults
            self._loaded_at = time.monotonic()
            return list(by_runtime.values())

    async def capabilities(self) -> list[RuntimeCapability]:
        values = await self.refresh()
        return sorted(values, key=lambda item: (item.canonical_language, item.display_name))

    async def resolve(self, *, runtime_id: str | None, language: str | None) -> RuntimeCapability | None:
        await self.refresh()
        if runtime_id:
            return self._by_runtime_id.get(runtime_id.strip().lower()) or self._by_runtime_id.get(runtime_id.strip())

        canonical = (language or "").strip().lower()
        canonical = _ALIASES.get(canonical, canonical)
        canonical = {
            "c++": "cpp",
            "c#": "csharp",
            "visual basic.net": "visual_basic",
            "objective-c": "objective_c",
        }.get(canonical, canonical.replace(" ", "_"))
        return self._defaults_by_canonical.get(canonical)
