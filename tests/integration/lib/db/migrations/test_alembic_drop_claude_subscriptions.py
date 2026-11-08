"""Alembic 迁移：删掉 Claude 订阅令牌表（订阅改成连线），降级时重建。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command


def _tables(db_path: Path) -> list[str]:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        return sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_upgrade_drops_the_table_and_downgrade_recreates_it(
    alembic_cfg: tuple[Config, Path], migration_revisions: Callable[[str], tuple[str, str]]
):
    cfg, db_path = alembic_cfg
    revision, parent = migration_revisions("*_drop_claude_subscriptions.py")

    command.upgrade(cfg, parent)
    assert "claude_subscriptions" in _tables(db_path)

    command.upgrade(cfg, revision)
    assert "claude_subscriptions" not in _tables(db_path)

    command.downgrade(cfg, parent)
    assert "claude_subscriptions" in _tables(db_path)
