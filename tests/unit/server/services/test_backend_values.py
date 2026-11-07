"""设置里「连线」旁键的写入校验：指定的连线必须存在，且属于同一字段所选的供应商。"""

from __future__ import annotations

import pytest

from lib.db.repositories.credential_repository import CredentialRepository
from lib.infra.api_errors import BadRequestError
from server.services.backend_values import validate_backend_credential


@pytest.fixture
async def credentials(db_session):
    repo = CredentialRepository(db_session)
    first = await repo.create("gemini-aistudio", "公司帳", api_key="k1")
    second = await repo.create("gemini-aistudio", "個人帳", api_key="k2")
    other = await repo.create("openai", "OpenAI", api_key="k3")
    await db_session.commit()
    return first.id, second.id, other.id


async def test_no_connection_means_the_provider_default(db_session, credentials) -> None:
    assert await validate_backend_credential(db_session, "gemini-aistudio/gemini-3-pro", None) is None


async def test_a_connection_of_the_selected_provider_is_accepted(db_session, credentials) -> None:
    _, second, _ = credentials
    assert await validate_backend_credential(db_session, "gemini-aistudio/gemini-3-pro", second) == second


async def test_a_connection_of_another_provider_is_rejected(db_session, credentials) -> None:
    *_, other = credentials
    with pytest.raises(BadRequestError) as exc:
        await validate_backend_credential(db_session, "gemini-aistudio/gemini-3-pro", other)
    assert exc.value.key == "credential_not_for_provider"


async def test_a_missing_connection_is_rejected(db_session, credentials) -> None:
    with pytest.raises(BadRequestError) as exc:
        await validate_backend_credential(db_session, "gemini-aistudio/gemini-3-pro", 9999)
    assert exc.value.key == "credential_not_for_provider"


async def test_custom_providers_and_empty_values_take_no_connection(db_session, credentials) -> None:
    first, *_ = credentials
    for value in ("custom-3/my-model", ""):
        with pytest.raises(BadRequestError) as exc:
            await validate_backend_credential(db_session, value, first)
        assert exc.value.key == "credential_not_for_provider"
