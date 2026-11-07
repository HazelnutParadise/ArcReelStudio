"""
认证核心模块

提供 JWT token 创建/验证与当前用户解析。账号与密码存在 ``users`` 表，登录校验与成员管理见
:mod:`server.services.accounts`。会话 token 带账号 id（``uid``）与签发时的令牌版本（``ver``），
每次请求都核对账号仍启用、版本未变；API Key（`arc-` 前缀的 Bearer token）按创建它的账号解析。

凭证只经 ``Authorization`` header 传递，不接受 query param 形态的会话凭证。
浏览器原生请求（``<img>`` / ``<video>`` src 与原生下载导航）带不了该 header：
- 导出下载端点使用短时效下载 token（``purpose=download``）作为 query param 唯一认证方式
- 静态媒体文件不要求认证
SSE 由前端以 fetch 带 header 消费，与普通受保护端点走同一依赖（见 ``docs/adr/0071``）。
"""

import hashlib
import logging
import os
import secrets
import time
from collections import OrderedDict
from datetime import UTC
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict

from lib.infra.api_errors import ApiError
from lib.infra.data_root_layout import DataRootLayout
from lib.project.project_change_hints import ProjectChangeActor, set_project_change_actor

logger = logging.getLogger(__name__)


class CurrentUserInfo(BaseModel):
    """Current authenticated user info."""

    id: str
    sub: str
    role: str = "admin"
    # 账号的用户名；API Key 调用时 ``sub`` 是密钥标识，这里仍是持有者的用户名。内嵌 Agent 与匿名用户为空。
    username: str | None = None

    model_config = ConfigDict(frozen=True)


# JWT 签名密钥缓存
_cached_token_secret: str | None = None

# Token 有效期：7 天
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# 关闭认证时返回的匿名用户标识
_ANONYMOUS_USER_SUB = "local"

# 视为"关闭认证"的 env 取值。空串不在内 —— .env 误写 `AUTH_ENABLED=` 应回退到默认（开启），
# 避免静默 fail-open。
_AUTH_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})


def is_auth_enabled() -> bool:
    """``AUTH_ENABLED`` env 解析。默认 ``true``，保持现有部署行为；空值也按默认。

    ``false`` / ``0`` / ``no`` / ``off`` 一律视为关闭（不区分大小写）。
    """
    return os.environ.get("AUTH_ENABLED", "true").strip().lower() not in _AUTH_DISABLED_VALUES


def warn_if_auth_disabled() -> None:
    """认证关闭时输出一条 WARNING，提示全部管理接口无需认证。"""
    if is_auth_enabled():
        return
    logger.warning(
        "AUTH_ENABLED=false：全部管理接口无需认证即可访问。"
        "该模式仅适用于受独立网络边界保护的本机环境，远程部署请保持认证开启"
    )


def _anonymous_user() -> CurrentUserInfo:
    """关闭认证时返回的固定匿名用户。"""
    from lib.db.base import DEFAULT_USER_ID

    return CurrentUserInfo(id=DEFAULT_USER_ID, sub=_ANONYMOUS_USER_SUB, role="admin")


# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_token_secret() -> str:
    """获取 JWT 签名密钥

    显式设置的非空 ``AUTH_TOKEN_SECRET`` 优先；未设置时使用数据目录里持久化的密钥，
    首次使用时生成，重启后沿用，已登录会话不因重启失效。
    """
    global _cached_token_secret

    env_secret = os.environ.get("AUTH_TOKEN_SECRET")
    if env_secret:
        return env_secret

    if _cached_token_secret is None:
        _cached_token_secret = _load_or_create_persisted_token_secret()
    return _cached_token_secret


def reset_token_secret_for_tests() -> None:
    """清掉进程内缓存的签名密钥，模拟进程重启。"""
    global _cached_token_secret
    _cached_token_secret = None


def ensure_token_secret() -> None:
    """启动时预先解析签名密钥，请求路径上不再读写密钥文件。"""
    get_token_secret()


