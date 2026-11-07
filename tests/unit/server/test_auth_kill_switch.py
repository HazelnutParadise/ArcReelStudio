"""AUTH_ENABLED kill-switch behavior tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import server.auth as auth_module


@pytest.fixture(autouse=True)
def isolated_auth_env():
    """Clear the cached token secret per-test so env tweaks take effect."""
    auth_module._cached_token_secret = None
    yield
    auth_module._cached_token_secret = None


class TestIsAuthEnabled:
    """``is_auth_enabled()`` 解析 AUTH_ENABLED env 值。"""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, True),  # 未设置 → 默认开启（向后兼容）
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("anything-else", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("", True),  # 空串视为未配置 → 回退默认（开启），fail-closed
            ("  ", True),  # 仅空白同上
            ("  false  ", False),
        ],
    )
    def test_env_value_resolution(self, raw, expected):
        env = os.environ.copy()
        env.pop("AUTH_ENABLED", None)
        if raw is not None:
            env["AUTH_ENABLED"] = raw
        with patch.dict(os.environ, env, clear=True):
            assert auth_module.is_auth_enabled() is expected


class TestVerifyDownloadTokenKillSwitch:
    def test_disabled_returns_fake_payload_without_verifying(self):
        with patch.dict(os.environ, {"AUTH_ENABLED": "false"}):
            payload = auth_module.verify_download_token("invalid-garbage", "myproject")
        assert payload["project"] == "myproject"
        assert payload["purpose"] == "download"
        assert payload["sub"] == "local"

    def test_enabled_rejects_invalid_token(self):
        env = {
            "AUTH_ENABLED": "true",
            "AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes",
        }
        with patch.dict(os.environ, env):
            import jwt

            with pytest.raises(jwt.InvalidTokenError):
                auth_module.verify_download_token("not-a-jwt", "myproject")


class TestGetCurrentUserKillSwitch:
    """这些 dep 函数是 async；用 asyncio.run 直接调用。"""

    @pytest.mark.asyncio
    async def test_disabled_returns_anonymous_admin_without_token(self):
        with patch.dict(os.environ, {"AUTH_ENABLED": "false"}):
            user = await auth_module.get_current_user(token=None)
        assert user.role == "admin"
        assert user.sub == "local"

    @pytest.mark.asyncio
    async def test_disabled_returns_anonymous_admin_even_with_invalid_token(self):
        with patch.dict(os.environ, {"AUTH_ENABLED": "false"}):
            user = await auth_module.get_current_user(token="anything-goes")
        assert user.sub == "local"

    @pytest.mark.asyncio
    async def test_enabled_without_token_raises_401(self):
        env = os.environ.copy()
        env.pop("AUTH_ENABLED", None)
        env["AUTH_TOKEN_SECRET"] = "test-secret-key-that-is-at-least-32-bytes"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                await auth_module.get_current_user(token=None)
            assert exc_info.value.status_code == 401


class TestLoginRouteKillSwitch:
    @pytest.mark.asyncio
    async def test_disabled_login_succeeds_with_any_password(self):
        """端到端：AUTH_ENABLED=false 时 /auth/token 接受任意凭据。"""
        from fastapi.testclient import TestClient

        from server.app import app

        env = {"AUTH_ENABLED": "false"}
        with patch.dict(os.environ, env), TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/token",
                data={"username": "anyone", "password": "wrong"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]


class TestWarnIfAuthDisabled:
    def test_disabled_logs_warning(self, caplog):
        with patch.dict(os.environ, {"AUTH_ENABLED": "false"}), caplog.at_level("WARNING", logger="server.auth"):
            auth_module.warn_if_auth_disabled()
        records = [r for r in caplog.records if r.name == "server.auth" and "AUTH_ENABLED" in r.getMessage()]
        assert len(records) == 1
        assert records[0].levelname == "WARNING"

    def test_enabled_logs_nothing(self, caplog):
        with patch.dict(os.environ, {"AUTH_ENABLED": "true"}), caplog.at_level("DEBUG", logger="server.auth"):
            auth_module.warn_if_auth_disabled()
        assert not [r for r in caplog.records if "AUTH_ENABLED" in r.getMessage()]
