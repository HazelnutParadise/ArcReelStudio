"""推荐模型写进用户设置与推荐变化的提示（docs/adr/0130）。

目录给内置供应商每种媒体类型标的默认模型只作推荐：供应商首次配置时写进空的全局默认模型，之后推荐变化只提示，
由用户切换或保留。fork 的 ``audio`` 默认模型专指旁白配音，音乐模型的推荐不写也不提示。
"""

from __future__ import annotations

import asyncio

import pytest
from lib.config.recommended_models import (
    RecommendationChange,
    StaleRecommendationError,
    acknowledge_recommendation,
    recommendation_changes,
    seed_provider_recommendations,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Insert

from lib.catalog import query as catalog
from lib.config.registry import PROVIDER_REGISTRY
from lib.config.resolver import ConfigResolver, ProviderModel
from lib.config.service import ConfigService
from lib.db.repositories.credential_repository import CredentialRepository
from tests.catalog_support import install_catalog, with_recommendation

Sessions = async_sessionmaker[AsyncSession]

#: 「已见过的推荐」在系统设置里的键前缀，完整键是 ``<前缀><供应商>:<媒体类型>``（docs/adr/0130）。
SEEN_PREFIX = "recommendation_seen:"
#: 推荐只会写进这四个键；任务类型桶、文本档位、音乐音效与连线旁键都不写。
GLOBAL_DEFAULT_KEYS = {
    "default_text_backend",
    "default_image_backend",
    "default_video_backend",
    "default_audio_backend",
}
NEXT_IMAGE = "doubao-seedream-4-5-251128"
NEXT_VIDEO = "doubao-seedance-2-0-260128"
OLD_IMAGE = "doubao-seedream-4-0-250828"


async def _configure(sessions: Sessions, provider_id: str, name: str = "主 Key") -> int:
    async with sessions() as session:
        cred = await CredentialRepository(session).create(
            provider=provider_id, name=name, api_key=f"TEST-{provider_id}"
        )
        await session.commit()
        return cred.id


async def _settings(sessions: Sessions) -> dict[str, str]:
    async with sessions() as session:
        return await ConfigService(session).get_all_settings()


async def _set(sessions: Sessions, **values: str) -> None:
    async with sessions() as session:
        svc = ConfigService(session)
        for key, value in values.items():
            await svc.set_setting(key, value)
        await session.commit()


async def _seen(sessions: Sessions) -> dict[str, str]:
    return {
        key.removeprefix(SEEN_PREFIX): value
        for key, value in (await _settings(sessions)).items()
        if key.startswith(SEEN_PREFIX)
    }


async def _written(sessions: Sessions) -> dict[str, str]:
    """除「已见过的推荐」外写进系统设置、且有值的键。"""
    return {
        key: value for key, value in (await _settings(sessions)).items() if value and not key.startswith(SEEN_PREFIX)
    }


async def _seed(sessions: Sessions, provider_id: str) -> None:
    async with sessions() as session:
        await seed_provider_recommendations(session, provider_id)
        await session.commit()


async def _changes(sessions: Sessions) -> list[RecommendationChange]:
    async with sessions() as session:
        return await recommendation_changes(session)


async def _acknowledge(sessions: Sessions, provider_id: str, media_type: str, model: str, *, apply: bool) -> None:
    async with sessions() as session:
        await acknowledge_recommendation(session, provider_id, media_type, model, apply=apply)
        await session.commit()


def _recommended(provider_id: str, media_type: str) -> str:
    model = catalog.default_model(provider_id, media_type)
    assert model is not None
    return model


def _recommendation_changed(monkeypatch, provider_id: str, media_type: str, model: str | None) -> None:
    install_catalog(monkeypatch, with_recommendation(catalog.factory_snapshot(), provider_id, media_type, model))


class TestSeedProviderRecommendations:
    async def test_first_configuration_writes_recommendations_into_empty_defaults(self, session_factory):
        await _set(session_factory, default_image_backend="openai/gpt-image-2")

        await _seed(session_factory, "ark")

        settings = await _settings(session_factory)
        # 已有设置不覆盖，空的媒体类型写入推荐；ark 没有音频推荐，音频不写
        assert settings["default_image_backend"] == "openai/gpt-image-2"
        assert settings["default_text_backend"] == f"ark/{_recommended('ark', 'text')}"
        assert settings["default_video_backend"] == f"ark/{_recommended('ark', 'video')}"
        assert not settings.get("default_audio_backend")
        seen = await _seen(session_factory)
        assert seen["ark:text"] == _recommended("ark", "text")
        assert seen["ark:video"] == _recommended("ark", "video")

    async def test_only_the_four_global_default_keys_are_written_and_never_a_connection_side_key(self, session_factory):
        """任务类型桶、文本档位、音乐音效与 ``<键>_credential_id`` 都不写；写进去的值只有 ``provider/model``。"""
        await _configure(session_factory, "gemini-aistudio")

        await _seed(session_factory, "gemini-aistudio")

        written = await _written(session_factory)
        assert set(written) == GLOBAL_DEFAULT_KEYS
        assert written["default_text_backend"] == f"gemini-aistudio/{_recommended('gemini-aistudio', 'text')}"
        assert written["default_image_backend"] == f"gemini-aistudio/{_recommended('gemini-aistudio', 'image')}"
        assert written["default_video_backend"] == f"gemini-aistudio/{_recommended('gemini-aistudio', 'video')}"
        assert written["default_audio_backend"] == f"gemini-aistudio/{_recommended('gemini-aistudio', 'audio')}"

    async def test_a_second_provider_only_fills_what_is_still_empty(self, session_factory):
        await _seed(session_factory, "ark")
        await _seed(session_factory, "dashscope")

        settings = await _settings(session_factory)
        assert settings["default_video_backend"].startswith("ark/")
        assert settings["default_audio_backend"] == f"dashscope/{_recommended('dashscope', 'audio')}"

    async def test_an_existing_audio_default_is_not_overwritten(self, session_factory):
        await _set(session_factory, default_audio_backend="minimax/speech-2.8-turbo")

        await _seed(session_factory, "dashscope")

        assert (await _settings(session_factory))["default_audio_backend"] == "minimax/speech-2.8-turbo"

    @pytest.mark.parametrize(
        ("provider_id", "music_model"), [("stability", "stable-audio-3"), ("elevenlabs", "music_v2_5")]
    )
    async def test_a_music_recommendation_is_not_seeded_as_the_narration_model(
        self, session_factory, provider_id, music_model
    ):
        """这两家的音频推荐是音乐模型：只配了它们时，旁白配音的默认模型留空，音乐与音效也不写。"""
        assert _recommended(provider_id, "audio") == music_model

        await _seed(session_factory, provider_id)

        assert await _written(session_factory) == {}

    async def test_a_music_provider_does_not_block_a_later_narration_recommendation(self, session_factory):
        await _seed(session_factory, "stability")
        await _seed(session_factory, "dashscope")

        settings = await _settings(session_factory)
        assert settings["default_audio_backend"] == f"dashscope/{_recommended('dashscope', 'audio')}"

    async def test_unknown_provider_writes_nothing(self, session_factory):
        before = await _settings(session_factory)
        await _seed(session_factory, "custom-1")
        assert await _settings(session_factory) == before

    async def test_seeding_again_keeps_the_user_value_and_the_seen_record(self, session_factory, monkeypatch):
        await _seed(session_factory, "ark")
        await _set(session_factory, default_video_backend="ark/doubao-seedance-2-0-fast-260128")
        before = _recommended("ark", "video")
        _recommendation_changed(monkeypatch, "ark", "video", NEXT_VIDEO)

        await _seed(session_factory, "ark")

        settings = await _settings(session_factory)
        assert settings["default_video_backend"] == "ark/doubao-seedance-2-0-fast-260128"
        assert (await _seen(session_factory))["ark:video"] == before

    async def test_recreating_the_only_credential_keeps_a_pending_recommendation_change(
        self, session_factory, monkeypatch
    ):
        """推荐变化的提示出现后删掉唯一凭证再重建：已见过的推荐不被覆盖，提示仍在，直到用户自己处理。"""
        await _configure(session_factory, "ark")
        await _seed(session_factory, "ark")
        before = _recommended("ark", "image")
        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)
        expected = [RecommendationChange("image", "ark", NEXT_IMAGE, f"ark/{before}")]
        assert await _changes(session_factory) == expected

        await _seed(session_factory, "ark")

        assert await _changes(session_factory) == expected
        assert (await _seen(session_factory))["ark:image"] == before


