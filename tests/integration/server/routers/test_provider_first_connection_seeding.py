"""内置供应商的第一条连线生效时，把推荐模型写进空的全局默认模型（docs/adr/0130）。

覆盖 API 金钥与 Vertex 凭证上传两个入口；订阅登录见 ``tests/integration/server/services/test_subscription_logins.py``。
激活已有连线、删除生效连线后的自动接任都不算第一条连线生效，不写。
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.catalog import query as catalog
from lib.config.service import ConfigService
from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from lib.project.project_manager import ProjectManager
from server.error_handlers import register_error_handlers
from server.routers import providers
from tests.auth_deps import AUTH_DEPENDENCIES, override_auth
from tests.fakes import use_project_manager

SEEN_PREFIX = "recommendation_seen:"
GLOBAL_DEFAULT_KEYS = {
    "default_text_backend",
    "default_image_backend",
    "default_video_backend",
    "default_audio_backend",
}


@pytest.fixture
def providers_client(db_factory: async_sessionmaker[AsyncSession], tmp_path, monkeypatch) -> Generator[TestClient]:
    use_project_manager(monkeypatch, ProjectManager(tmp_path))
    app = FastAPI()

    async def _override_session():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    override_auth(app)
    app.include_router(providers.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    register_error_handlers(app)
    with TestClient(app) as test_client:
        yield test_client


async def _written(db_factory) -> dict[str, str]:
    """除「已见过的推荐」外写进系统设置、且有值的键。"""
    async with db_factory() as session:
        settings = await ConfigService(session).get_all_settings()
    return {key: value for key, value in settings.items() if value and not key.startswith(SEEN_PREFIX)}


async def _set(db_factory, **values: str) -> None:
    async with db_factory() as session:
        svc = ConfigService(session)
        for key, value in values.items():
            await svc.set_setting(key, value)
        await session.commit()


def _recommended(provider_id: str, media_type: str) -> str:
    model = catalog.default_model(provider_id, media_type)
    assert model is not None
    return f"{provider_id}/{model}"


def _create(client: TestClient, provider_id: str, name: str = "主 Key") -> dict:
    response = client.post(f"/api/v1/providers/{provider_id}/credentials", json={"name": name, "api_key": "TEST-key"})
    assert response.status_code == 201
    return response.json()


async def test_creating_the_first_api_key_writes_the_recommendations_into_empty_defaults(providers_client, db_factory):
    created = _create(providers_client, "ark")

    assert created["is_active"] is True
    assert await _written(db_factory) == {
        "default_text_backend": _recommended("ark", "text"),
        "default_image_backend": _recommended("ark", "image"),
        "default_video_backend": _recommended("ark", "video"),
    }
    async with db_factory() as session:
        settings = await ConfigService(session).get_all_settings()
    assert settings[f"{SEEN_PREFIX}ark:video"] == catalog.default_model("ark", "video")


async def test_a_default_the_user_already_has_is_not_overwritten(providers_client, db_factory):
    await _set(db_factory, default_image_backend="openai/gpt-image-2")

    _create(providers_client, "ark")

    written = await _written(db_factory)
    assert written["default_image_backend"] == "openai/gpt-image-2"
    assert written["default_video_backend"] == _recommended("ark", "video")


async def test_only_the_four_global_default_keys_are_written_and_no_connection_side_key(providers_client, db_factory):
    _create(providers_client, "gemini-aistudio")

    written = await _written(db_factory)
    assert set(written) == GLOBAL_DEFAULT_KEYS
    assert written["default_audio_backend"] == _recommended("gemini-aistudio", "audio")


@pytest.mark.parametrize("provider_id", ["stability", "elevenlabs"])
async def test_a_music_recommendation_is_not_written_as_the_narration_default(
    providers_client, db_factory, provider_id
):
    _create(providers_client, provider_id)

    assert await _written(db_factory) == {}


async def test_a_second_connection_is_inactive_and_does_not_write(providers_client, db_factory):
    _create(providers_client, "ark", "公司帳")
    await _set(db_factory, default_image_backend="", default_video_backend="")

    second = _create(providers_client, "ark", "個人帳")

    assert second["is_active"] is False
    written = await _written(db_factory)
    assert "default_image_backend" not in written
    assert "default_video_backend" not in written


async def test_activating_another_existing_connection_does_not_write(providers_client, db_factory):
    async with db_factory() as session:
        repo = CredentialRepository(session)
        await repo.create("ark", "公司帳", api_key="k1")
        second = await repo.create("ark", "個人帳", api_key="k2")
        await session.commit()

    response = providers_client.post(f"/api/v1/providers/ark/credentials/{second.id}/activate")

    assert response.status_code == 204
    assert await _written(db_factory) == {}


async def test_the_automatic_promotion_after_deleting_the_active_connection_does_not_write(
    providers_client, db_factory
):
    async with db_factory() as session:
        repo = CredentialRepository(session)
        first = await repo.create("ark", "公司帳", api_key="k1")
        await repo.create("ark", "個人帳", api_key="k2")
        await session.commit()

    response = providers_client.delete(f"/api/v1/providers/ark/credentials/{first.id}")

    assert response.status_code == 204
    assert await _written(db_factory) == {}


async def test_uploading_a_vertex_credential_writes_the_recommendations(providers_client, db_factory):
    response = providers_client.post(
        "/api/v1/providers/gemini-vertex/credentials/upload",
        files={"file": ("sa.json", json.dumps({"project_id": "uploaded"}), "application/json")},
    )

    assert response.status_code == 201
    assert response.json()["is_active"] is True
    written = await _written(db_factory)
    assert set(written) == GLOBAL_DEFAULT_KEYS
    assert written["default_video_backend"] == _recommended("gemini-vertex", "video")
    assert written["default_audio_backend"] == _recommended("gemini-vertex", "audio")


async def test_uploading_a_second_vertex_credential_does_not_write(providers_client, db_factory):
    upload = {"file": ("sa.json", json.dumps({"project_id": "uploaded"}), "application/json")}
    providers_client.post("/api/v1/providers/gemini-vertex/credentials/upload", files=upload)
    await _set(db_factory, default_image_backend="")

    second = providers_client.post("/api/v1/providers/gemini-vertex/credentials/upload", files=upload)

    assert second.status_code == 201
    assert second.json()["is_active"] is False
    assert "default_image_backend" not in await _written(db_factory)
