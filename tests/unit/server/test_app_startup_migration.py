"""FastAPI 启动：全新数据根照常起来；遍历项目的步骤按当前布局找项目，跑完项目 schema 迁移与过期备份回收。"""

import json
import os
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import SimpleNamespace

import pytest

import server.app as app_module
from lib.infra.data_root_layout import DataRootLayout
from lib.project.project_manager import ProjectManager
from lib.project.project_migration_failure import MIGRATION_FAILURE_FILENAME, SCHEMA_UNSUPPORTED_CODE
from lib.project.project_migrations.runner import CURRENT_SCHEMA_VERSION
from tests.unit.server.app_lifespan_support import stub_lifespan_dependencies


async def _noop_async(*args, **kwargs):
    """No-op coroutine for mocking async startup steps."""


def _seed_stale_project(projects_root: Path) -> tuple[Path, Path]:
    """种一个落后版本的项目，外加一份 8 天前的旧版备份。"""
    project_dir = projects_root / "p1"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps(
            {"schema_version": 19, "name": "p1", "video_backend": "ark", "image_provider_t2i": "openai/gpt-image-2"}
        ),
        encoding="utf-8",
    )
    stale_backup = project_dir / "project.json.bak.v19-100000000"
    stale_backup.write_text("recovery", encoding="utf-8")
    expired = time.time() - 8 * 86400
    os.utime(stale_backup, (expired, expired))
    return project_dir, stale_backup


@pytest.mark.asyncio
async def test_startup_migrates_projects_and_reaps_stale_backups(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    project_dir, stale_backup = _seed_stale_project(DataRootLayout(data_root).projects_dir)

    # 数据目录指向 tmp：迁移与备份回收都照真实跑，落点是本用例种下的项目。
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    monkeypatch.setattr("lib.project.project_manager.get_project_manager", lambda: ProjectManager(data_root))
    stub_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "migrate_local_transcripts_to_store", _noop_async)

    app = app_module.app
    app.state = SimpleNamespace()

    async with app_module.lifespan(app):
        pass

    migrated = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert not stale_backup.exists()


@pytest.mark.asyncio
async def test_startup_project_walks_run_on_projects_under_the_current_layout(tmp_path, monkeypatch):
    """源文件编码迁移、schema 迁移、备份回收、Agent 配置物化与本地会话导入都在 ``<数据根>/projects/`` 下找项目。"""
    data_root = tmp_path / "data"
    project_dir, stale_backup = _seed_stale_project(DataRootLayout(data_root).projects_dir)
    (project_dir / "source").mkdir()
    source_bytes = "春天来了".encode("gbk")
    (project_dir / "source" / "novel.txt").write_bytes(source_bytes)
    imported_from: list[Path] = []

    async def import_transcripts(_store, *, data_root: Path) -> None:
        imported_from.append(data_root)

    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    monkeypatch.setenv("ARCREEL_SDK_SESSION_STORE", "db")
    monkeypatch.setattr(app_module, "migrate_local_transcripts_to_store", import_transcripts)
    monkeypatch.setattr("lib.project.project_manager.get_project_manager", lambda: ProjectManager(data_root))
    stub_lifespan_dependencies(monkeypatch)

    app = app_module.app
    app.state = SimpleNamespace()

    async with app_module.lifespan(app):
        pass

    assert imported_from == [data_root.resolve()]
    migrated_source = (project_dir / "source" / "novel.txt").read_bytes()
    migrated_source.decode("utf-8")
    assert migrated_source != source_bytes
    assert (project_dir / "source" / "raw" / "novel.txt").read_bytes() == source_bytes
    assert (
        json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["schema_version"]
        == CURRENT_SCHEMA_VERSION
    )
    assert not stale_backup.exists()
    assert (project_dir / "CLAUDE.md").is_file()


