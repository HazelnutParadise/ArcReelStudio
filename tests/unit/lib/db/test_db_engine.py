"""Tests for lib.db.engine configuration."""

from pathlib import Path

import pytest

from lib.db.engine import get_database_url, is_sqlite_backend
from lib.infra.app_data_dir import reset_for_tests


@pytest.fixture
def default_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """未设置 ``DATABASE_URL``、数据根指向临时目录；返回数据根。"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    reset_for_tests()
    return data_root


def _sqlite_file(url: str) -> Path:
    prefix = "sqlite+aiosqlite:///"
    assert url.startswith(prefix)
    return Path(url.removeprefix(prefix))


class TestGetDatabaseUrl:
    def test_default_returns_sqlite_inside_data_root(self, default_sqlite: Path):
        assert _sqlite_file(get_database_url()) == default_sqlite.resolve() / "arcreel.db"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
        assert get_database_url() == "postgresql+asyncpg://localhost/test"


class TestIsSqliteBackend:
    def test_sqlite(self, default_sqlite: Path):
        assert is_sqlite_backend() is True

    def test_postgresql(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
        assert is_sqlite_backend() is False
