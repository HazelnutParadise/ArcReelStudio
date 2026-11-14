"""Vertex 凭证经配置解析与后端装配：用连线自己的凭证文件，找不到时报出是哪条连线，不拿别的文件顶替。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.backends.backend_assembly.assembler import assemble_backend
from lib.catalog import query as catalog
from lib.config.resolver import ConfigResolver
from lib.config.vertex_credentials import VertexCredentialMissingError
from lib.db.repositories.credential_repository import CredentialRepository
from lib.generation.task_failure import render_failure
from lib.generation.task_failure_encoding import encode_task_failure_message
from lib.i18n import _ as translate_message
from lib.infra.app_data_dir import reset_for_tests
from lib.infra.data_root_layout import DataRootLayout
from tests.factories import make_display_names
from tests.fakes import captured_vertex_credentials


@pytest.mark.parametrize("media_type", ["image", "video", "text"])
async def test_vertex_uses_recorded_credential_when_derived_file_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    db_factory: async_sessionmaker[AsyncSession],
    media_type: str,
) -> None:
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(tmp_path / "data"))
    recorded = tmp_path / "legacy" / "vertex.json"
    recorded.parent.mkdir()
    recorded.write_text(json.dumps({"project_id": "legacy-project"}), encoding="utf-8")
    repo = CredentialRepository(db_session)
    cred = await repo.create(provider="gemini-vertex", name="Vertex", credentials_path=str(recorded))
    await repo.activate(cred.id, "gemini-vertex")
    await db_session.commit()

    with (
        patch("google.genai.Client"),
        captured_vertex_credentials() as load_credentials,
    ):
        backend = await assemble_backend(
            provider_id="gemini-vertex",
            media_type=media_type,
            model_id=catalog.default_model("gemini-vertex", media_type),
            resolver=ConfigResolver(db_factory),
        )

    assert backend is not None
    assert load_credentials.call_args.args[0] == str(recorded)


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DataRootLayout]:
    """数据根指向本用例的临时目录；数据根按进程缓存，前后各清一次。"""
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(tmp_path / "data"))
    reset_for_tests()
    yield DataRootLayout.current()
    reset_for_tests()


@pytest.mark.parametrize("media_type", ["image", "video", "text", "audio"])
async def test_vertex_without_its_own_file_names_the_connection_instead_of_using_another_file(
    data_root: DataRootLayout,
    db_session: AsyncSession,
    db_factory: async_sessionmaker[AsyncSession],
    media_type: str,
) -> None:
    repo = CredentialRepository(db_session)
    other = await repo.create(provider="gemini-vertex", name="Other account", credentials_path=None)
    await db_session.flush()
    # 另一条连线的凭证文件在 vertex_keys/ 里：不能被拿来顶替。
    other_file = data_root.vertex_credential_path(other.id)
    other_file.parent.mkdir(parents=True)
    other_file.write_text(json.dumps({"project_id": "other-project"}), encoding="utf-8")
    (other_file.parent / "vertex_credentials.json").write_text(json.dumps({"project_id": "x"}), encoding="utf-8")
    cred = await repo.create(provider="gemini-vertex", name="Studio account", credentials_path=None)
    await repo.activate(cred.id, "gemini-vertex")
    await db_session.commit()

    with (
        patch("google.genai.Client"),
        captured_vertex_credentials() as load_credentials,
        pytest.raises(VertexCredentialMissingError) as raised,
    ):
        await assemble_backend(
            provider_id="gemini-vertex",
            media_type=media_type,
            model_id=_vertex_model(media_type),
            resolver=ConfigResolver(db_factory),
        )

    assert load_credentials.call_count == 0
    assert raised.value.key == "vertex_credential_file_missing"
    assert raised.value.params == {"connection": "Studio account"}
    rendered = render_failure(
        encode_task_failure_message(raised.value),
        lambda key, **params: translate_message(key, locale="zh", **params),
        make_display_names("zh"),
    )
    assert rendered == (
        "Vertex AI 连线「Studio account」的凭证文件不见了，无法调用；请在连线中心重新上传这个服务账号的凭证文件"
    )


async def test_vertex_without_any_connection_asks_to_upload_a_credential(
    data_root: DataRootLayout, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    stray = data_root.vertex_keys_dir / "vertex_cred_7.json"
    stray.parent.mkdir(parents=True)
    stray.write_text(json.dumps({"project_id": "stray"}), encoding="utf-8")

    with (
        patch("google.genai.Client"),
        captured_vertex_credentials() as load_credentials,
        pytest.raises(VertexCredentialMissingError) as raised,
    ):
        await assemble_backend(
            provider_id="gemini-vertex",
            media_type="image",
            model_id=_vertex_model("image"),
            resolver=ConfigResolver(db_factory),
        )

    assert load_credentials.call_count == 0
    assert raised.value.key == "vertex_connection_missing"


def _vertex_model(media_type: str) -> str:
    model = catalog.default_model("gemini-vertex", media_type)
    assert model is not None
    return model