@pytest.mark.asyncio
async def test_catalog_layers_load_before_project_migrations(tmp_path, monkeypatch):
    """项目迁移按目录的推荐改写裸供应商：官方同步数据、用户修改的条目副本与用户添加的模型都装入之后才跑迁移（docs/adr/0130）。"""
    data_root = tmp_path / "data"
    DataRootLayout(data_root).projects_dir.mkdir(parents=True)
    events: list[str] = []

    def recording(name: str):
        async def _load(*_args, **_kwargs) -> None:
            events.append(name)

        return _load

    real_run_project_migrations = app_module.run_project_migrations

    def run_project_migrations(*args, **kwargs):
        events.append("project-migrations")
        return real_run_project_migrations(*args, **kwargs)

    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    monkeypatch.setattr("lib.project.project_manager.get_project_manager", lambda: ProjectManager(data_root))
    monkeypatch.setattr("lib.catalog.official_sync.load_synced_data", recording("synced-data"))
    monkeypatch.setattr("lib.catalog.user_entries.reload_user_entries", recording("user-entries"))
    monkeypatch.setattr("server.routers.provider_models.reload_user_added_models", recording("user-added-models"))
    monkeypatch.setattr(app_module, "run_project_migrations", run_project_migrations)
    stub_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "migrate_local_transcripts_to_store", _noop_async)

    app = app_module.app
    app.state = SimpleNamespace()

    async with app_module.lifespan(app):
        pass

    # 三层按叠加顺序装入（官方数据 → 用户修改的条目 → 用户添加的模型），迁移最后跑
    assert events == ["synced-data", "user-entries", "user-added-models", "project-migrations"]


@pytest.mark.asyncio
async def test_startup_leaves_a_project_older_than_the_minimum_schema_untouched(tmp_path, monkeypatch):
    """早于最低版本的项目：源文件编码迁移与 schema 迁移都不碰它，只在项目旁写下「版本过旧」的裁决。"""
    data_root = tmp_path / "data"
    project_dir = DataRootLayout(data_root).projects_dir / "old"
    (project_dir / "source").mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"schema_version": 18, "name": "old"}), encoding="utf-8")
    (project_dir / "source" / "novel.txt").write_bytes("春天来了".encode("gbk"))
    before = {
        path.relative_to(project_dir).as_posix(): path.read_bytes() for path in project_dir.rglob("*") if path.is_file()
    }

    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    monkeypatch.setattr("lib.project.project_manager.get_project_manager", lambda: ProjectManager(data_root))
    stub_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "migrate_local_transcripts_to_store", _noop_async)

    app = app_module.app
    app.state = SimpleNamespace()

    async with app_module.lifespan(app):
        pass

    after = {path: project_dir.joinpath(path).read_bytes() for path in before}
    assert after == before
    assert not (project_dir / ".arcreel").exists()
    assert not (project_dir / "source" / "raw").exists()
    verdict = json.loads((project_dir / MIGRATION_FAILURE_FILENAME).read_text(encoding="utf-8"))
    assert verdict["code"] == SCHEMA_UNSUPPORTED_CODE


@pytest.fixture
def fresh_startup_state(monkeypatch):
    """全新安装的启动状态：不带签名密钥与管理员密码，开文件日志；结束后摘掉本用例挂的 file handler。"""
    import logging

    import server.auth as auth_module
    from lib.infra import app_data_dir

    monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("ARCREEL_LOG_FILE_DISABLED", raising=False)
    # 先前用例的 lifespan 可能已挂上指向别处的 file handler；挂载幂等，留着它本用例就不会再挂。
    root = logging.getLogger()
    before = list(root.handlers)
    for handler in before:
        if isinstance(handler, TimedRotatingFileHandler):
            root.removeHandler(handler)
    auth_module.reset_token_secret_for_tests()
    app_data_dir.reset_for_tests()
    yield
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()
    root.handlers[:] = before
    auth_module.reset_token_secret_for_tests()
    app_data_dir.reset_for_tests()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fresh_startup_state")
async def test_fresh_empty_data_root_starts_cleanly(tmp_path, monkeypatch, file_db_factory):
    """不存在的数据根上首次启动：写出签名密钥与初始管理员密码、建出默认管理员，日志写到数据根的 logs/ 下。"""
    import logging

    import server.auth as auth_module
    from lib.db.repositories.user_repo import UserRepository

    data_root = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    monkeypatch.setattr("lib.project.project_manager.get_project_manager", lambda: ProjectManager(data_root))
    stub_lifespan_dependencies(monkeypatch, keep_bootstrap_admin=True)
    monkeypatch.setattr(app_module, "async_session_factory", file_db_factory)
    monkeypatch.setattr(app_module, "migrate_local_transcripts_to_store", _noop_async)

    app = app_module.app
    app.state = SimpleNamespace()
    async with app_module.lifespan(app):
        logging.getLogger("test.fresh_start").warning("fresh-start-marker")

    layout = DataRootLayout(data_root.resolve())
    assert layout.auth_token_secret_path.read_text(encoding="utf-8").strip() == auth_module.get_token_secret()
    assert layout.initial_admin_password_path.read_text(encoding="utf-8").strip()
    async with file_db_factory() as session:
        assert await UserRepository(session).any_with_password()
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "fresh-start-marker" in (layout.log_dir / "arcreel.log").read_text(encoding="utf-8")
