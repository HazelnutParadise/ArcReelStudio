"""删除被设置指定的连线：先列出位置、要确认才删，确认后那些设置改回默认连线。"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.config.service import ConfigService
from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from lib.project.project_manager import ProjectManager
from server.error_handlers import register_error_handlers
from server.routers import providers
from tests.auth_deps import AUTH_DEPENDENCIES, override_auth
from tests.fakes import use_project_manager


@pytest.fixture
def credential_refs_client(db_factory: async_sessionmaker[AsyncSession]) -> Generator[TestClient]:
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


@pytest.fixture
def credential_refs_pm(tmp_path, monkeypatch) -> ProjectManager:
    manager = ProjectManager(tmp_path)
    use_project_manager(monkeypatch, manager)
    return manager


@pytest.fixture
async def pinned(db_factory, credential_refs_pm) -> int:
    async with db_factory() as session:
        repo = CredentialRepository(session)
        await repo.create("gemini-aistudio", "公司帳", api_key="k1")
        second = await repo.create("gemini-aistudio", "個人帳", api_key="k2")
        svc = ConfigService(session)
        await svc.set_setting("default_image_backend", "gemini-aistudio/gemini-3-pro")
        await svc.set_setting("default_image_backend_credential_id", str(second.id))
        await session.commit()
    credential_refs_pm.create_project("pa")
    credential_refs_pm.update_project(
        "pa",
        lambda p: p.update(
            {"title": "雨夜", "video_backend": "gemini-aistudio/veo-3", "video_backend_credential_id": second.id}
        ),
    )
    credential_refs_pm.create_project("pb")
    return second.id


def test_references_list_global_settings_and_projects(credential_refs_client, pinned) -> None:
    resp = credential_refs_client.get(f"/api/v1/providers/gemini-aistudio/credentials/{pinned}/references")

    assert resp.status_code == 200
    assert resp.json() == {
        "settings": ["default_image_backend"],
        "projects": [{"name": "pa", "title": "雨夜", "settings": ["video_backend"]}],
    }


def test_deleting_a_connection_in_use_needs_confirmation(credential_refs_client, pinned) -> None:
    resp = credential_refs_client.delete(f"/api/v1/providers/gemini-aistudio/credentials/{pinned}")

    assert resp.status_code == 409
    listed = credential_refs_client.get("/api/v1/providers/gemini-aistudio/credentials").json()["credentials"]
    assert pinned in [c["id"] for c in listed]


async def test_confirmed_delete_returns_those_settings_to_the_default(
    credential_refs_client, pinned, db_factory, credential_refs_pm
) -> None:
    resp = credential_refs_client.delete(f"/api/v1/providers/gemini-aistudio/credentials/{pinned}?force=true")

    assert resp.status_code == 204
    async with db_factory() as session:
        settings = await ConfigService(session).get_all_settings()
    assert settings.get("default_image_backend_credential_id", "") == ""
    assert settings["default_image_backend"] == "gemini-aistudio/gemini-3-pro"
    project = credential_refs_pm.load_project("pa")
    assert "video_backend_credential_id" not in project
    assert project["video_backend"] == "gemini-aistudio/veo-3"


def test_every_connection_is_listed_across_providers(credential_refs_client, pinned) -> None:
    resp = credential_refs_client.get("/api/v1/providers/credentials")

    assert resp.status_code == 200
    listed = [(c["provider"], c["name"]) for c in resp.json()["credentials"]]
    assert listed == [("gemini-aistudio", "公司帳"), ("gemini-aistudio", "個人帳")]