class TestRecommendationChangesKeepGenerationModels:
    @pytest.fixture(autouse=True)
    async def ark_configured(self, session_factory):
        await _configure(session_factory, "ark")
        await _seed(session_factory, "ark")

    async def test_nothing_is_suggested_right_after_seeding(self, session_factory):
        assert await _changes(session_factory) == []

    async def test_changed_recommendation_does_not_change_the_configured_model(self, session_factory, monkeypatch):
        """已配置的用户：目录推荐变化后生成用的模型不变，推荐变化以提示呈现，由用户决定是否切换。"""
        before = _recommended("ark", "image")
        resolver = ConfigResolver(session_factory)
        assert await resolver.resolve_image_backend(None, None, generation_type="t2i") == ProviderModel("ark", before)

        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)

        assert await resolver.resolve_image_backend(None, None, generation_type="t2i") == ProviderModel("ark", before)
        assert await _changes(session_factory) == [RecommendationChange("image", "ark", NEXT_IMAGE, f"ark/{before}")]

    async def test_keeping_the_current_model_dismisses_the_notice(self, session_factory, monkeypatch):
        before = _recommended("ark", "image")
        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)

        await _acknowledge(session_factory, "ark", "image", NEXT_IMAGE, apply=False)

        assert await _changes(session_factory) == []
        assert (await _settings(session_factory))["default_image_backend"] == f"ark/{before}"
        assert (await _seen(session_factory))["ark:image"] == NEXT_IMAGE

    async def test_switching_sets_the_global_default(self, session_factory, monkeypatch):
        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)

        await _acknowledge(session_factory, "ark", "image", NEXT_IMAGE, apply=True)

        assert await _changes(session_factory) == []
        resolved = await ConfigResolver(session_factory).resolve_image_backend(None, None, generation_type="t2i")
        assert resolved == ProviderModel("ark", NEXT_IMAGE)
        assert (await _seen(session_factory))["ark:image"] == NEXT_IMAGE

    async def test_acknowledging_a_stale_recommendation_changes_nothing(self, session_factory):
        before = await _settings(session_factory)
        async with session_factory() as session:
            with pytest.raises(StaleRecommendationError):
                await acknowledge_recommendation(session, "ark", "image", NEXT_IMAGE, apply=True)
        assert await _settings(session_factory) == before

    async def test_a_model_chosen_by_the_user_is_not_nagged_until_the_recommendation_changes(
        self, session_factory, monkeypatch
    ):
        await _set(session_factory, default_image_backend=f"ark/{OLD_IMAGE}")
        assert await _changes(session_factory) == []

        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)
        assert [change.recommended_model for change in await _changes(session_factory)] == [NEXT_IMAGE]

    async def test_a_dismissed_recommendation_is_not_shown_again_but_the_next_change_is(
        self, session_factory, monkeypatch
    ):
        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)
        await _acknowledge(session_factory, "ark", "image", NEXT_IMAGE, apply=False)
        assert await _changes(session_factory) == []

        _recommendation_changed(monkeypatch, "ark", "image", OLD_IMAGE)

        assert [change.recommended_model for change in await _changes(session_factory)] == [OLD_IMAGE]

    async def test_a_music_recommendation_is_never_suggested_for_the_narration_default(
        self, session_factory, monkeypatch
    ):
        """全局旁白配音默认是 Gemini 的配音模型，它的音频推荐换成了音乐模型：不提示，也不能确认。"""
        await _configure(session_factory, "gemini-aistudio")
        await _set(session_factory, default_audio_backend="gemini-aistudio/gemini-3.8-flash-lite-tts")
        _recommendation_changed(monkeypatch, "gemini-aistudio", "audio", "lyria-3.5")

        assert [change for change in await _changes(session_factory) if change.media_type == "audio"] == []
        async with session_factory() as session:
            with pytest.raises(StaleRecommendationError):
                await acknowledge_recommendation(session, "gemini-aistudio", "audio", "lyria-3.5", apply=True)


