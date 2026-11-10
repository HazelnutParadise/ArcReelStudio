"""ElevenLabs Sound Effects：同步生成，回应即音频（MP3），按分钟计价。

官方文件：https://elevenlabs.io/docs/overview/capabilities/sound-effects 。``POST /v1/sound-generation``，
长度 0.5 到 30 秒；免费方案只能非商用，付费方案可商用。与音乐共用「提示词 + 长度 → 音频」的接口（docs/adr/0127）。
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
DEFAULT_MODEL = "eleven_text_to_sound_v3"
DEFAULT_BASE_URL = "https://api.elevenlabs.io"
MIN_SECONDS = 0.5
MAX_SECONDS = 30.0


class ElevenLabsSoundEffectsBackend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        transport_layer: TransportLayer | None = None,
        http_timeout: float = 180.0,
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
        seconds = None
        if request.duration_seconds:
            seconds = min(max(float(request.duration_seconds), MIN_SECONDS), MAX_SECONDS)
        audio = await self._generate(request, seconds)
        await run_noninterruptible_sync(request.output_path.write_bytes, audio)
        return MusicGenerationResult(
            provider=PROVIDER_ELEVENLABS, model=self._model, output_path=request.output_path, duration_seconds=seconds
        )

    @with_retry_async(retry_if=should_retry_submit)
    async def _generate(self, request: MusicGenerationRequest, seconds: float | None) -> bytes:
        payload: dict[str, object] = {"text": request.prompt, "model_id": self._model}
        if seconds is not None:
            # 省略时由模型按提示词自行决定长度
            payload["duration_seconds"] = seconds
        logger.info(
            "调用 ElevenLabs Sound Effects model=%s seconds=%s chars=%d", self._model, seconds, len(request.prompt)
        )
        async with artifact_http_client(timeout=self._http_timeout, transport_layer=self._transport_layer) as client:
            response = await submit_post(
                lambda: client.post(
                    f"{self._base_url}/v1/sound-generation",
                    json=payload,
                    headers={"xi-api-key": self._api_key, "Accept": "audio/mpeg"},
                ),
                provider=PROVIDER_ELEVENLABS,
                include_provider_reason=False,
            )
        return response.content
