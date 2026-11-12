"""任务去重闸在整条迁移链上始终存在：升到 head、退回 base 再升回 head 都不丢。

``idx_tasks_dedupe_active`` 是带表达式键的 partial unique 索引：同一资源在排队或运行中时不能再起一个任务。
SQLAlchemy 反射不出它，autogenerate 也会略过它，SQLite 上走 batch 重建 ``tasks`` 的迁移若没用
``lib.db.migration_helpers.preserve_sqlite_indexes`` 就会把它静默丢掉。这条全链走查不依赖枚举具体迁移，
以后新增的迁移引入同类缺陷时也会红。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_DEDUPE_INDEX = "idx_tasks_dedupe_active"


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, Path]:
    """空构造的 Config（不读 alembic.ini，免得 fileConfig 重置日志），库位置经 ``DATABASE_URL`` 传给 ``env.py``。"""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = Config()
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return cfg, db_path


def _dedupe_index_sql(db_path: Path) -> str | None:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return conn.execute(
                sa.text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = :name"), {"name": _DEDUPE_INDEX}
            ).scalar()
    finally:
        engine.dispose()


def _assert_dedupe_index(db_path: Path) -> None:
    sql = _dedupe_index_sql(db_path)
    assert sql is not None, f"{_DEDUPE_INDEX} 不见了"
    assert sql.startswith("CREATE UNIQUE INDEX")
    assert "COALESCE(script_file, '')" in sql
    assert "COALESCE(resource_type, '')" in sql
    assert "WHERE status IN ('queued', 'running')" in sql


def test_head_has_the_task_dedupe_index(alembic_cfg: tuple[Config, Path]) -> None:
    cfg, db_path = alembic_cfg

    command.upgrade(cfg, "head")

    _assert_dedupe_index(db_path)


def test_the_task_dedupe_index_survives_a_full_downgrade_and_upgrade(alembic_cfg: tuple[Config, Path]) -> None:
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "base")
    assert _dedupe_index_sql(db_path) is None
    command.upgrade(cfg, "head")

    _assert_dedupe_index(db_path)