class TestRecommendationsForAnEmptyDefault:
    async def test_a_new_recommendation_is_suggested_when_the_default_is_empty(self, session_factory, monkeypatch):
        """供应商配置时还没有这个媒体类型的推荐，之后才有：全局默认模型为空时提示设为默认。"""
        snapshot = with_recommendation(catalog.factory_snapshot(), "ark", "image", None)
        install_catalog(monkeypatch, snapshot)
        await _configure(session_factory, "ark")
        await _seed(session_factory, "ark")
        assert "default_image_backend" not in await _settings(session_factory)

        install_catalog(monkeypatch, with_recommendation(snapshot, "ark", "image", NEXT_IMAGE))

        assert await _changes(session_factory) == [RecommendationChange("image", "ark", NEXT_IMAGE, None)]

    async def test_the_first_configured_provider_in_registry_order_is_offered_once_per_media_type(
        self, session_factory
    ):
        """dashscope 先配、ark 后配，都还没有写入推荐：每个媒体类型只提示一条，取注册顺序靠前的。"""
        order = list(PROVIDER_REGISTRY)
        assert order.index("ark") < order.index("dashscope")
        await _configure(session_factory, "dashscope")
        await _configure(session_factory, "ark")

        changes = await _changes(session_factory)

        assert {
            change.media_type: (change.provider_id, change.recommended_model, change.current) for change in changes
        } == {
            "text": ("ark", _recommended("ark", "text"), None),
            "image": ("ark", _recommended("ark", "image"), None),
            "video": ("ark", _recommended("ark", "video"), None),
            "audio": ("dashscope", _recommended("dashscope", "audio"), None),
        }
        assert len(changes) == 4

    async def test_a_provider_without_a_credential_is_not_offered(self, session_factory):
        assert await _changes(session_factory) == []

    @pytest.mark.parametrize("provider_id", ["stability", "elevenlabs"])
    async def test_a_music_recommendation_is_not_offered_as_the_narration_default(self, session_factory, provider_id):
        await _configure(session_factory, provider_id)

        assert [change for change in await _changes(session_factory) if change.media_type == "audio"] == []

    async def test_applying_an_offer_for_an_empty_default_sets_it_and_dismisses_the_notice(self, session_factory):
        await _configure(session_factory, "ark")
        offered = [change for change in await _changes(session_factory) if change.media_type == "video"]
        assert offered == [RecommendationChange("video", "ark", _recommended("ark", "video"), None)]

        await _acknowledge(session_factory, "ark", "video", _recommended("ark", "video"), apply=True)

        assert (await _settings(session_factory))["default_video_backend"] == f"ark/{_recommended('ark', 'video')}"
        assert [change for change in await _changes(session_factory) if change.media_type == "video"] == []

    async def test_keeping_an_empty_default_dismisses_the_offer_without_setting_it(self, session_factory):
        await _configure(session_factory, "ark")

        await _acknowledge(session_factory, "ark", "video", _recommended("ark", "video"), apply=False)

        assert not (await _settings(session_factory)).get("default_video_backend")
        assert [change for change in await _changes(session_factory) if change.media_type == "video"] == []


