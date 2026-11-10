"""音效轨的摆放：纯函数，时间一律是整数微秒。读取投影、成片与剪映草稿共用这份摆放。

音效片段按绝对起点摆放，放完截取区间即止，可以互相重叠。超出时间线末尾的部分截断，截断处固定淡出
:data:`SFX_CUTOFF_FADE_MICROSECONDS` 免得爆音；完全落在末尾之后的片段不出声。淡入淡出加起来超过摆放后的时长时：
截断的片段先保住截断处的淡出，再缩短淡入；未截断的片段两者按比例缩短。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lib.edit_timeline.model import SfxClip
from lib.sfx.library import SfxSource

SFX_CUTOFF_FADE_MICROSECONDS = 50_000
"""超出时间线末尾被截断的音效片段，在截断处淡出这么久。"""


@dataclass(frozen=True, slots=True)
class PlacedSfx:
    """时间线上实际出声的一段音效：``volume`` 是片段音量，还没乘上音效的峰值增益。"""

    clip_id: str
    sfx_id: str
    start_us: int
    source_in_us: int
    duration_us: int
    volume: float
    fade_in_us: int
    fade_out_us: int
    truncated: bool

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us


def sfx_clip_length_us(clip: SfxClip) -> int:
    return clip.out_us - clip.in_us


def place_sfx(sfx: Sequence[SfxClip], duration_us: int) -> tuple[PlacedSfx, ...]:
    """按起点排列音效片段，截到时间线末尾；截成空的丢弃。"""
    placed: list[PlacedSfx] = []
    for clip in sorted(sfx, key=lambda item: (item.start_us, item.id)):
        natural_end = clip.start_us + sfx_clip_length_us(clip)
        end = min(natural_end, duration_us)
        if end <= clip.start_us:
            continue
        length = end - clip.start_us
        truncated = end < natural_end
        fade_in, fade_out = _fit_fades(clip, length, truncated=truncated)
        placed.append(
            PlacedSfx(
                clip_id=clip.id,
                sfx_id=clip.sfx_id,
                start_us=clip.start_us,
                source_in_us=clip.in_us,
                duration_us=length,
                volume=clip.volume,
                fade_in_us=fade_in,
                fade_out_us=fade_out,
                truncated=truncated,
            )
        )
    return tuple(placed)


def _fit_fades(clip: SfxClip, length: int, *, truncated: bool) -> tuple[int, int]:
    if truncated:
        fade_out = min(max(clip.fade_out_us, SFX_CUTOFF_FADE_MICROSECONDS), length)
        return min(clip.fade_in_us, length - fade_out), fade_out
    total = clip.fade_in_us + clip.fade_out_us
    if total <= length:
        return clip.fade_in_us, clip.fade_out_us
    return clip.fade_in_us * length // total, clip.fade_out_us * length // total


def sfx_ids(sfx: Sequence[SfxClip]) -> tuple[str, ...]:
    """音效轨引用的音效，按首次出现的顺序。"""
    return tuple(dict.fromkeys(clip.sfx_id for clip in sfx))


def sfx_sources_input(sfx: Sequence[SfxClip], sources: Mapping[str, SfxSource]) -> dict[str, object]:
    """生成依据里音效的部分：每个被引用音效的内容指纹与静态增益；取不到的记为不可用。"""
    return {
        sfx_id: source.to_input() if (source := sources.get(sfx_id)) is not None else {"unavailable": True}
        for sfx_id in sfx_ids(sfx)
    }


__all__ = [
    "SFX_CUTOFF_FADE_MICROSECONDS",
    "PlacedSfx",
    "place_sfx",
    "sfx_clip_length_us",
    "sfx_ids",
    "sfx_sources_input",
]
