"""音频 provider 解析：resolve_audio_backend（payload > project > 全局默认 / auto）与新建 TTS 项目的预填值。"""

from __future__ import annotations

import pytest

from lib.config.resolver import ConfigResolver, NoAvailableProviderError, ProviderModel
from lib.config.service import ProviderStatus


def _ready(name: str, media_types: list[str]) -> ProviderStatus:
    return ProviderStatus(
        name=name,
        display_name=name,
        status="ready",
        media_types=media_types,
        capabilities=[],
        required_keys=[],
        credential_count=0,
    )


class _FakeSvc:
    def __init__(self, *, settings: dict[str, str] | None = None, ready: list[ProviderStatus] | None = None):
        self._settings = settings or {}
        self._ready = ready

    async def get_setting(self, key: str, default: str = "") -> str:
        return self._settings.get(key, default)

    async def get_all_settings(self) -> dict[str, str]:
        return dict(self._settings)

    async def get_all_providers_status(self) -> list[ProviderStatus]:
        if self._ready is not None:
            return self._ready
        return [_ready("dashscope", ["audio"])]


class TestResolveAudioProviderModel:
    async def test_payload_wins(self):
        resolver = ConfigResolver.__new__(ConfigResolver)
        result = await resolver._resolve_audio_provider_model(
            _FakeSvc(),
            None,
            {"audio_backend": "dashscope/qwen3-tts-flash"},
            {"audio_provider": "dashscope", "audio_model": "qwen3-tts-flash"},
        )
        assert result == ProviderModel("dashscope", "qwen3-tts-flash")

    async def test_payload_untrusted_provider_ignored(self):
        # 未知 provider 不予信任 → 回退 project
        resolver = ConfigResolver.__new__(ConfigResolver)
        result = await resolver._resolve_audio_provider_model(
            _FakeSvc(),
            None,
            {"audio_backend": "dashscope/qwen3-tts-flash"},
            {"audio_provider": "totally-unknown", "audio_model": "x"},
        )
        assert result == ProviderModel("dashscope", "qwen3-tts-flash")

    async def test_project_override(self):
        resolver = ConfigResolver.__new__(ConfigResolver)
        result = await resolver._resolve_audio_provider_model(
            _FakeSvc(),
            None,
            {"audio_backend": "dashscope/qwen3-tts-flash"},
            None,
        )
        assert result == ProviderModel("dashscope", "qwen3-tts-flash")

    async def test_falls_back_to_global_setting(self):
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={"default_audio_backend": "dashscope/qwen3-tts-flash"})
        result = await resolver._resolve_audio_provider_model(svc, None, None, None)
        assert result == ProviderModel("dashscope", "qwen3-tts-flash")

    async def test_unset_settings_do_not_pick_a_catalog_recommendation(self, db_session):
        # 无 payload / project / 全局设置 → 不按就绪供应商的目录推荐挑选（docs/adr/0130）
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={}, ready=[_ready("dashscope", ["audio"])])
        with pytest.raises(NoAvailableProviderError) as exc_info:
            await resolver._resolve_audio_provider_model(svc, db_session, None, None)
        assert exc_info.value.media_type == "audio"

    @pytest.mark.parametrize(
        "ready_names",
        [["elevenlabs"], ["stability"], ["stability", "elevenlabs"]],
        ids=["elevenlabs-only", "stability-only", "both"],
    )
    async def test_music_only_connections_never_become_the_narration_model(self, db_session, ready_names):
        """只配了 Stability / ElevenLabs、没有默认配音模型：目录里这两家 audio 的默认是音乐模型，
        旁白配音不能被挑成它，要报错请用户设置（docs/adr/0130）。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={}, ready=[_ready(name, ["audio"]) for name in ready_names])
        with pytest.raises(NoAvailableProviderError) as exc_info:
            await resolver._resolve_audio_provider_model(svc, db_session, None, None)
        assert exc_info.value.media_type == "audio"

    async def test_project_bare_builtin_provider_is_rejected(self, db_session):
        """项目的 audio_backend 只写了内置供应商：报「没有选定模型」，不补配音推荐，也不用全局设置顶替。"""
        from lib.catalog.errors import ModelNotSelectedError

        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={"default_audio_backend": "minimax/speech-2.8-hd"})
        with pytest.raises(ModelNotSelectedError) as exc_info:
            await resolver._resolve_audio_provider_model(svc, db_session, {"audio_backend": "dashscope"}, None)
        assert (exc_info.value.code, exc_info.value.params) == ("model_not_selected", {"provider": "dashscope"})

    async def test_payload_without_a_model_falls_back_to_the_settings(self, db_session):
        """历史 payload 只有 audio_provider、缺 audio_model：不补推荐，回退全局设置。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={"default_audio_backend": "minimax/speech-2.8-hd"})
        result = await resolver._resolve_audio_provider_model(svc, db_session, None, {"audio_provider": "dashscope"})
        assert result == ProviderModel("minimax", "speech-2.8-hd")


