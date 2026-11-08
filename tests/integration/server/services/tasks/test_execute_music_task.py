"""音乐生成任务端到端：设定里的音乐模型 + 资料库里的 Stability 连线 → 真的 Stable Audio 后端（HTTP 以 respx 拦截）
→ 记账 → 登记进项目 BGM 库。"""

from __future__ import annotations

from pathlib import Path

import httpx2
import pytest
from sqlalchemy import select

from lib.bgm.library import read_bgm_library
from lib.config.repository import SystemSettingRepository
from lib.db.models.api_call import ApiCall
from lib.db.repositories.credential_repository import CredentialRepository
from lib.project.project_manager import ProjectManager
from server.services.tasks import generation_context
from server.services.tasks.music_task import execute_music_task, music_task_payload
from tests.factories import wav_bytes
from tests.fakes import bind_session_factory, use_project_manager
from tests.http_capture import capture_http, only_request

_SUBMIT = "https://api.stability.ai/v2beta/audio/stable-audio/text-to-audio"


@pytest.fixture
def music_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_factory) -> ProjectManager:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("demo", publish=False)
    manager.create_project_metadata("demo", "Demo", "Anime", "narration")
    bind_session_factory(monkeypatch, db_factory)
    use_project_manager(monkeypatch, manager)
    generation_context.invalidate_backend_cache()
    return manager


async def _stability_connection(db_factory) -> int:
    async with db_factory() as session:
        credential = await CredentialRepository(session).create(provider="stability", name="team", api_key="sk-stab")
        await SystemSettingRepository(session).set("default_music_backend", "stability/stable-audio-3")
        await session.commit()
        return credential.id


async def test_music_is_generated_billed_and_added_to_the_bgm_library(
    music_project: ProjectManager, db_factory
) -> None:
    credential_id = await _stability_connection(db_factory)
    payload = music_task_payload(
        prompt="rainy night lofi",
        provider_id="stability",
        model_id="stable-audio-3",
        credential_id=None,
        duration_seconds=2,
        name="雨夜",
    )
    with capture_http() as router:
        route = router.post(_SUBMIT).mock(
            return_value=httpx2.Response(
                200, content=wav_bytes(2.0, tone_hz=330), headers={"content-type": "audio/wav"}
            )
        )
        result = await execute_music_task("demo", "music-1", payload, task_id="t-1")

    assert only_request(route).headers["Authorization"] == "Bearer sk-stab"
    library = read_bgm_library(music_project.load_project("demo"))
    track = library[result["bgm_id"]]
    assert (track.name, track.source, track.prompt, track.model) == (
        "雨夜",
        "ai",
        "rainy night lofi",
        "stability/stable-audio-3",
    )
    assert (music_project.get_project_path("demo") / track.file).exists()
    async with db_factory() as session:
        (call,) = (await session.execute(select(ApiCall))).scalars().all()
    assert (call.provider, call.model, call.call_type, call.status) == (
        "stability",
        "stable-audio-3",
        "audio",
        "success",
    )
    assert call.credential_id == credential_id
    assert float(call.cost_amount) == pytest.approx(0.08)


async def test_a_failed_generation_adds_nothing(music_project: ProjectManager, db_factory) -> None:
    await _stability_connection(db_factory)
    payload = music_task_payload(prompt="p", provider_id="stability", model_id="stable-audio-3", credential_id=None)
    with capture_http() as router:
        router.post(_SUBMIT).mock(return_value=httpx2.Response(400, json={"errors": ["bad prompt"]}))
        with pytest.raises(httpx2.HTTPStatusError):
            await execute_music_task("demo", "music-2", payload)

    assert read_bgm_library(music_project.load_project("demo")) == {}
    async with db_factory() as session:
        (call,) = (await session.execute(select(ApiCall))).scalars().all()
    assert call.status == "failed"


async def test_a_speech_model_cannot_run_a_music_task(music_project: ProjectManager, db_factory) -> None:
    payload = music_task_payload(prompt="p", provider_id="minimax", model_id="speech-2.8-hd", credential_id=None)
    async with db_factory() as session:
        await CredentialRepository(session).create(provider="minimax", name="k", api_key="sk")
        await session.commit()

    with pytest.raises(ValueError, match="不是音乐模型"):
        await execute_music_task("demo", "music-3", payload)
