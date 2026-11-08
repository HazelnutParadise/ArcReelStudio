"""音乐生成后端的通用接口：一段提示词 → 一首音乐（docs/adr/0126）。

与配音（:mod:`lib.backends.audio_backends`）同属音频媒体类型，接口分开：配音吃「文字＋音色」，音乐吃提示词与长度。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MusicGenerationRequest:
    prompt: str
    output_path: Path
    #: 想要的长度（秒）；供应商不支援指定长度时写进提示词
    duration_seconds: int | None = None
    #: 只要器乐、不要人声
    instrumental: bool = True


@dataclass(frozen=True)
class MusicGenerationResult:
    provider: str
    model: str
    output_path: Path
    #: 供应商回报的实际长度；没回报时为 None，由入库时实测
    duration_seconds: float | None = None


class MusicBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult: ...


def describe_length(prompt: str, duration_seconds: int | None) -> str:
    """供应商不接受长度参数时，把想要的长度写进提示词。"""
    if not duration_seconds:
        return prompt
    return f"{prompt}\n\nLength: about {duration_seconds} seconds."
