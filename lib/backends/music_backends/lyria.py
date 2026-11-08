"""Google Lyria（Gemini API 的 Interactions）：同步生成整首音乐，回应内联 base64 音频（预设 MP3）。

官方文件：https://aistudio.google.com/docs/music-generation 。Lyria 3.5 没有长度参数，想要的长度写进提示词。
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from lib.backends.gemini_shared import gemini_http_options, resolve_gemini_api_key
from lib.backends.music_backends.base import MusicGenerationRequest, MusicGenerationResult, describe_length
from lib.backends.providers import PROVIDER_GEMINI
from lib.backends.transport_layer import TransportLayer
from lib.config.url_utils import normalize_base_url
from lib.infra.async_thread import run_noninterruptible_sync

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "lyria-3.5"


class LyriaMusicBackend:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        transport_layer: TransportLayer | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model or DEFAULT_MODEL
        if client is not None:
            self._client = client
        else:
            from google import genai

            self._client = genai.Client(
                api_key=resolve_gemini_api_key(api_key),
                http_options=gemini_http_options(normalize_base_url(base_url), transport_layer),
            )

    @property
    def name(self) -> str:
        return PROVIDER_GEMINI

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult:
        prompt = describe_length(request.prompt, request.duration_seconds)
        if request.instrumental:
            prompt = f"{prompt}\nInstrumental only, no vocals."
        logger.info("调用 Lyria 音乐生成 model=%s chars=%d", self._model, len(prompt))
        interaction = await self._client.aio.interactions.create(model=self._model, input=prompt)
        audio = getattr(interaction, "output_audio", None)
        data = getattr(audio, "data", None)
        if not data:
            raise RuntimeError("音乐生成失败: Lyria 没有返回音频")
        # 供应商已计费返回：解码与写盘不可被取消打断
        await run_noninterruptible_sync(request.output_path.write_bytes, base64.b64decode(data))
        return MusicGenerationResult(provider=PROVIDER_GEMINI, model=self._model, output_path=request.output_path)
