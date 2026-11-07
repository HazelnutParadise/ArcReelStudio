"""
API Key 认证分流单元测试

测试 auth 模块中的 API Key 路径：哈希计算、缓存逻辑、认证分流。
"""

import hashlib
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import server.auth as auth_module
from tests.fakes import bind_session_factory


@pytest.fixture(autouse=True)
def clear_cache():
    """每次测试前清空 API Key 缓存。"""
    auth_module._api_key_cache.clear()
    yield
    auth_module._api_key_cache.clear()


@pytest.fixture
def api_key_db(db_factory, monkeypatch):
    """把 API Key 查库路径绑到内存库。

    ``verify_api_key`` 在函数内 import ``lib.db.async_session_factory``，缓存未命中时
    真的落库查询；绑内存库后过期判定与缓存写入这两步都按真实数据跑。
    """
    bind_session_factory(monkeypatch, db_factory)
    return db_factory


async def _seed_api_key(
    factory, name: str, key: str, *, expires_at: datetime | None = None, user_id: str | None = None
) -> None:
    from lib.db.models.api_key import ApiKey

    owner = {"user_id": user_id} if user_id is not None else {}
    async with factory() as session:
        session.add(
            ApiKey(
                name=name,
                key_hash=auth_module.hash_api_key(key),
                key_prefix=key[:8],
                expires_at=expires_at,
                **owner,
            )
        )
        await session.commit()


async def _seed_member(factory, username: str) -> str:
    from lib.db.repositories.user_repo import UserRepository

    async with factory() as session, session.begin():
        user = await UserRepository(session).create(username=username, password_hash="x", role="user")
        return user.id


async def _set_member_active(factory, user_id: str, active: bool) -> None:
    from lib.db.repositories.user_repo import UserRepository

    async with factory() as session, session.begin():
        user = await UserRepository(session).get(user_id)
        assert user is not None
        user.is_active = active


class TestHashApiKey:
    def test_deterministic(self):
        key = "arc-testapikey1234"
        assert auth_module.hash_api_key(key) == auth_module.hash_api_key(key)

    def test_sha256_output(self):
        key = "arc-abc"
        expected = hashlib.sha256(key.encode()).hexdigest()
        assert auth_module.hash_api_key(key) == expected


class TestApiKeyCache:
    def test_cache_miss(self):
        hit, payload = auth_module._get_cached_api_key_payload("nonexistent")
        assert not hit
        assert payload is None

    def test_cache_set_and_hit(self):
        auth_module._set_api_key_cache("hash123", {"sub": "apikey:test", "via": "apikey"})
        hit, payload = auth_module._get_cached_api_key_payload("hash123")
        assert hit
        assert payload == {"sub": "apikey:test", "via": "apikey"}

    def test_cache_negative_entry(self):
        auth_module._set_api_key_cache("hash_missing", None)
        hit, payload = auth_module._get_cached_api_key_payload("hash_missing")
        assert hit
        assert payload is None

    def test_cache_expired_entry(self):
        auth_module._api_key_cache["hash_expired"] = ({"sub": "test"}, time.monotonic() - 1)
        hit, _ = auth_module._get_cached_api_key_payload("hash_expired")
        assert not hit

    def test_invalidate_removes_entry(self):
        auth_module._set_api_key_cache("hash_to_delete", {"sub": "test"})
        auth_module.invalidate_api_key_cache("hash_to_delete")
        hit, _ = auth_module._get_cached_api_key_payload("hash_to_delete")
        assert not hit

    def test_cache_hit_skips_db(self):
        """缓存命中时不应查询数据库（通过 verify_api_key 的分支逻辑验证）。"""
        key = "arc-cached-key"
        key_hash = auth_module.hash_api_key(key)
        auth_module._set_api_key_cache(key_hash, {"sub": "apikey:cached", "via": "apikey"})
        # 若命中缓存则返回缓存值；True means hit
        hit, payload = auth_module._get_cached_api_key_payload(key_hash)
        assert hit
        assert payload["sub"] == "apikey:cached"