class TestResolveDefaultAudioBackend:
    async def test_global_setting_parsed(self):
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={"default_audio_backend": "dashscope/qwen3-tts-flash"})
        assert await resolver._resolve_default_audio_backend(svc, None) == ("dashscope", "qwen3-tts-flash")

    async def test_empty_setting_does_not_pick_a_catalog_recommendation(self, db_session):
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={}, ready=[_ready("dashscope", ["audio"])])
        with pytest.raises(NoAvailableProviderError) as exc_info:
            await resolver._resolve_default_audio_backend(svc, db_session)
        assert exc_info.value.media_type == "audio"
        assert "全局设置 → 默认模型" in str(exc_info.value)

    @pytest.mark.parametrize("ready_name", ["elevenlabs", "stability"])
    async def test_music_only_connection_never_becomes_the_default_narration_model(self, db_session, ready_name):
        resolver = ConfigResolver.__new__(ConfigResolver)
        svc = _FakeSvc(settings={}, ready=[_ready(ready_name, ["audio"])])
        with pytest.raises(NoAvailableProviderError):
            await resolver._resolve_default_audio_backend(svc, db_session)


class TestDefaultNarrationTts:
    """全局音频默认、音色与语速只作为新建 TTS 项目的预填值。"""

    async def test_reads_global_settings(self, db_factory):
        from lib.config.service import ConfigService

        async with db_factory() as session:
            svc = ConfigService(session)
            await svc.set_setting("default_audio_backend", "dashscope/qwen3-tts-flash")
            await svc.set_setting("narration_voice", "Ethan")
            await svc.set_setting("narration_speed", "1.2")
            await session.commit()
        resolver = ConfigResolver(db_factory)
        assert await resolver.default_narration_tts() == (
            ProviderModel("dashscope", "qwen3-tts-flash"),
            "Ethan",
            1.2,
        )

    async def test_unset_voice_and_speed_use_service_defaults(self, db_factory):
        from lib.config.service import ConfigService

        async with db_factory() as session:
            await ConfigService(session).set_setting("default_audio_backend", "dashscope/qwen3-tts-flash")
            await session.commit()
        resolver = ConfigResolver(db_factory)
        _backend, voice, speed = await resolver.default_narration_tts()
        assert voice == "Cherry"
        assert speed is None


class TestPublicAudioResolverApi:
    async def test_default_audio_backend_reads_global_setting(self, db_factory):
        from lib.config.service import ConfigService

        async with db_factory() as session:
            await ConfigService(session).set_setting("default_audio_backend", "dashscope/qwen3-tts-flash")
            await session.commit()
        resolver = ConfigResolver(db_factory)
        assert await resolver.default_audio_backend() == ("dashscope", "qwen3-tts-flash")

    async def test_resolve_audio_backend_payload_short_circuit(self, db_factory):
        resolver = ConfigResolver(db_factory)
        result = await resolver.resolve_audio_backend(
            None, {"audio_provider": "dashscope", "audio_model": "qwen3-tts-flash"}
        )
        assert result == ProviderModel("dashscope", "qwen3-tts-flash")


class TestServiceDefaultAudioBackend:
    async def test_falls_back_to_builtin_default(self, db_factory):
        from lib.config.service import ConfigService

        async with db_factory() as session:
            svc = ConfigService(session)
            assert await svc.get_default_audio_backend() == ("dashscope", "qwen3-tts-flash")


class TestServiceNarrationVoice:
    async def test_blank_setting_falls_back_to_default(self, db_factory):
        # 全局 setting 被保存成空白时回退默认值，与项目级覆盖的 strip 语义一致
        from lib.config.service import ConfigService

        async with db_factory() as session:
            svc = ConfigService(session)
            await svc.set_setting("narration_voice", "  ")
            await session.commit()
            assert await svc.get_narration_voice() == "Cherry"

            await svc.set_setting("narration_voice", "Ethan")
            await session.commit()
            assert await svc.get_narration_voice() == "Ethan"
