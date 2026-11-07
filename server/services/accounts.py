"""工作区账号：默认管理员初始化、登录校验、成员管理与令牌失效。

账号存在 ``users`` 表。所有登录的成员共用同一个工作区（项目、供应商凭据、设置）；``admin`` 另外可以
管理成员。``AUTH_USERNAME`` / ``AUTH_PASSWORD`` 只在库里还没有任何可登录账号时用来初始化默认管理员
（``id = default``），之后改密码、加成员都在界面或 ``scripts/manage_users.py`` 中进行，不再读写 ``.env``。
未设置 ``AUTH_PASSWORD`` 时生成随机密码，写入数据根下仅属主可读的文件，管理员改密码后删除该文件。

改密码、停用或改角色时 ``token_version`` 加一；会话令牌带着签发时的版本，版本不一致即失效。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import string
from pathlib import Path

from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.db.base import DEFAULT_USER_ID
from lib.db.models.user import USER_ROLES, User
from lib.db.repositories.user_repo import UserRepository
from lib.infra.api_errors import BadRequestError, ConflictError, NotFoundError

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")
_DEFAULT_ADMIN_USERNAME = "admin"
_GENERATED_PASSWORD_LENGTH = 20

_password_hash = PasswordHash.recommended()
# 账号不存在时也做一次同等代价的校验，响应时间不泄露用户名是否存在。
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))


def normalize_username(raw: str) -> str:
    """去掉首尾空白并转成小写；不符合规则时抛 ``username_invalid``。"""
    username = raw.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(username):
        raise BadRequestError("username_invalid")
    return username


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BadRequestError("password_too_short", min=MIN_PASSWORD_LENGTH)


def _validate_role(role: str) -> None:
    if role not in USER_ROLES:
        raise BadRequestError("user_role_invalid", role=role)


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(_GENERATED_PASSWORD_LENGTH))


def _write_owner_only(path: Path, content: str) -> None:
    """先写同目录临时文件（创建即 0600）再换入，中途失败不留下半个文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)  # hard-delete: infra -- 写入失败的初始密码临时文件
        raise


def _discard_initial_password(path: Path) -> None:
    path.unlink(missing_ok=True)  # hard-delete: infra -- 默认管理员已改密码，初始密码作废


async def bootstrap_admin(session_factory: async_sessionmaker[AsyncSession], *, initial_password_path: Path) -> None:
    """库里还没有任何可登录账号时，按 ``AUTH_USERNAME`` / ``AUTH_PASSWORD`` 初始化默认管理员。

    已有可登录账号时什么都不做，之后修改这两个变量不会重置密码。
    """
    raw_username = os.environ.get("AUTH_USERNAME", "").strip() or _DEFAULT_ADMIN_USERNAME
    try:
        username = normalize_username(raw_username)
    except BadRequestError:
        logger.warning("AUTH_USERNAME 不是有效的用户名，默认管理员改用 %s", _DEFAULT_ADMIN_USERNAME)
        username = _DEFAULT_ADMIN_USERNAME
    configured = os.environ.get("AUTH_PASSWORD", "")
    password = configured or _generate_password()

    async with session_factory() as session, session.begin():
        repo = UserRepository(session)
        if await repo.any_with_password():
            return
        password_hash = _password_hash.hash(password)
        admin = await repo.get(DEFAULT_USER_ID)
        if admin is None:
            await repo.create(username=username, password_hash=password_hash, role="admin", user_id=DEFAULT_USER_ID)
        else:
            admin.username = username
            admin.role = "admin"
            admin.is_active = True
            # 此前没有可登录账号，也就没有要作废的登录，令牌版本不变
            admin.password_hash = password_hash

    if configured:
        logger.info("已按 AUTH_USERNAME / AUTH_PASSWORD 初始化默认管理员 %s", username)
        return
    await asyncio.to_thread(_write_owner_only, initial_password_path, password)
    logger.warning(
        "未设置 AUTH_PASSWORD，已为默认管理员 %s 生成初始密码，保存在 %s；登录后请在「设置 › 账号与成员」中修改密码",
        username,
        initial_password_path,
    )


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    """校验用户名与密码；账号不存在、未设密码或已停用时返回 None。"""
    try:
        normalized = normalize_username(username)
    except BadRequestError:
        normalized = None
    user = await UserRepository(session).get_by_username(normalized) if normalized else None
    if user is None or user.password_hash is None or not user.is_active:
        _password_hash.verify(password, _DUMMY_HASH)
        return None
    return user if _password_hash.verify(password, user.password_hash) else None


async def resolve_session_user(session: AsyncSession, user_id: str, token_version: int) -> User | None:
    """会话令牌对应的账号：存在、启用且令牌版本一致才返回。"""
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        return None
    return user


async def list_accounts(session: AsyncSession) -> list[User]:
    return await UserRepository(session).list_all()


async def create_account(session: AsyncSession, *, username: str, password: str, role: str) -> User:
    normalized = normalize_username(username)
    _validate_password(password)
    _validate_role(role)
    repo = UserRepository(session)
    if await repo.get_by_username(normalized) is not None:
        raise ConflictError("username_exists", username=normalized)
    return await repo.create(username=normalized, password_hash=_password_hash.hash(password), role=role)


async def update_account(
    session: AsyncSession,
    *,
    actor_id: str,
    user_id: str,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
    initial_password_path: Path | None = None,
) -> User:
    """管理员修改成员的角色、启用状态或重设密码；任一项改动都会让该成员现有的登录失效。"""
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user_not_found", user_id=user_id)
    if role is not None:
        _validate_role(role)
    if password is not None:
        _validate_password(password)

    loses_admin = user.role == "admin" and user.is_active and (role == "user" or is_active is False)
    if loses_admin:
        if user.id == actor_id:
            raise BadRequestError("cannot_change_own_admin_access")
        if await repo.count_active_admins() <= 1:
            raise ConflictError("last_admin_required")

    changed = False
    if role is not None and role != user.role:
        user.role = role
        changed = True
    if is_active is not None and is_active != user.is_active:
        user.is_active = is_active
        changed = True
    if password is not None:
        user.password_hash = _password_hash.hash(password)
        changed = True
        if user.id == DEFAULT_USER_ID and initial_password_path is not None:
            await asyncio.to_thread(_discard_initial_password, initial_password_path)
    if changed:
        user.token_version += 1
    await session.flush()
    return user


async def change_own_password(
    session: AsyncSession,
    user_id: str,
    *,
    current_password: str,
    new_password: str,
    initial_password_path: Path | None = None,
) -> User:
    """成员修改自己的密码：须提供当前密码；成功后其他设备上的登录随之失效。"""
    user = await UserRepository(session).get(user_id)
    if user is None or user.password_hash is None or not _password_hash.verify(current_password, user.password_hash):
        raise BadRequestError("current_password_incorrect")
    _validate_password(new_password)
    user.password_hash = _password_hash.hash(new_password)
    user.token_version += 1
    await session.flush()
    if user.id == DEFAULT_USER_ID and initial_password_path is not None:
        await asyncio.to_thread(_discard_initial_password, initial_password_path)
    return user
