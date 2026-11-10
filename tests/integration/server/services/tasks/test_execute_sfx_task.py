"""音效生成任务端到端：设定里的音效模型 + 资料库里的 ElevenLabs 连线 → 真的 ElevenLabs 音效后端（HTTP 以 respx 拦截）
→ 记账 → 登记进项目音效库。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import select

from lib.config.repository import SystemSettingRepository
from lib.db.models.api_call import ApiCall
from lib.db.repositories.credential_repository import CredentialRepository
from lib.project.project_manager import ProjectManager
from lib.sfx.library import read_sfx_library
from server.services.tasks import generation_context
from server.services.tasks.sfx_task import execute_sfx_task, sfx_task_payload
from tests.factories import wav_bytes
from tests.fakes import bind_session_factory, use_project_manager
from tests.http_capture import capture_http, only_request

_GENERATE = "https://api.elevenlabs.io/v1/sound-generation"


@pytest.fixture
def sfx_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_factory) -> ProjectManager:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("demo", publish=False)
    manager.create_project_metadata("demo", "Demo", "Anime", "narration")
    bind_session_factory(monkeypatch, db_factory)
    use_project_manager(monkeypatch, manager)
    generation_context.invalidate_backend_cache()
    return manager


async def _elevenlabs_connection(db_factory) -> int:
    async with db_factory() as session:
        credential = await CredentialRepository(session).create(provider="elevenlabs", name="team", api_key="xi-key")
        await SystemSettingRepository(session).set("default_sfx_backend", "elevenlabs/eleven_text_to_sound_v3")
        await session.commit()
        return credential.id


async def test_a_sound_effect_is_generated_billed_and_added_to_the_library(
    sfx_project: ProjectManager, db_factory
) -> None:
    credential_id = await _elevenlabs_connection(db_factory)
    payload = sfx_task_payload(
        prompt="glass shattering on a stone floor",
        provider_id="elevenlabs",
        model_id="eleven_text_to_sound_v3",
        credential_id=None,
        duration_seconds=2,
        name="玻璃碎裂",
    )
    with capture_http() as router:
        route = router.post(_GENERATE).mock(
            return_value=httpx2.Response(
                200, content=wav_bytes(2.0, tone_hz=660), headers={"content-type": "audio/wav"}
            )
        )
        result = await execute_sfx_task("demo", "sfx-1", payload, task_id="t-1")

    request = only_request(route)
    assert request.headers["xi-api-key"] == "xi-key"
    assert json.loads(request.content) == {
        "text": "glass shattering on a stone floor",
        "model_id": "eleven_text_to_sound_v3",
        "duration_seconds": 2.0,
    }
    sound = read_sfx_library(sfx_project.load_project("demo"))[result["sfx_id"]]
    assert (sound.name, sound.source, sound.prompt, sound.model) == (
        "玻璃碎裂",
        "ai",
        "glass shattering on a stone floor",
        "elevenlabs/eleven_text_to_sound_v3",
    )
    assert (sfx_project.get_project_path("demo") / sound.file).exists()
    async with db_factory() as session:
        (call,) = (await session.execute(select(ApiCall))).scalars().all()
    assert (call.provider, call.model, call.call_type, call.status) == (
        "elevenlabs",
        "eleven_text_to_sound_v3",
        "audio",
        "success",
    )
    assert call.credential_id == credential_id
    # $0.12 / 分钟，2 秒
    assert float(call.cost_amount) == pytest.approx(0.004)


async def test_a_sound_effect_task_is_refused_when_no_sound_effect_model_is_set(sfx_project: ProjectManager, db_factory) -> None:
    async with db_factory() as session:
        await SystemSettingRepository(session).set("default_sfx_backend", "")
        await session.commit()
    payload = {"prompt": "door slam"}

    with pytest.raises(ValueError, match="default_sfx_backend"):
        await execute_sfx_task("demo", "sfx-2", payload)

    assert read_sfx_library(sfx_project.load_project("demo")) == {}
