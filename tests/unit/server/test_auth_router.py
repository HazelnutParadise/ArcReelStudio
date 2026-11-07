"""
登录 API 路由测试

测试 server.routers.auth 中的登录和 token 验证路由。
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.auth as auth_module
from server.routers import auth as auth_router
from tests.auth_deps import AUTH_DEPENDENCIES, seed_login_account


@pytest.fixture
def username() -> str:
    """全局测试库里能用 ``testpass`` 登录的账号。"""
    return seed_login_account("testpass", prefix="testuser")


@pytest.fixture
def auth_router_client(username):
    """创建测试客户端，设置固定的签名密钥"""
    auth_module._cached_token_secret = None
    with patch.dict(
        os.environ,
        {
            "AUTH_TOKEN_SECRET": "test-router-secret-key-at-least-32-bytes-long",
        },
    ):
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
        app.include_router(auth_router.public_router, prefix="/api/v1")
        with TestClient(app) as c:
            yield c


class TestLoginRoute:
    def test_login_success(self, auth_router_client, username):
        """正确凭据返回 200 + access_token"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": username, "password": "testpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, auth_router_client, username):
        """错误密码返回 401"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": username, "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self, auth_router_client):
        """错误用户名返回 401"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": "wronguser", "password": "testpass"},
        )
        assert resp.status_code == 401


class TestVerifyRoute:
    def test_verify_valid_token(self, auth_router_client, username):
        """有效 token 验证通过"""
        login_resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": username, "password": "testpass"},
        )
        token = login_resp.json()["access_token"]

        resp = auth_router_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["username"] == username

    def test_verify_no_token(self, auth_router_client):
        """缺少 token 返回 401"""
        resp = auth_router_client.get("/api/v1/auth/verify")
        assert resp.status_code == 401

    def test_verify_invalid_token(self, auth_router_client):
        """无效 token 返回 401"""
        resp = auth_router_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401
