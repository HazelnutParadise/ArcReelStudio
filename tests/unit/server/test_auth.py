"""
认证核心模块测试

测试 server.auth 中的 JWT token、签名密钥与当前账号解析。账号登录与成员管理见 tests/integration/server/services/test_accounts.py。
"""

import os
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import server.auth as auth_module


class TestTokenSecret:
    def setup_method(self):
        """每个测试前重置缓存"""
        auth_module._cached_token_secret = None

    def test_get_token_secret_from_env(self):
        """优先使用 AUTH_TOKEN_SECRET 环境变量"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "my-secret-key"}):
            secret = auth_module.get_token_secret()
            assert secret == "my-secret-key"

    def test_get_token_secret_auto_generate(self):
        """自动生成并缓存"""
        env = os.environ.copy()
        env.pop("AUTH_TOKEN_SECRET", None)
        with patch.dict(os.environ, env, clear=True):
            secret1 = auth_module.get_token_secret()
            assert secret1 is not None
            assert len(secret1) > 0

            # 再次调用应返回相同的缓存值
            secret2 = auth_module.get_token_secret()
            assert secret1 == secret2


def _simulate_restart() -> None:
    """进程重启：进程内缓存全部丢失，数据目录与 .env 保留。"""
    auth_module.reset_token_secret_for_tests()


class TestTokenSecretPersistence:
    """未设置 AUTH_TOKEN_SECRET 时签名密钥落在数据目录，重启后沿用。"""

    def setup_method(self):
        _simulate_restart()

    def teardown_method(self):
        _simulate_restart()

    @pytest.mark.parametrize("unset", ["missing", "empty"])
    def test_token_survives_restart_without_configured_secret(self, monkeypatch, unset):
        if unset == "missing":
            monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
        else:
            monkeypatch.setenv("AUTH_TOKEN_SECRET", "")
        token = auth_module.create_token("admin")

        _simulate_restart()

        payload = auth_module.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"

    def test_persisted_secret_file_is_owner_only(self, monkeypatch):
        from lib.infra.data_root_layout import DataRootLayout

        monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
        auth_module.ensure_token_secret()

        secret_path = DataRootLayout.current().auth_token_secret_path
        assert secret_path.read_text(encoding="utf-8").strip() == auth_module.get_token_secret()
        if os.name == "posix":
            assert secret_path.stat().st_mode & 0o777 == 0o600

    def test_existing_secret_file_is_reused(self, monkeypatch):
        from lib.infra.data_root_layout import DataRootLayout

        monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
        secret_path = DataRootLayout.current().auth_token_secret_path
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text("previously-persisted-secret\n", encoding="utf-8")

        assert auth_module.get_token_secret() == "previously-persisted-secret"

    def test_configured_secret_wins_over_persisted_file(self, monkeypatch):
        monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
        token_signed_with_persisted = auth_module.create_token("admin")

        _simulate_restart()
        monkeypatch.setenv("AUTH_TOKEN_SECRET", "explicit-secret-that-is-at-least-32-bytes")

        assert auth_module.get_token_secret() == "explicit-secret-that-is-at-least-32-bytes"
        assert auth_module.verify_token(token_signed_with_persisted) is None

    def test_unwritable_data_dir_falls_back_to_process_secret(self, monkeypatch, tmp_path, caplog):
        """数据目录写不进密钥时不阻断启动，退回进程内随机密钥（重启后需重新登录）。"""
        from lib.infra.app_data_dir import reset_for_tests

        monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
        data_root = tmp_path / "data-root"
        data_root.mkdir()
        (data_root / "runtime").write_text("", encoding="utf-8")  # runtime/ 建不出来
        monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
        reset_for_tests()

        with caplog.at_level("WARNING", logger=auth_module.__name__):
            secret = auth_module.get_token_secret()

        assert secret
        assert auth_module.get_token_secret() == secret
        assert any("AUTH_TOKEN_SECRET" in r.getMessage() for r in caplog.records)
        assert all(secret not in r.getMessage() for r in caplog.records)


class TestCreateAndVerifyToken:
    def setup_method(self):
        auth_module._cached_token_secret = None

    def test_create_and_verify_token(self):
        """创建后验证往返一致"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_token("admin")
            payload = auth_module.verify_token(token)
            assert payload is not None
            assert payload["sub"] == "admin"
            assert "iat" in payload
            assert "exp" in payload

    def test_create_token_accepts_a_shorter_expiry(self):
        """内嵌 Agent 可签发短时效会话 JWT，不改变网页登录默认时效。"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_token("embedded-agent", expiry_seconds=900)
            payload = auth_module.verify_token(token)

        assert payload is not None
        assert payload["exp"] - payload["iat"] == 900

    def test_verify_token_invalid(self):
        """无效 token 返回 None"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            result = auth_module.verify_token("this-is-not-a-valid-jwt")
            assert result is None

    def test_verify_token_expired(self):
        """过期 token 返回 None"""
        import jwt

        secret = "test-secret-key-that-is-at-least-32-bytes"
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": secret}):
            # 手动创建一个已过期的 token
            payload = {
                "sub": "admin",
                "iat": time.time() - 3600,
                "exp": time.time() - 1,  # 已过期
            }
            expired_token = jwt.encode(payload, secret, algorithm="HS256")
            result = auth_module.verify_token(expired_token)
            assert result is None

    @pytest.mark.parametrize("purpose", ["download", "other"])
    def test_verify_token_rejects_purpose_bound_token(self, purpose):
        """带 purpose 声明的 token（任意取值）不被会话校验接受"""
        import jwt

        secret = "test-secret-key-that-is-at-least-32-bytes"
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": secret}):
            payload = {"sub": "admin", "purpose": purpose, "iat": time.time(), "exp": time.time() + 300}
            token = jwt.encode(payload, secret, algorithm="HS256")
            assert auth_module.verify_token(token) is None

    def test_verify_token_accepts_session_token(self):
        """不带 purpose 的会话 token（登录与内嵌 Agent 均经 create_token 签发）照常通过"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            payload = auth_module.verify_token(auth_module.create_token("embedded-agent", expiry_seconds=60))
            assert payload is not None
            assert payload["sub"] == "embedded-agent"


class TestDownloadToken:
    def setup_method(self):
        auth_module._cached_token_secret = None

    def test_create_and_verify_download_token(self):
        """签发并验证下载 token"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_download_token("admin", "my-project")
            payload = auth_module.verify_download_token(token, "my-project")
            assert payload["sub"] == "admin"
            assert payload["project"] == "my-project"
            assert payload["purpose"] == "download"

    def test_verify_download_token_wrong_project(self):
        """项目不匹配应抛出 ValueError"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_download_token("admin", "project-a")
            import pytest

            with pytest.raises(ValueError, match="project 不匹配"):
                auth_module.verify_download_token(token, "project-b")

    def test_verify_download_token_expired(self):
        """过期 token 应抛出 ExpiredSignatureError"""
        import jwt

        secret = "test-secret-key-that-is-at-least-32-bytes"
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": secret}):
            payload = {
                "sub": "admin",
                "project": "demo",
                "purpose": "download",
                "iat": time.time() - 600,
                "exp": time.time() - 1,
            }
            expired_token = jwt.encode(payload, secret, algorithm="HS256")
            with pytest.raises(jwt.ExpiredSignatureError):
                auth_module.verify_download_token(expired_token, "demo")

    def test_verify_download_token_wrong_purpose(self):
        """purpose 不匹配应抛出 ValueError"""
        import jwt

        secret = "test-secret-key-that-is-at-least-32-bytes"
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": secret}):
            payload = {
                "sub": "admin",
                "project": "demo",
                "purpose": "other",
                "iat": time.time(),
                "exp": time.time() + 300,
            }
            token = jwt.encode(payload, secret, algorithm="HS256")
            with pytest.raises(ValueError, match="purpose 不匹配"):
                auth_module.verify_download_token(token, "demo")


class TestGetCurrentUser:
    """FastAPI 依赖函数测试"""

    def setup_method(self):
        auth_module._cached_token_secret = None

    async def test_get_current_user_valid_token(self):
        """会话 token 解析成库里的账号：用户名与角色取自账号，不取自 token。"""
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_token("someone-else", user_id="default", token_version=0)
            result = await auth_module.get_current_user(token)
            assert isinstance(result, auth_module.CurrentUserInfo)
            # 用户名取自库里的默认管理员（走 lifespan 的用例会按各自的 AUTH_USERNAME 重设它），不取 token 的 sub
            assert result.sub != "someone-else"
            assert result.id == "default"
            assert result.role == "admin"

    @pytest.mark.parametrize(
        "claims",
        [
            {},
            {"user_id": "missing-user"},
            {"user_id": "default", "token_version": 99},
        ],
        ids=["no-account", "unknown-account", "stale-version"],
    )
    async def test_get_current_user_rejects_tokens_without_a_current_account(self, claims):
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_token("admin", **claims)
            with pytest.raises(HTTPException) as exc_info:
                await auth_module.get_current_user(token)
        assert exc_info.value.status_code == 401

    async def test_embedded_agent_token_is_a_regular_member_without_an_account(self):
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            token = auth_module.create_token(auth_module.EMBEDDED_AGENT_SUB, expiry_seconds=900)
            result = await auth_module.get_current_user(token)
        assert (result.id, result.sub, result.role) == ("default", auth_module.EMBEDDED_AGENT_SUB, "user")

    async def test_get_current_user_invalid_token(self):

        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes"}):
            with pytest.raises(HTTPException) as exc_info:
                await auth_module.get_current_user("invalid-token")
            assert exc_info.value.status_code == 401