class TestApplyingARecommendationAndTheConnectionSideKey:
    async def test_switching_provider_clears_the_connection_side_key(self, session_factory):
        openai_connection = await _configure(session_factory, "openai")
        await _configure(session_factory, "ark")
        await _set(
            session_factory,
            default_image_backend="openai/gpt-image-2",
            default_image_backend_credential_id=str(openai_connection),
        )

        await _acknowledge(session_factory, "ark", "image", _recommended("ark", "image"), apply=True)

        settings = await _settings(session_factory)
        assert settings["default_image_backend"] == f"ark/{_recommended('ark', 'image')}"
        assert not settings.get("default_image_backend_credential_id")

    async def test_the_same_provider_keeps_the_connection_the_user_chose(self, session_factory, monkeypatch):
        await _configure(session_factory, "ark", "公司帳")
        chosen = await _configure(session_factory, "ark", "個人帳")
        await _set(
            session_factory,
            default_image_backend=f"ark/{OLD_IMAGE}",
            default_image_backend_credential_id=str(chosen),
        )
        _recommendation_changed(monkeypatch, "ark", "image", NEXT_IMAGE)

        await _acknowledge(session_factory, "ark", "image", NEXT_IMAGE, apply=True)

        settings = await _settings(session_factory)
        assert settings["default_image_backend"] == f"ark/{NEXT_IMAGE}"
        assert settings["default_image_backend_credential_id"] == str(chosen)


async def test_concurrent_acknowledgements_of_two_media_types_are_both_kept(concurrent_session_factory, monkeypatch):
    """同一供应商两个媒体类型的推荐同时变化、各自确认：两次确认都在对方读完之后才写，两条都记下。

    每次确认用独立的连接与事务，握手放在数据库边界（第一条写语句之前）；SQLite 文件库与 PostgreSQL 下都成立，
    不靠进程内的锁。
    """
    sessions = concurrent_session_factory
    await _configure(sessions, "ark")
    await _seed(sessions, "ark")
    changed = with_recommendation(catalog.factory_snapshot(), "ark", "image", NEXT_IMAGE)
    install_catalog(monkeypatch, with_recommendation(changed, "ark", "video", NEXT_VIDEO))
    assert len(await _changes(sessions)) == 2

    both_read = asyncio.Barrier(2)

    class _ReadsBeforeWrites(AsyncSession):
        """执行第一条写语句前等另一个会话也走到这里：两次确认都在对方读完之后才写。"""

        waited = False

        async def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Insert) and not self.waited:
                self.waited = True
                await asyncio.wait_for(both_read.wait(), 5)
            return await super().execute(statement, *args, **kwargs)

    racing = async_sessionmaker(sessions.kw["bind"], class_=_ReadsBeforeWrites, expire_on_commit=False)

    async def acknowledge(media_type: str, model: str) -> None:
        async with racing() as session:
            await acknowledge_recommendation(session, "ark", media_type, model, apply=False)
            await session.commit()

    await asyncio.gather(acknowledge("image", NEXT_IMAGE), acknowledge("video", NEXT_VIDEO))

    assert await _changes(sessions) == []
    seen = await _seen(sessions)
    assert (seen["ark:image"], seen["ark:video"]) == (NEXT_IMAGE, NEXT_VIDEO)
