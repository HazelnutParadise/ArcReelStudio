"""Stability AI Stable Audio：音乐与音效，按次计价。

官方文件：https://docs.stability.ai/api-reference/stable-audio/text-to-audio.md 。``POST .../text-to-audio`` 以
``multipart/form-data`` 送出；生成较短时直接回音频，较长时回 HTTP 202 与 ``id``，再轮询 ``GET /v2beta/audio/results/{id}``
到回 200 音频为止。长度 1–380 秒。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from lib.backends.artifact_download_guard import artifact_http_client
from lib.backends.backend_runtime import should_retry_submit, submit_post
from lib.backends.music_backends.base import MusicGenerationRequest, MusicGenerationResult
from lib.backends.transport_layer import TransportLayer
from lib.infra.async_thread import run_noninterruptible_sync
from lib.infra.retry import with_retry_async

logger = logging.getLogger(__name__)

PROVIDER_STABILITY = "stability"
DEFAULT_MODEL = "stable-audio-3"
DEFAULT_BASE_URL = "https://api.stability.ai"
MAX_SECONDS = 380
POLL_INTERVAL_SECONDS = 5.0
POLL_TIMEOUT_SECONDS = 15 * 60.0


class StableAudioBackend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        transport_layer: TransportLayer | None = None,
        http_timeout: float = 300.0,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("Stability API key is required")
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._transport_layer = transport_layer
        self._http_timeout = http_timeout
        self._poll_interval = poll_interval

    @property
    def name(self) -> str:
        return PROVIDER_STABILITY

    @property
    def model(self) -> str:
        return self._model

    def _headers(self, accept: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Accept": accept}

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult:
        seconds = min(max(request.duration_seconds or 60, 1), MAX_SECONDS)
        fmt = "wav" if request.output_path.suffix.lower() == ".wav" else "mp3"
        audio = await self._submit_and_wait(request.prompt, seconds, fmt)
        await run_noninterruptible_sync(request.output_path.write_bytes, audio)
        return MusicGenerationResult(
            provider=PROVIDER_STABILITY, model=self._model, output_path=request.output_path, duration_seconds=seconds
        )

    async def _submit_and_wait(self, prompt: str, seconds: int, fmt: str) -> bytes:
        async with artifact_http_client(timeout=self._http_timeout, transport_layer=self._transport_layer) as client:
            response = await self._submit(client, prompt, seconds, fmt)
            if response.status_code == 200 and _is_audio(response):
                return response.content
            job_id = _job_id(response)
            deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                await asyncio.sleep(self._poll_interval)
                result = await client.get(
                    f"{self._base_url}/v2beta/audio/results/{job_id}", headers=self._headers("audio/*")
                )
                if result.status_code == 202:
                    continue
                result.raise_for_status()
                if _is_audio(result):
                    return result.content
                raise RuntimeError(f"音乐生成失败: Stable Audio 回应不是音频（{result.headers.get('content-type')}）")
        raise RuntimeError("音乐生成失败: Stable Audio 等待逾时")

    @with_retry_async(retry_if=should_retry_submit)
    async def _submit(self, client: Any, prompt: str, seconds: int, fmt: str) -> Any:
        logger.info("调用 Stable Audio model=%s seconds=%d chars=%d", self._model, seconds, len(prompt))
        fields = {"prompt": prompt, "duration": str(seconds), "output_format": fmt, "model": self._model}
        return await submit_post(
            lambda: client.post(
                f"{self._base_url}/v2beta/audio/stable-audio/text-to-audio",
                headers=self._headers("audio/*"),
                files={key: (None, value) for key, value in fields.items()},
            ),
            provider=PROVIDER_STABILITY,
            include_provider_reason=False,
        )


def _is_audio(response: Any) -> bool:
    return str(response.headers.get("content-type") or "").startswith("audio/")


def _job_id(response: Any) -> str:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("音乐生成失败: Stable Audio 回应无法解析") from exc
    job_id = body.get("id") if isinstance(body, dict) else None
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError("音乐生成失败: Stable Audio 没有返回任务 id")
    return job_id
