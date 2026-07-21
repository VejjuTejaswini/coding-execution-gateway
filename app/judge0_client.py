from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .config import Settings


class Judge0Client:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        if self.settings.judge0_auth_header and self.settings.judge0_auth_token:
            return {self.settings.judge0_auth_header: self.settings.judge0_auth_token}
        return {}

    def _submission_payload(
        self,
        *,
        language_id: int,
        source_code: str,
        stdin: str,
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> dict[str, Any]:
        cpu_seconds = max(0.1, time_limit_ms / 1000.0)
        return {
            "language_id": language_id,
            "source_code": source_code,
            "stdin": stdin,
            "cpu_time_limit": cpu_seconds,
            "wall_time_limit": max(cpu_seconds + 2.0, cpu_seconds * 2.0),
            "memory_limit": max(16, memory_limit_mb) * 1024,
            "max_file_size": 2048,
            "enable_network": self.settings.enable_network,
        }

    async def execute_many(
        self,
        *,
        language_id: int,
        source_code: str,
        stdins: list[str],
        source_codes: list[str] | None = None,
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> list[dict[str, Any]]:
        if not stdins:
            return []

        effective_sources = source_codes or [source_code for _ in stdins]
        if len(effective_sources) != len(stdins):
            raise ValueError("source_codes and stdins must have the same length")

        submissions = [
            self._submission_payload(
                language_id=language_id,
                source_code=current_source,
                stdin=stdin,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb,
            )
            for current_source, stdin in zip(effective_sources, stdins)
        ]

        if self.settings.use_batch_api and len(submissions) > 1:
            try:
                return await self._execute_batch(submissions)
            except (httpx.HTTPError, ValueError, KeyError):
                pass

        results: list[dict[str, Any]] = []
        for submission in submissions:
            results.append(await self._execute_one(submission))
        return results

    async def _execute_one(self, submission: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.judge0_url}/submissions",
                params={"base64_encoded": "false", "wait": "false"},
                headers=self._headers(),
                json=submission,
            )
            response.raise_for_status()
            token = str(response.json()["token"])
            return await self._poll_one(client, token)

    async def _poll_one(self, client: httpx.AsyncClient, token: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.max_poll_sec
        fields = "stdout,stderr,compile_output,message,time,wall_time,memory,status,exit_code,exit_signal"
        while True:
            response = await client.get(
                f"{self.settings.judge0_url}/submissions/{token}",
                params={"base64_encoded": "false", "fields": fields},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            status_id = int((payload.get("status") or {}).get("id") or 0)
            if status_id not in {1, 2}:
                payload["token"] = token
                return payload
            if time.monotonic() >= deadline:
                return {
                    "token": token,
                    "stdout": None,
                    "stderr": "Judge0 result polling timed out.",
                    "compile_output": None,
                    "message": "Judge0 result polling timed out.",
                    "time": None,
                    "memory": None,
                    "status": {"id": 0, "description": "Infrastructure Timeout"},
                }
            await asyncio.sleep(self.settings.poll_interval_sec)

    async def _execute_batch(self, submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.judge0_url}/submissions/batch",
                params={"base64_encoded": "false"},
                headers=self._headers(),
                json={"submissions": submissions},
            )
            response.raise_for_status()
            token_items = response.json()
            tokens = [str(item["token"]) for item in token_items]

            deadline = time.monotonic() + self.settings.max_poll_sec
            fields = "stdout,stderr,compile_output,message,time,wall_time,memory,status,exit_code,exit_signal"
            while True:
                result_response = await client.get(
                    f"{self.settings.judge0_url}/submissions/batch",
                    params={
                        "tokens": ",".join(tokens),
                        "base64_encoded": "false",
                        "fields": fields,
                    },
                    headers=self._headers(),
                )
                result_response.raise_for_status()
                payload = result_response.json()
                results = list(payload.get("submissions") or [])
                if len(results) == len(tokens) and all(
                    int((item.get("status") or {}).get("id") or 0) not in {1, 2}
                    for item in results
                ):
                    for token, item in zip(tokens, results):
                        item["token"] = token
                    return results

                if time.monotonic() >= deadline:
                    return [
                        {
                            "token": token,
                            "stdout": None,
                            "stderr": "Judge0 batch result polling timed out.",
                            "compile_output": None,
                            "message": "Judge0 batch result polling timed out.",
                            "time": None,
                            "memory": None,
                            "status": {"id": 0, "description": "Infrastructure Timeout"},
                        }
                        for token in tokens
                    ]
                await asyncio.sleep(self.settings.poll_interval_sec)
