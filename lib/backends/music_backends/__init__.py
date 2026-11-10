"""音乐与音效生成后端（docs/adr/0126、0127）：都是「提示词 + 长度 → 音频」。端点名即注册名。"""

from __future__ import annotations

from lib.backends.music_backends.base import MusicBackend, MusicGenerationRequest, MusicGenerationResult
from lib.backends.music_backends.elevenlabs import ElevenLabsMusicBackend
from lib.backends.music_backends.elevenlabs_sfx import ElevenLabsSoundEffectsBackend
from lib.backends.music_backends.lyria import LyriaMusicBackend
from lib.backends.music_backends.registry import create_backend, get_registered_backends, register_backend
from lib.backends.music_backends.stable_audio import StableAudioBackend

register_backend("gemini-lyria", LyriaMusicBackend)
register_backend("stability-audio", StableAudioBackend)
register_backend("elevenlabs-music", ElevenLabsMusicBackend)
register_backend("elevenlabs-sfx", ElevenLabsSoundEffectsBackend)

__all__ = [
    "ElevenLabsMusicBackend",
    "ElevenLabsSoundEffectsBackend",
    "LyriaMusicBackend",
    "MusicBackend",
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "StableAudioBackend",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]
