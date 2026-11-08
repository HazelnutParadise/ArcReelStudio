"""音乐生成后端（docs/adr/0126）。端点名即注册名。"""

from __future__ import annotations

from lib.backends.music_backends.base import MusicBackend, MusicGenerationRequest, MusicGenerationResult
from lib.backends.music_backends.elevenlabs import ElevenLabsMusicBackend
from lib.backends.music_backends.lyria import LyriaMusicBackend
from lib.backends.music_backends.registry import create_backend, get_registered_backends, register_backend
from lib.backends.music_backends.stable_audio import StableAudioBackend

register_backend("gemini-lyria", LyriaMusicBackend)
register_backend("stability-audio", StableAudioBackend)
register_backend("elevenlabs-music", ElevenLabsMusicBackend)

__all__ = [
    "ElevenLabsMusicBackend",
    "LyriaMusicBackend",
    "MusicBackend",
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "StableAudioBackend",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]
