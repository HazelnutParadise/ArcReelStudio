"""把素材库里 BGM 库不收的音频格式（OGG、FLAC）转成 MP3。

公有领域的音乐多半以 OGG 存在维基共享资源；BGM 库与音效库只收 MP3、WAV、M4A，导入前用随包 ffmpeg 转一次。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from lib.infra.ffmpeg import FfmpegUnavailableError, ffmpeg_executable, local_file_input
from lib.infra.subprocess_deadline import SubprocessDeadlineExceeded, run_with_deadline
from lib.stock.model import StockError

#: 库里直接收的格式；其余的先转成 MP3
STORABLE_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a")
#: 来源会给、且 ffmpeg 能解的格式
TRANSCODABLE_AUDIO_EXTENSIONS = (".ogg", ".oga", ".flac")

_TRANSCODE_DEADLINE_SECONDS = 300.0


async def to_storable_audio(content: bytes, extension: str) -> tuple[bytes, str]:
    """返回 ``(字节, 扩展名)``：库里直接收的格式原样返回，OGG / FLAC 转成 192 kbps 的 MP3。"""
    if extension in STORABLE_AUDIO_EXTENSIONS:
        return content, extension
    if extension not in TRANSCODABLE_AUDIO_EXTENSIONS:
        raise StockError("stock_file_unsupported", f"素材的音频格式不受支持：{extension}")
    try:
        ffmpeg = await asyncio.to_thread(ffmpeg_executable)
    except FfmpegUnavailableError as exc:
        raise StockError("stock_file_unsupported", f"随包 ffmpeg 不可用，无法转换音频格式：{exc}") from exc
    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="arcreel-stock-"))
    try:
        source, target = workdir / f"in{extension}", workdir / "out.mp3"
        await asyncio.to_thread(source.write_bytes, content)
        args = [ffmpeg, "-nostdin", "-y", *local_file_input(source), "-vn", "-b:a", "192k", str(target)]
        try:
            result = await run_with_deadline(args, deadline_seconds=_TRANSCODE_DEADLINE_SECONDS, capture_stderr=True)
        except SubprocessDeadlineExceeded:
            raise StockError("stock_file_unsupported", "素材的音频格式转换超时") from None
        if result.returncode != 0 or not await asyncio.to_thread(target.is_file):
            detail = result.stderr.decode(errors="replace").strip()[-300:]
            raise StockError("stock_file_unsupported", f"素材的音频无法转换：{detail}")
        return await asyncio.to_thread(target.read_bytes), ".mp3"
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)  # hard-delete: temp -- 转码用的临时目录
