"""成片画面编码器的选择：GPU 自检结论由注入的 run_self_check 给出，不启动子进程。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.infra.video_encoder import (
    CPU_ENCODING,
    NVENC_ENCODER,
    GpuEncoderStatus,
    inspect_gpu_encoder,
    select_video_encoding,
)


def _gpu_ffmpeg(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"")
    return executable


def _completed(returncode: int, stderr: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=b"", stderr=stderr)


def _never_called(_exe: Path) -> subprocess.CompletedProcess[bytes]:
    raise AssertionError("没有 GPU ffmpeg 时不应自检")


def test_unavailable_without_the_gpu_ffmpeg(tmp_path: Path):
    status = inspect_gpu_encoder(tmp_path / "missing", run_self_check=_never_called)

    assert not status.available
    assert status.encoder is None
    assert "未找到支持 GPU 编码的 ffmpeg" in (status.unavailable_reason or "")


def test_available_when_nvenc_encodes_the_probe_frames(tmp_path: Path):
    executable = _gpu_ffmpeg(tmp_path)

    status = inspect_gpu_encoder(executable, run_self_check=lambda _exe: _completed(0))

    assert status.available
    assert status.executable == executable
    assert status.encoder == NVENC_ENCODER


def test_unavailable_when_the_container_has_no_gpu(tmp_path: Path):
    status = inspect_gpu_encoder(
        _gpu_ffmpeg(tmp_path),
        run_self_check=lambda _exe: _completed(1, b"Cannot load libcuda.so.1\n"),
    )

    assert not status.available
    assert status.unavailable_reason == "NVENC 编码自检失败（退出码 1）：Cannot load libcuda.so.1"


def test_unavailable_when_the_self_check_cannot_run(tmp_path: Path):
    def _timeout(exe: Path) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd=str(exe), timeout=30)

    status = inspect_gpu_encoder(_gpu_ffmpeg(tmp_path), run_self_check=_timeout)

    assert not status.available
    assert (status.unavailable_reason or "").startswith("GPU 编码自检无法运行：")


def test_uses_nvenc_with_the_gpu_ffmpeg_when_enabled_and_available(tmp_path: Path):
    executable = _gpu_ffmpeg(tmp_path)

    encoding = select_video_encoding(gpu_enabled=True, status=GpuEncoderStatus(executable, None))

    assert encoding.uses_gpu
    assert encoding.executable == str(executable)
    assert encoding.codec_args[:2] == ("-c:v", NVENC_ENCODER)


def test_uses_cpu_when_the_setting_turns_gpu_encoding_off(tmp_path: Path):
    encoding = select_video_encoding(gpu_enabled=False, status=GpuEncoderStatus(_gpu_ffmpeg(tmp_path), None))

    assert encoding == CPU_ENCODING
    assert not encoding.uses_gpu


def test_uses_cpu_when_the_gpu_is_unavailable():
    encoding = select_video_encoding(gpu_enabled=True, status=GpuEncoderStatus(None, "未找到"))

    assert encoding == CPU_ENCODING
    assert encoding.codec_args == ("-c:v", "libx264", "-preset", "veryfast", "-crf", "20")