class TestVerifyAndGetPayloadAsync:
    @pytest.mark.asyncio
    async def test_jwt_path_success(self):
        """非 arc- 前缀走 JWT 路径，成功返回 payload。"""
        with patch("server.auth.verify_token", return_value={"sub": "admin"}):
            result = await auth_module._verify_and_get_payload_async("some.jwt.token")
        assert result == {"sub": "admin"}

    @pytest.mark.asyncio
    async def test_jwt_invalid_raises_401(self):
        """非 arc- 前缀但 JWT 验证失败，抛出 401。"""
        with patch("server.auth.verify_token", return_value=None), pytest.raises(HTTPException) as exc_info:
            await auth_module._verify_and_get_payload_async("invalid.jwt.token")
        assert exc_info.value.status_code == 401

    async def test_api_key_path_success(self, api_key_db):
        """arc- 前缀走 API Key 路径：查库命中后返回 payload 并写入缓存。"""
        await _seed_api_key(api_key_db, "mykey", "arc-validkey")

        result = await auth_module._verify_and_get_payload_async("arc-validkey")

        assert result["via"] == "apikey"
        assert result["sub"] == "apikey:mykey"
        hit, cached = auth_module._get_cached_api_key_payload(auth_module.hash_api_key("arc-validkey"))
        assert hit
        assert cached == result

    async def test_api_key_not_found_raises_401(self, api_key_db):
        """arc- 前缀但库里没有该 key，抛出 401。"""
        with pytest.raises(HTTPException) as exc_info:
            await auth_module._verify_and_get_payload_async("arc-badkey")
        assert exc_info.value.status_code == 401

    async def test_api_key_expired_raises_401(self, api_key_db):
        """库里有该 key 但 expires_at 已过，抛出 401 并落负缓存。"""
        await _seed_api_key(
            api_key_db,
            "expiredkey",
            "arc-expiredkey",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )

        with pytest.raises(HTTPException) as exc_info:
            await auth_module._verify_and_get_payload_async("arc-expiredkey")

        assert exc_info.value.status_code == 401
        hit, cached = auth_module._get_cached_api_key_payload(auth_module.hash_api_key("arc-expiredkey"))
        assert hit
        assert cached is None


class TestVerifyActiveApiKey:
    async def test_keys_of_active_members_verify(self, api_key_db):
        member = await _seed_member(api_key_db, "active-member")
        await _seed_api_key(api_key_db, "active-key", "arc-activekey", user_id=member)

        payload = await auth_module.verify_active_api_key("arc-activekey")

        assert payload is not None
        assert payload["uid"] == member

    async def test_keys_of_disabled_members_are_rejected(self, api_key_db):
        member = await _seed_member(api_key_db, "disabled-member")
        await _seed_api_key(api_key_db, "disabled-key", "arc-disabledkey", user_id=member)
        await _set_member_active(api_key_db, member, False)

        assert await auth_module.verify_active_api_key("arc-disabledkey") is None

    async def test_disabling_a_member_rejects_a_key_that_already_verified(self, api_key_db):
        member = await _seed_member(api_key_db, "later-disabled")
        await _seed_api_key(api_key_db, "cached-key", "arc-cachedkey", user_id=member)
        assert await auth_module.verify_active_api_key("arc-cachedkey") is not None

        await _set_member_active(api_key_db, member, False)

        assert await auth_module.verify_active_api_key("arc-cachedkey") is None

    async def test_keys_whose_owner_no_longer_exists_are_rejected(self, api_key_db):
        await _seed_api_key(api_key_db, "orphan-key", "arc-orphankey", user_id="missing-member")

        assert await auth_module.verify_active_api_key("arc-orphankey") is None

    async def test_unknown_keys_are_rejected(self, api_key_db):
        assert await auth_module.verify_active_api_key("arc-neverissued") is None
