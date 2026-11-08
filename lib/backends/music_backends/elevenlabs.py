"""ElevenLabs Music：同步生成，回应即音频（MP3），按分钟计价。

官方文件：https://elevenlabs.io/docs/overview/capabilities/music 。``POST /v1/music``，长度以毫秒给（3 秒到 10 分钟）。
注意：ElevenLabs 的音乐条款禁止把音乐模型提供给第三方平台使用（Model Resale）；自己部署、自己的金钥给自己团队用不在此列，
对外开放前要先取得 ElevenLabs 的授权（设定页与文件都有说明）。
"""

from __future__ import annotations

import logging

from lib.backends.artifact_download_guard import artifact_http_client
from lib.backends.backend_runtime import should_retry_submit, submit_post
from lib.backends.music_backends.base import MusicGenerationRequest, MusicGenerationResult
from lib.backends.transport_layer import TransportLayer
from lib.infra.async_thread import run_noninterruptible_sync
from lib.infra.retry import with_retry_async

logger = logging.getLogger(__name__)

PROVIDER_ELEVENLABS = "elevenlabs"
DEFAULT_MODEL = "music_v2_5"
DEFAULT_BASE_URL = "https://api.elevenlabs.io"
MIN_SECONDS = 3
MAX_SECONDS = 600


class ElevenLabsMusicBackend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        transport_layer: TransportLayer | None = None,
        http_timeout: float = 600.0,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._transport_layer = transport_layer
        self._http_timeout = http_timeout

    @property
    def name(self) -> str:
        return PROVIDER_ELEVENLABS

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult:
        seconds = min(max(request.duration_seconds or 60, MIN_SECONDS), MAX_SECONDS)
        audio = await self._compose(request, seconds)
        await run_noninterruptible_sync(request.output_path.write_bytes, audio)
        return MusicGenerationResult(
            provider=PROVIDER_ELEVENLABS, model=self._model, output_path=request.output_path, duration_seconds=seconds
        )

    @with_retry_async(retry_if=should_retry_submit)
    async def _compose(self, request: MusicGenerationRequest, seconds: int) -> bytes:
        payload = {
            "prompt": request.prompt,
            "music_length_ms": seconds * 1000,
            "model_id": self._model,
            "force_instrumental": request.instrumental,
        }
        logger.info("调用 ElevenLabs Music model=%s seconds=%d chars=%d", self._model, seconds, len(request.prompt))
        async with artifact_http_client(timeout=self._http_timeout, transport_layer=self._transport_layer) as client:
            response = await submit_post(
                lambda: client.post(
                    f"{self._base_url}/v1/music",
                    json=payload,
                    headers={"xi-api-key": self._api_key, "Accept": "audio/mpeg"},
                ),
                provider=PROVIDER_ELEVENLABS,
                include_provider_reason=False,
            )
        return response.content
