"""素材库音频转码：库里不收的格式用随包 ffmpeg 转成 MP3，直接收的格式原样返回。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.infra.ffmpeg import ffmpeg_executable
from lib.infra.media_probe import probe_media
from lib.stock.model import StockError
from lib.stock.transcode import to_storable_audio
from tests.factories import wav_bytes


def _flac_bytes(tmp_path: Path) -> bytes:
    source, target = tmp_path / "tone.wav", tmp_path / "tone.flac"
    source.write_bytes(wav_bytes(1.0, tone_hz=440))
    subprocess.run(
        [ffmpeg_executable(), "-nostdin", "-y", "-i", str(source), str(target)], check=True, capture_output=True
    )
    return target.read_bytes()


async def test_flac_becomes_an_mp3_of_the_same_length(tmp_path: Path) -> None:
    content, extension = await to_storable_audio(_flac_bytes(tmp_path), ".flac")

    assert extension == ".mp3"
    out = tmp_path / "out.mp3"
    out.write_bytes(content)
    audio = (await probe_media(out)).first_stream("audio")
    assert audio is not None
    assert audio.duration_seconds == pytest.approx(1.0, abs=0.1)


async def test_formats_the_library_accepts_are_returned_untouched() -> None:
    wav = wav_bytes(0.2, tone_hz=440)

    assert await to_storable_audio(wav, ".wav") == (wav, ".wav")


@pytest.mark.parametrize(("content", "extension"), [(b"not audio", ".ogg"), (b"MThd", ".mid")])
async def test_audio_that_cannot_be_converted_is_refused(content: bytes, extension: str) -> None:
    with pytest.raises(StockError) as caught:
        await to_storable_audio(content, extension)

    assert caught.value.code == "stock_file_unsupported"