def _load_or_create_persisted_token_secret() -> str:
    """读取数据目录里的签名密钥，不存在则生成并以 0600 写入。

    读写失败时退回进程内随机密钥，不阻断启动；此时重启后已登录会话失效。
    """
    path = DataRootLayout.current().auth_token_secret_path
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    except OSError:
        logger.warning("无法读取 JWT 签名密钥文件 %s，本次启动改用临时密钥；请修复后重启或设置 AUTH_TOKEN_SECRET", path)
        return secrets.token_hex(32)

    if existing:
        return existing

    secret = secrets.token_hex(32)
    try:
        _write_owner_only(path, secret)
    except OSError:
        logger.warning(
            "无法写入 JWT 签名密钥文件 %s，本次启动改用临时密钥，重启后需重新登录；请检查数据目录权限或设置 AUTH_TOKEN_SECRET",
            path,
        )
        return secret
    logger.info("未设置 AUTH_TOKEN_SECRET，已生成 JWT 签名密钥并保存到 %s", path)
    return secret


def _write_owner_only(path: Path, content: str) -> None:
    """先写同目录临时文件（创建即 0600）再换入，中途失败不留下半个密钥文件。"""
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
        tmp.unlink(missing_ok=True)  # hard-delete: infra -- 写入失败的签名密钥临时文件
        raise


def create_token(
    username: str,
    *,
    user_id: str | None = None,
    token_version: int = 0,
    expiry_seconds: int = TOKEN_EXPIRY_SECONDS,
) -> str:
    """创建 JWT token

    Args:
        username: 用户名，写入 ``sub``
        user_id: 账号 id；会话 token 必须给出，不带账号的 token 只有内嵌 Agent 的会被接受
        token_version: 签发时账号的令牌版本，账号改密码、停用或改角色后旧 token 失效
        expiry_seconds: token 有效秒数；网页登录沿用 7 天，内嵌 Agent 使用短时效。

    Returns:
        JWT token 字符串
    """
    now = time.time()
    payload: dict[str, object] = {
        "sub": username,
        "iat": now,
        "exp": now + expiry_seconds,
    }
    if user_id is not None:
        payload["uid"] = user_id
        payload["ver"] = token_version
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """验证会话 JWT token

    带 ``purpose`` 声明的 token（如下载 token）只供对应端点自行校验，不作为会话凭据。

    Args:
        token: JWT token 字符串

    Returns:
        成功返回 payload dict，失败返回 None
    """
    try:
        payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError, jwt.ExpiredSignatureError:
        return None
    if "purpose" in payload:
        return None
    return payload


DOWNLOAD_TOKEN_EXPIRY_SECONDS = 300  # 5 分钟


