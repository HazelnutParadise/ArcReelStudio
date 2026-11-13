"""推荐变化的提示接口：读取提示、保留当前设置或改用推荐模型，使用真实数据库（docs/adr/0130）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.catalog import query as catalog
from lib.config.recommended_models import seed_provider_recommendations
from lib.config.service import ConfigService
from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from lib.i18n.zh import errors as zh_errors
from server.error_handlers import register_error_handlers
from server.routers import system_config
from tests.auth_deps import AUTH_DEPENDENCIES, override_auth
from tests.catalog_support import install_catalog, with_recommendation
from tests.fakes import use_system_config_sessions

NEXT_IMAGE = "doubao-seedream-4-5-251128"
LIST_URL = "/api/v1/system/config/recommendation-changes"
ACK_URL = "/api/v1/system/config/recommendation-changes/acknowledge"


@pytest.fixture
def recommendation_client(db_factory, monkeypatch) -> Iterator[TestClient]:
    use_system_config_sessions(monkeypatch, db_factory)
    app = FastAPI()
    override_auth(app)
    register_error_handlers(app)

    async def _session():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session
    app.include_router(system_config.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def changed_recommendation(db_factory, monkeypatch) -> str:
    """ark 首次配置时写入推荐，之后目录把推荐图片模型换成 ``NEXT_IMAGE``；返回原来的全局默认图片模型。"""
    async with db_factory() as session:
        await CredentialRepository(session).create(provider="ark", name="主 Key", api_key="TEST-ark")
        await seed_provider_recommendations(session, "ark")
        await session.commit()
    before = f"ark/{catalog.default_model('ark', 'image')}"
    install_catalog(monkeypatch, with_recommendation(catalog.factory_snapshot(), "ark", "image", NEXT_IMAGE))
    return before


async def _global_image_default(db_factory) -> str:
    async with db_factory() as session:
        return await ConfigService(session).get_setting("default_image_backend")


async def test_nothing_is_listed_when_no_provider_is_configured(recommendation_client):
    response = recommendation_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.json() == {"changes": []}


async def test_lists_the_changed_recommendation(recommendation_client, changed_recommendation):
    response = recommendation_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.json() == {
        "changes": [
            {
                "media_type": "image",
                "provider_id": "ark",
                "recommended": f"ark/{NEXT_IMAGE}",
                "current": changed_recommendation,
            }
        ]
    }


async def test_a_configured_provider_with_empty_defaults_is_offered_with_no_current_model(
    recommendation_client, db_factory
):
    async with db_factory() as session:
        await CredentialRepository(session).create(provider="dashscope", name="主 Key", api_key="TEST-dashscope")
        await session.commit()

    changes = recommendation_client.get(LIST_URL).json()["changes"]

    assert {change["media_type"]: change for change in changes}["audio"] == {
        "media_type": "audio",
        "provider_id": "dashscope",
        "recommended": f"dashscope/{catalog.default_model('dashscope', 'audio')}",
        "current": None,
    }
    assert sorted(change["media_type"] for change in changes) == ["audio", "image", "text", "video"]


async def test_a_music_only_provider_offers_nothing(recommendation_client, db_factory):
    async with db_factory() as session:
        await CredentialRepository(session).create(provider="stability", name="主 Key", api_key="TEST-stability")
        await session.commit()

    assert recommendation_client.get(LIST_URL).json() == {"changes": []}


@pytest.mark.parametrize("apply", [False, True])
async def test_acknowledging_clears_the_notice(recommendation_client, db_factory, changed_recommendation, apply):
    response = recommendation_client.post(
        ACK_URL, json={"media_type": "image", "recommended": f"ark/{NEXT_IMAGE}", "apply": apply}
    )

    assert response.status_code == 204
    assert recommendation_client.get(LIST_URL).json() == {"changes": []}
    expected = f"ark/{NEXT_IMAGE}" if apply else changed_recommendation
    assert await _global_image_default(db_factory) == expected


async def test_a_stale_recommendation_is_rejected_and_changes_nothing(
    recommendation_client, db_factory, changed_recommendation
):
    response = recommendation_client.post(
        ACK_URL, json={"media_type": "image", "recommended": "ark/doubao-seedream-4-0-250828", "apply": True}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == zh_errors.MESSAGES["recommendation_changed_again"]
    assert await _global_image_default(db_factory) == changed_recommendation
    assert len(recommendation_client.get(LIST_URL).json()["changes"]) == 1
