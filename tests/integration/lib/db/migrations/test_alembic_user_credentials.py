"""Alembic 迁移：users 表加登录凭据列的 upgrade / downgrade，默认管理员行保留。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command

_MIGRATION = "*_add_user_credentials.py"


def _columns(engine: sa.Engine) -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(sa.text("PRAGMA table_info(users)")).fetchall()
    return {row[1] for row in rows}


def test_upgrade_adds_credentials_and_keeps_the_default_admin(
    alembic_cfg: tuple[Config, Path], migration_revisions: Callable[[str], tuple[str, str]]
):
    revision_id, parent_id = migration_revisions(_MIGRATION)
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, parent_id)
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        assert "password_hash" not in _columns(engine)

        command.upgrade(cfg, revision_id)

        assert {"password_hash", "token_version"} <= _columns(engine)
        with engine.begin() as conn:
            row = conn.execute(
                sa.text("SELECT username, role, password_hash, token_version FROM users WHERE id = 'default'")
            ).one()
        assert tuple(row) == ("admin", "admin", None, 0)

        command.downgrade(cfg, parent_id)

        assert not {"password_hash", "token_version"} & _columns(engine)
    finally:
        engine.dispose()
