"""用随包 ffmpeg 的 ``volumedetect`` 滤镜实测音频的峰值电平。"""

from __future__ import annotations

import re
from pathlib import Path

from lib.infra.ffmpeg import local_file_input
from lib.infra.subprocess_deadline import Spawner, SubprocessDeadlineExceeded, run_with_deadline

MEASURE_DEADLINE_FLOOR_SECONDS = 60.0
MEASURE_DEADLINE_PER_AUDIO_SECOND = 0.5

_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB")


class PeakMeasurementError(Exception):
    """ffmpeg 测不出峰值：解码失败、超时，或输出里没有 ``volumedetect`` 的汇总。"""


def measure_args(ffmpeg: str, path: Path) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-nostats",
        *local_file_input(path),
        "-vn",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]


def parse_peak(stderr: str) -> float:
    """从 ``volumedetect`` 的汇总里取峰值（dBFS）；全静音时 ffmpeg 报 ``-inf``。"""
    matches = _MAX_VOLUME_RE.findall(stderr)
    if not matches:
        raise PeakMeasurementError("ffmpeg 输出里没有峰值汇总")
    value = matches[-1]
    return float("-inf") if value == "-inf" else float(value)


async def measure_peak(ffmpeg: str, path: Path, *, duration_seconds: float, spawn: Spawner | None = None) -> float:
    """实测 ``path`` 的峰值电平（dBFS）。"""
    try:
        result = await run_with_deadline(
            measure_args(ffmpeg, path),
            deadline_seconds=MEASURE_DEADLINE_FLOOR_SECONDS + MEASURE_DEADLINE_PER_AUDIO_SECOND * duration_seconds,
            capture_stderr=True,
            spawn=spawn,
        )
    except SubprocessDeadlineExceeded:
        raise PeakMeasurementError("峰值测量超时") from None
    stderr = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        raise PeakMeasurementError(f"ffmpeg 退出码 {result.returncode}：{stderr.strip()[-500:]}")
    return parse_peak(stderr)


__all__ = ["PeakMeasurementError", "measure_args", "measure_peak", "parse_peak"]
