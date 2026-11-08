"""音乐后端：Stable Audio 与 ElevenLabs 经 respx 捕获真实请求；Lyria 以假 SDK 客户端验证请求与写盘。"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from lib.backends.music_backends import (
    ElevenLabsMusicBackend,
    LyriaMusicBackend,
    MusicGenerationRequest,
    StableAudioBackend,
    create_backend,
)
from tests.http_capture import capture_http, only_request, request_json

_STABLE_SUBMIT = "https://api.stability.ai/v2beta/audio/stable-audio/text-to-audio"
_ELEVEN = "https://api.elevenlabs.io/v1/music"


async def test_stable_audio_returns_direct_audio(tmp_path: Path) -> None:
    out = tmp_path / "song.mp3"
    with capture_http() as router:
        route = router.post(_STABLE_SUBMIT).mock(
            return_value=httpx2.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"})
        )
        backend = StableAudioBackend(api_key="sk-stab")
        result = await backend.generate(
            MusicGenerationRequest(prompt="calm piano", output_path=out, duration_seconds=45)
        )

    sent = only_request(route)
    assert sent.headers["Authorization"] == "Bearer sk-stab"
    body = sent.content.decode("utf-8", "replace")
    assert 'name="prompt"' in body
    assert "calm piano" in body
    assert 'name="duration"' in body
    assert "45" in body
    assert out.read_bytes() == b"ID3mp3"
    assert (result.provider, result.model, result.duration_seconds) == ("stability", "stable-audio-3", 45)


async def test_stable_audio_polls_until_the_job_finishes(tmp_path: Path) -> None:
    out = tmp_path / "song.wav"
    with capture_http() as router:
        router.post(_STABLE_SUBMIT).mock(return_value=httpx2.Response(202, json={"id": "job-1"}))
        router.get("https://api.stability.ai/v2beta/audio/results/job-1").mock(
            side_effect=[
                httpx2.Response(202, json={"status": "in-progress"}),
                httpx2.Response(200, content=b"RIFFwav", headers={"content-type": "audio/wav"}),
            ]
        )
        backend = StableAudioBackend(api_key="sk", poll_interval=0)
        await backend.generate(MusicGenerationRequest(prompt="drums", output_path=out, duration_seconds=999))

    assert out.read_bytes() == b"RIFFwav"


async def test_stable_audio_clamps_the_length(tmp_path: Path) -> None:
    with capture_http() as router:
        route = router.post(_STABLE_SUBMIT).mock(
            return_value=httpx2.Response(200, content=b"x", headers={"content-type": "audio/mpeg"})
        )
        result = await StableAudioBackend(api_key="sk").generate(
            MusicGenerationRequest(prompt="p", output_path=tmp_path / "a.mp3", duration_seconds=999)
        )
    assert result.duration_seconds == 380
    assert "380" in only_request(route).content.decode("utf-8", "replace")


async def test_elevenlabs_sends_length_in_ms_and_instrumental_flag(tmp_path: Path) -> None:
    out = tmp_path / "song.mp3"
    with capture_http() as router:
        route = router.post(_ELEVEN).mock(return_value=httpx2.Response(200, content=b"ID3eleven"))
        result = await ElevenLabsMusicBackend(api_key="xi").generate(
            MusicGenerationRequest(prompt="epic orchestra", output_path=out, duration_seconds=90, instrumental=False)
        )

    sent = only_request(route)
    assert sent.headers["xi-api-key"] == "xi"
    assert request_json(sent) == {
        "prompt": "epic orchestra",
        "music_length_ms": 90000,
        "model_id": "music_v2_5",
        "force_instrumental": False,
    }
    assert out.read_bytes() == b"ID3eleven"
    assert result.provider == "elevenlabs"


async def test_elevenlabs_failure_raises_without_a_file(tmp_path: Path) -> None:
    out = tmp_path / "song.mp3"
    with capture_http() as router:
        router.post(_ELEVEN).mock(return_value=httpx2.Response(401, json={"detail": "bad key"}))
        with pytest.raises(httpx2.HTTPStatusError):
            await ElevenLabsMusicBackend(api_key="xi").generate(MusicGenerationRequest(prompt="p", output_path=out))
    assert not out.exists()


class _FakeInteractions:
    def __init__(self, audio: bytes | None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._audio = audio

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        output = None if self._audio is None else SimpleNamespace(data=base64.b64encode(self._audio).decode())
        return SimpleNamespace(output_audio=output)


def _fake_client(audio: bytes | None) -> tuple[Any, _FakeInteractions]:
    interactions = _FakeInteractions(audio)
    return SimpleNamespace(aio=SimpleNamespace(interactions=interactions)), interactions


async def test_lyria_writes_the_returned_audio_and_asks_for_the_length(tmp_path: Path) -> None:
    client, interactions = _fake_client(b"ID3lyria")
    out = tmp_path / "song.mp3"
    result = await LyriaMusicBackend(client=client).generate(
        MusicGenerationRequest(prompt="lofi beat", output_path=out, duration_seconds=60)
    )

    (call,) = interactions.calls
    assert call["model"] == "lyria-3.5"
    assert "lofi beat" in call["input"]
    assert "60 seconds" in call["input"]
    assert "Instrumental" in call["input"]
    assert out.read_bytes() == b"ID3lyria"
    assert result.model == "lyria-3.5"


async def test_lyria_without_audio_fails(tmp_path: Path) -> None:
    client, _ = _fake_client(None)
    with pytest.raises(RuntimeError):
        await LyriaMusicBackend(client=client).generate(
            MusicGenerationRequest(prompt="p", output_path=tmp_path / "a.mp3")
        )


def test_backends_are_registered_by_endpoint() -> None:
    assert isinstance(create_backend("stability-audio", api_key="k"), StableAudioBackend)
    assert isinstance(create_backend("elevenlabs-music", api_key="k"), ElevenLabsMusicBackend)
    with pytest.raises(ValueError, match="Unknown music backend"):
        create_backend("nope")
