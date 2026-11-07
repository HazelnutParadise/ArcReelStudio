"""成片画面编码器的选择：检测到可用的 NVIDIA GPU 时用 NVENC，否则用随包 ffmpeg 的 libx264。

随包 ffmpeg（见 :mod:`lib.infra.ffmpeg`）没有编入 NVENC。Docker 镜像在 :data:`GPU_FFMPEG_PATH` 另放一份
支持 NVENC 的 ffmpeg，只用于成片的画面编码；混音、封装与媒体探测仍走随包 ffmpeg。GPU 是否可用在进程内
自检一次：用这份 ffmpeg 以 NVENC 编码几帧，成功即可用。容器没拿到 GPU（宿主机没有 NVIDIA GPU，或 Compose
没有加载 GPU 配置）时自检失败，成片照常用 CPU 编码。系统设置 :data:`GPU_ENCODING_SETTING` 可以关掉 GPU 编码。
"""

from __future__ import annotations

import functools
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

GPU_FFMPEG_PATH = Path("/opt/arcreel/ffmpeg-gpu/ffmpeg")
"""支持 NVENC 的 ffmpeg 在 Docker 镜像中的位置；与 Dockerfile 的 COPY 目标一致。"""

GPU_ENCODING_SETTING = "gpu_encoding_enabled"
"""系统设置：``"false"`` 关闭 GPU 编码，缺省为开。"""

NVENC_ENCODER = "h264_nvenc"

_SELF_CHECK_TIMEOUT_SECONDS = 30.0
_REASON_TAIL = 300

CPU_CODEC_ARGS: tuple[str, ...] = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "20")
NVENC_CODEC_ARGS: tuple[str, ...] = (
    "-c:v",
    NVENC_ENCODER,
    "-preset",
    "p5",
    "-tune",
    "hq",
    "-rc",
    "vbr",
    "-cq",
    "21",
    "-b:v",
    "0",
    "-profile:v",
    "high",
)

SelfCheckRunner = Callable[[Path], "subprocess.CompletedProcess[bytes]"]


@dataclass(frozen=True, slots=True)
class VideoEncoding:
    """成片画面编码方式。``executable`` 为 None 时用调用方传入的随包 ffmpeg。"""

    encoder: str
    codec_args: tuple[str, ...]
    executable: str | None = None

    @property
    def uses_gpu(self) -> bool:
        return self.executable is not None


CPU_ENCODING = VideoEncoding(encoder="libx264", codec_args=CPU_CODEC_ARGS)


@dataclass(frozen=True, slots=True)
class GpuEncoderStatus:
    """GPU 编码的自检结论。``unavailable_reason`` 为 None 即可用。"""

    executable: Path | None
    unavailable_reason: str | None

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def encoder(self) -> str | None:
        return NVENC_ENCODER if self.available else None


def _run_self_check(executable: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            str(executable),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=256x144:r=25:d=0.2",
            "-c:v",
            NVENC_ENCODER,
            "-f",
            "null",
            "-",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=_SELF_CHECK_TIMEOUT_SECONDS,
        check=False,
    )


def inspect_gpu_encoder(executable: Path, *, run_self_check: SelfCheckRunner = _run_self_check) -> GpuEncoderStatus:
    """检查 ``executable`` 能否用 NVENC 编码：文件不存在即不可用，存在则试编几帧。"""
    if not executable.is_file():
        return GpuEncoderStatus(None, f"未找到支持 GPU 编码的 ffmpeg：{executable}")
    try:
        result = run_self_check(executable)
    except (OSError, subprocess.SubprocessError) as exc:
        return GpuEncoderStatus(executable, f"GPU 编码自检无法运行：{exc}")
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()[-_REASON_TAIL:]
        return GpuEncoderStatus(executable, f"NVENC 编码自检失败（退出码 {result.returncode}）：{stderr}")
    return GpuEncoderStatus(executable, None)


@functools.cache
def gpu_encoder_status() -> GpuEncoderStatus:
    """GPU 编码的自检结论；首次调用时自检一次，结论在进程内固定。会启动子进程，异步代码须放进线程调用。"""
    return inspect_gpu_encoder(GPU_FFMPEG_PATH)


def log_gpu_encoder_status() -> GpuEncoderStatus:
    """执行自检并记录结论，供服务启动时调用。"""
    status = gpu_encoder_status()
    if status.available:
        logger.info("GPU 编码可用：成片画面用 %s 编码（%s）", NVENC_ENCODER, status.executable)
    else:
        logger.info("GPU 编码不可用，成片画面用 CPU 编码：%s", status.unavailable_reason)
    return status


def select_video_encoding(*, gpu_enabled: bool, status: GpuEncoderStatus | None = None) -> VideoEncoding:
    """按系统设置与自检结论选编码方式：设置开启且 GPU 可用时用 NVENC，否则用 CPU。

    ``status`` 缺省时取进程内的自检结论（首次调用会启动子进程）。
    """
    if not gpu_enabled:
        return CPU_ENCODING
    resolved = status if status is not None else gpu_encoder_status()
    if not resolved.available or resolved.executable is None:
        return CPU_ENCODING
    return VideoEncoding(encoder=NVENC_ENCODER, codec_args=NVENC_CODEC_ARGS, executable=str(resolved.executable))


def reset_for_tests() -> None:
    """test helper —— 清除进程级自检缓存。"""
    gpu_encoder_status.cache_clear()