def create_download_token(username: str, project_name: str) -> str:
    """签发短时效下载 token，用于浏览器原生下载认证"""
    now = time.time()
    payload = {
        "sub": username,
        "project": project_name,
        "purpose": "download",
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_download_token(token: str, project_name: str) -> dict:
    """验证下载 token

    Returns:
        成功返回 payload dict

    Raises:
        jwt.ExpiredSignatureError: token 已过期
        jwt.InvalidTokenError: token 无效
        ValueError: purpose 或 project 不匹配
    """
    if not is_auth_enabled():
        return {
            "sub": _ANONYMOUS_USER_SUB,
            "project": project_name,
            "purpose": "download",
        }
    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "download":
        raise ValueError("token purpose 不匹配")
    if payload.get("project") != project_name:
        raise ValueError("token project 不匹配")
    return payload


# ---------------------------------------------------------------------------
# API Key 认证支持
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "arc-"
API_KEY_CACHE_TTL = 300  # 5 分钟

# LRU 缓存：key_hash → (payload_dict | None, expires_at_timestamp)
# payload 为 None 表示 key 不存在或已过期（负缓存）
# 使用 OrderedDict 实现 LRU：命中时 move_to_end，淘汰时 popitem(last=False)
_api_key_cache: OrderedDict[str, tuple[dict | None, float]] = OrderedDict()
_API_KEY_CACHE_MAX = 512


def hash_api_key(key: str) -> str:
    """计算 API Key 的 SHA-256 哈希。"""
    return hashlib.sha256(key.encode()).hexdigest()


def invalidate_api_key_cache(key_hash: str) -> None:
    """立即清除指定 key_hash 的缓存条目（key 删除时调用）。"""
    _api_key_cache.pop(key_hash, None)


def _get_cached_api_key_payload(key_hash: str) -> tuple[bool, dict | None]:
    """从缓存中查找。返回 (命中, payload 或 None)。命中时将条目移至末尾（LRU）。"""
    entry = _api_key_cache.get(key_hash)
    if entry is None:
        return False, None
    payload, expiry = entry
    if time.monotonic() > expiry:
        _api_key_cache.pop(key_hash, None)
        return False, None
    _api_key_cache.move_to_end(key_hash)
    return True, payload


def _set_api_key_cache(key_hash: str, payload: dict | None, expires_at_ts: float | None = None) -> None:
    """写入缓存（含 LRU 淘汰）。

    正向缓存（payload 非 None）TTL 以 key 实际过期时间为上界，
    避免 key 过期后仍在缓存中通过验证的安全问题。
    """
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX:
        # 淘汰最久未使用的条目（LRU：OrderedDict 头部）
        _api_key_cache.popitem(last=False)
    ttl = API_KEY_CACHE_TTL
    if payload is not None and expires_at_ts is not None:
        time_to_expiry = expires_at_ts - time.monotonic()
        if time_to_expiry <= 0:
            # key 已过期，写入负缓存
            _api_key_cache[key_hash] = (None, time.monotonic() + API_KEY_CACHE_TTL)
            return
        ttl = min(ttl, time_to_expiry)
    _api_key_cache[key_hash] = (payload, time.monotonic() + ttl)


async def verify_api_key(token: str) -> dict | None:
    """验证 API Key token，返回 payload dict 或 None（失败/过期/不存在）。

    内部先查缓存，缓存未命中再查数据库。
    查库成功后更新 last_used_at（后台异步，不阻塞响应）。
    """
    key_hash = hash_api_key(token)

    # 缓存查询
    hit, cached_payload = _get_cached_api_key_payload(key_hash)
    if hit:
        return cached_payload

    # 数据库查询
    from lib.db import async_session_factory
    from lib.db.repositories.api_key_repository import ApiKeyRepository

    async with async_session_factory() as session, session.begin():
        repo = ApiKeyRepository(session)
        row = await repo.get_by_hash(key_hash)

    if row is None:
        _set_api_key_cache(key_hash, None)
        return None

    # 检查过期
    expires_at = row.get("expires_at")
    expires_at_monotonic: float | None = None
    if expires_at:
        from datetime import datetime

        try:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) >= exp_dt:
                _set_api_key_cache(key_hash, None)
                return None
            # 将过期时刻转换为 monotonic 时间戳，供缓存 TTL 上界计算
            remaining_secs = (exp_dt - datetime.now(UTC)).total_seconds()
            expires_at_monotonic = time.monotonic() + remaining_secs
        except ValueError, TypeError:
            logger.warning("API Key expires_at 值格式无法解析，忽略过期检查: %r", expires_at)

    payload = {"sub": f"apikey:{row['name']}", "via": "apikey", "uid": row["user_id"]}
    _set_api_key_cache(key_hash, payload, expires_at_ts=expires_at_monotonic)

    # 异步更新 last_used_at（不阻塞，保存引用防止 GC）
    import asyncio

    async def _touch():
        try:
            async with async_session_factory() as s, s.begin():
                await ApiKeyRepository(s).touch_last_used(key_hash)
        except Exception:
            logger.exception("更新 API Key last_used_at 失败（非致命）")

    _touch_task = asyncio.create_task(_touch())
    _touch_task.add_done_callback(lambda _: None)  # suppress "never retrieved" warning

    return payload


async def verify_active_api_key(token: str) -> dict | None:
    """验证 API Key，并确认它所属的账号仍存在且启用；远程 MCP 等不经 ``get_current_user`` 的入口用它。

    ``verify_api_key`` 的缓存只记 key 本身，账号状态每次都查库，停用成员后立即生效。
    """
    payload = await verify_api_key(token)
    if payload is None:
        return None
    uid = payload.get("uid")
    if not isinstance(uid, str):
        return None

    from lib.db import async_session_factory
    from lib.db.repositories.user_repo import UserRepository

    async with async_session_factory() as session:
        owner = await UserRepository(session).get(uid)
    return payload if owner is not None and owner.is_active else None


