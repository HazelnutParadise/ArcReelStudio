"""账号服务：默认管理员初始化、登录校验、成员管理规则与令牌失效，用真实库。"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.user_repo import UserRepository
from lib.infra.api_errors import ApiError
from server.services import accounts


async def _bootstrap(db_factory: async_sessionmaker[AsyncSession], tmp_path: Path) -> Path:
    password_file = tmp_path / "runtime" / "initial-admin-password"
    await accounts.bootstrap_admin(db_factory, initial_password_path=password_file)
    return password_file


async def _authenticate(db_factory: async_sessionmaker[AsyncSession], username: str, password: str):
    async with db_factory() as session:
        return await accounts.authenticate(session, username, password)


async def test_bootstrap_uses_the_configured_admin_credentials(db_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "Boss")
    monkeypatch.setenv("AUTH_PASSWORD", "configured-pass")

    password_file = await _bootstrap(db_factory, tmp_path)

    user = await _authenticate(db_factory, "boss", "configured-pass")
    assert user is not None
    assert (user.id, user.username, user.role) == (DEFAULT_USER_ID, "boss", "admin")
    assert not password_file.exists()


async def test_bootstrap_without_a_password_writes_an_owner_only_initial_password(db_factory, tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)

    password_file = await _bootstrap(db_factory, tmp_path)

    generated = password_file.read_text(encoding="utf-8").strip()
    assert len(generated) >= 16
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    assert await _authenticate(db_factory, "admin", generated) is not None


async def test_bootstrap_runs_once_and_later_env_changes_do_not_reset_the_admin(db_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "first-password")
    await _bootstrap(db_factory, tmp_path)
    monkeypatch.setenv("AUTH_PASSWORD", "second-password")

    await _bootstrap(db_factory, tmp_path)

    assert await _authenticate(db_factory, "admin", "first-password") is not None
    assert await _authenticate(db_factory, "admin", "second-password") is None


async def test_authentication_rejects_wrong_unknown_and_disabled_accounts(db_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "admin-password")
    await _bootstrap(db_factory, tmp_path)
    async with db_factory() as session, session.begin():
        member = await accounts.create_account(session, username="Editor", password="editor-pass", role="user")
        await accounts.update_account(session, actor_id=DEFAULT_USER_ID, user_id=member.id, is_active=False)

    assert await _authenticate(db_factory, "admin", "wrong-password") is None
    assert await _authenticate(db_factory, "nobody", "admin-password") is None
    assert await _authenticate(db_factory, "editor", "editor-pass") is None
    assert await _authenticate(db_factory, "ADMIN", "admin-password") is not None


@pytest.mark.parametrize(
    ("username", "password", "key"),
    [
        ("has space", "long-enough", "username_invalid"),
        ("", "long-enough", "username_invalid"),
        ("member", "short", "password_too_short"),
    ],
)
async def test_creating_an_account_validates_username_and_password(db_factory, username, password, key):
    async with db_factory() as session, session.begin():
        with pytest.raises(ApiError) as caught:
            await accounts.create_account(session, username=username, password=password, role="user")
    assert caught.value.key == key


async def test_usernames_are_unique_regardless_of_case(db_factory):
    async with db_factory() as session, session.begin():
        await accounts.create_account(session, username="member", password="member-pass", role="user")
        with pytest.raises(ApiError) as caught:
            await accounts.create_account(session, username="MEMBER", password="member-pass", role="user")
    assert caught.value.key == "username_exists"
    assert caught.value.status_code == 409


async def test_the_last_active_admin_cannot_be_demoted_or_disabled(db_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "admin-password")
    await _bootstrap(db_factory, tmp_path)
    async with db_factory() as session, session.begin():
        other = await accounts.create_account(session, username="second", password="second-pass", role="admin")
        await accounts.update_account(session, actor_id=other.id, user_id=DEFAULT_USER_ID, role="user")
        for change in ({"role": "user"}, {"is_active": False}):
            with pytest.raises(ApiError) as caught:
                await accounts.update_account(session, actor_id=DEFAULT_USER_ID, user_id=other.id, **change)
            assert caught.value.key == "last_admin_required"


async def test_admins_cannot_remove_their_own_admin_access(db_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "admin-password")
    await _bootstrap(db_factory, tmp_path)
    async with db_factory() as session, session.begin():
        await accounts.create_account(session, username="second", password="second-pass", role="admin")
        for change in ({"role": "user"}, {"is_active": False}):
            with pytest.raises(ApiError) as caught:
                await accounts.update_account(session, actor_id=DEFAULT_USER_ID, user_id=DEFAULT_USER_ID, **change)
            assert caught.value.key == "cannot_change_own_admin_access"


async def test_role_status_and_password_changes_invalidate_existing_sessions(db_factory):
    async with db_factory() as session, session.begin():
        admin = await accounts.create_account(session, username="root", password="root-pass1", role="admin")
        member = await accounts.create_account(session, username="member", password="member-pass", role="user")
        versions = [member.token_version]
        for change in ({"role": "admin"}, {"is_active": False}, {"is_active": True}, {"password": "new-member-pass"}):
            updated = await accounts.update_account(session, actor_id=admin.id, user_id=member.id, **change)
            versions.append(updated.token_version)
    assert versions == sorted(set(versions))
    assert len(versions) == 5
    assert await _authenticate(db_factory, "member", "new-member-pass") is not None


async def test_session_resolution_requires_an_active_account_with_the_current_version(db_factory):
    async with db_factory() as session, session.begin():
        admin = await accounts.create_account(session, username="root", password="root-pass1", role="admin")
        member = await accounts.create_account(session, username="member", password="member-pass", role="user")
        version = member.token_version
    async with db_factory() as session:
        assert (await accounts.resolve_session_user(session, member.id, version)) is not None
        assert await accounts.resolve_session_user(session, member.id, version + 1) is None
        assert await accounts.resolve_session_user(session, "missing", 0) is None
    async with db_factory() as session, session.begin():
        disabled = await accounts.update_account(session, actor_id=admin.id, user_id=member.id, is_active=False)
    async with db_factory() as session:
        assert await accounts.resolve_session_user(session, member.id, disabled.token_version) is None


async def test_changing_your_own_password_checks_the_current_one(db_factory, tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    password_file = await _bootstrap(db_factory, tmp_path)
    generated = password_file.read_text(encoding="utf-8").strip()

    async with db_factory() as session, session.begin():
        with pytest.raises(ApiError) as caught:
            await accounts.change_own_password(
                session,
                DEFAULT_USER_ID,
                current_password="wrong",
                new_password="brand-new-pass",
                initial_password_path=password_file,
            )
    assert caught.value.key == "current_password_incorrect"

    async with db_factory() as session, session.begin():
        await accounts.change_own_password(
            session,
            DEFAULT_USER_ID,
            current_password=generated,
            new_password="brand-new-pass",
            initial_password_path=password_file,
        )

    assert await _authenticate(db_factory, "admin", "brand-new-pass") is not None
    assert not password_file.exists()
    async with db_factory() as session:
        assert (await UserRepository(session).get(DEFAULT_USER_ID)).token_version > 0