def _verify_and_get_payload(token: str) -> dict:
    """同步验证 JWT token 并在失败时抛出 401 异常。（仅用于 JWT 路径）"""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _verify_and_get_payload_async(token: str) -> dict:
    """异步验证 token，支持 API Key（arc- 前缀）和 JWT 两种模式。"""
    if token.startswith(API_KEY_PREFIX):
        payload = await verify_api_key(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="API Key 无效、已过期或不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    # JWT 路径
    return _verify_and_get_payload(token)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def _payload_to_user(payload: dict) -> CurrentUserInfo:
    """把已验签的 JWT / API Key payload 解析成当前账号；账号不存在、已停用或令牌版本过时即 401。"""
    from lib.db import async_session_factory
    from lib.db.base import DEFAULT_USER_ID
    from lib.db.repositories.user_repo import UserRepository
    from server.services.accounts import resolve_session_user

    sub = payload.get("sub", "")
    uid = payload.get("uid")
    if uid is None and sub == EMBEDDED_AGENT_SUB:
        # 内嵌 Agent 在共用工作区里代创作者调用本地接口，不具备成员管理权限。
        return CurrentUserInfo(id=DEFAULT_USER_ID, sub=sub, role="user")
    if not isinstance(uid, str):
        raise _unauthorized("token 无效或已过期")
    async with async_session_factory() as session:
        if payload.get("via") == "apikey":
            user = await UserRepository(session).get(uid)
            if user is not None and not user.is_active:
                user = None
        else:
            version = payload.get("ver")
            user = await resolve_session_user(session, uid, version) if isinstance(version, int) else None
    if user is None:
        raise _unauthorized("账号不存在、已停用，或登录已失效")
    return CurrentUserInfo(
        id=user.id,
        sub=sub if payload.get("via") == "apikey" else user.username,
        role=user.role,
        username=user.username,
    )


async def authenticate_bearer(token: str) -> CurrentUserInfo:
    """校验一个 Bearer 令牌（JWT 或 API Key）并解析出账号；无效、过期或账号已失效时抛 401。

    供不经依赖注入的入口（如 WebSocket）使用，与 :func:`get_current_user` 的校验一致。
    """
    return await _payload_to_user(await _verify_and_get_payload_async(token))


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
) -> CurrentUserInfo:
    """标准认证依赖 — 支持 JWT 和 API Key Bearer token。

    ``AUTH_ENABLED=false`` 时无视 token，直接返回匿名 admin。
    启用时缺 token 抛 401（与旧 oauth2_scheme auto_error 行为等价）。
    """
    if not is_auth_enabled():
        set_project_change_actor(None)
        return _anonymous_user()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="未认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(token)
    user = await _payload_to_user(payload)
    # 本次请求里的项目写入归到这位成员名下：事件流据此让其他成员看到是谁改的。
    actor: ProjectChangeActor | None = None
    if user.sub != EMBEDDED_AGENT_SUB and user.username:
        actor = {"user_id": user.id, "username": user.username}
    set_project_change_actor(actor)
    return user


# Type aliases for FastAPI dependency injection
CurrentUser = Annotated[CurrentUserInfo, Depends(get_current_user)]

#: 内嵌 Agent 调用本地服务所用令牌的 sub（见 ``server/agent_runtime/options_assembler.py``）。
EMBEDDED_AGENT_SUB = "embedded-agent"


async def require_admin(user: CurrentUser) -> CurrentUserInfo:
    """成员管理只属于管理员本人：拒绝非管理员、内嵌 Agent 与 API Key。"""
    if user.sub == EMBEDDED_AGENT_SUB or user.sub.startswith("apikey:"):
        raise ApiError("jwt_auth_required", status_code=403)
    if user.role != "admin":
        raise ApiError("admin_only_operation", status_code=403)
    return user


AdminUser = Annotated[CurrentUserInfo, Depends(require_admin)]


async def reject_embedded_agent(user: CurrentUser) -> None:
    """不可恢复的操作只属于创作者：拒绝内嵌 Agent 的令牌，Agent 在沙箱里直接调 HTTP 也绕不过。

    鉴权关闭时所有请求都是同一个匿名用户、调用方不可区分，这道检查随之失效，与其余身份限制相同。
    """
    if user.sub == EMBEDDED_AGENT_SUB:
        raise ApiError("creator_only_operation", status_code=403)
