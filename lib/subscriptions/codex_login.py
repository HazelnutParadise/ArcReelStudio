"""用 ChatGPT 账号登录 Codex（device code）：后台起 ``codex app-server``，把验证网址与一次性代码交给页面，
用户在自己的浏览器登录并输入代码后，app-server 发 ``account/login/completed``，我们读出 ``auth.json`` 存起来。

每次登录用一个临时 ``CODEX_HOME``，结束（成功、失败、取消或过期）都会结束进程并删掉目录。可以同时进行多个
登录（不同成员各自添加账号），各自独立。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from lib.agent.codex_app_server import CodexAppServer, CodexRpcError, NotificationWaiter
from lib.subscriptions.device_login import DeviceLoginResult, SubscriptionLoginError

logger = logging.getLogger(__name__)

#: 拿到代码后多久没完成就作废（OpenAI 的 device code 有效期约 15 分钟）
LOGIN_TTL_SECONDS = 15 * 60
START_TIMEOUT_SECONDS = 30.0


@dataclass
class _CodexLogin:
    login_id: str
    codex_login_id: str
    home: str
    server: CodexAppServer
    verification_url: str
    user_code: str
    started_at: float = field(default_factory=time.monotonic)
    result: DeviceLoginResult = field(default_factory=lambda: DeviceLoginResult(status="pending"))
    watcher: asyncio.Task[None] | None = None


class CodexLoginManager:
    def __init__(self, cli_path: str | None = None, *, ttl_seconds: float = LOGIN_TTL_SECONDS) -> None:
        self._cli_path = cli_path
        self._ttl = ttl_seconds
        self._logins: dict[str, _CodexLogin] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> tuple[str, str, str]:
        """开始一次登录，返回 ``(login_id, 验证网址, 一次性代码)``。"""
        await self._sweep()
        home = await asyncio.to_thread(tempfile.mkdtemp, prefix="codex-login-")
        try:
            server = await CodexAppServer.start(home, cli_path=self._cli_path)
        except CodexRpcError as exc:
            await asyncio.to_thread(_remove_home, home)
            raise SubscriptionLoginError("cli_unavailable", str(exc)) from exc
        # 每次登录有自己的 app-server，只会有这一个登录的完成通知；先登记再发请求，通知来得再快也不会漏
        completion = server.expect_notification("account/login/completed")
        try:
            response = await server.request(
                "account/login/start", {"type": "chatgptDeviceCode"}, timeout=START_TIMEOUT_SECONDS
            )
        except CodexRpcError as exc:
            completion.cancel()
            await server.close()
            await asyncio.to_thread(_remove_home, home)
            raise SubscriptionLoginError("login_start_failed", str(exc)) from exc
        url = str((response or {}).get("verificationUrl") or "")
        code = str((response or {}).get("userCode") or "")
        codex_login_id = str((response or {}).get("loginId") or "")
        if not url or not code:
            completion.cancel()
            await server.close()
            await asyncio.to_thread(_remove_home, home)
            raise SubscriptionLoginError("login_start_failed", "missing verification url or user code")
        login = _CodexLogin(
            login_id=secrets.token_urlsafe(16),
            codex_login_id=codex_login_id,
            home=home,
            server=server,
            verification_url=url,
            user_code=code,
        )
        login.watcher = asyncio.create_task(self._watch(login, completion), name=f"codex-login-{login.login_id[:6]}")
        async with self._lock:
            self._logins[login.login_id] = login
        return login.login_id, url, code

    async def status(self, login_id: str) -> DeviceLoginResult:
        """登录进度。成功或失败的结果只交出一次，之后这个 login_id 就不存在了。"""
        await self._sweep()
        async with self._lock:
            login = self._logins.get(login_id)
            if login is None:
                raise SubscriptionLoginError("login_not_found")
            if login.result.status != "pending":
                self._logins.pop(login_id, None)
            return login.result

    async def cancel(self, login_id: str) -> None:
        async with self._lock:
            login = self._logins.pop(login_id, None)
        if login is not None:
            if login.codex_login_id and not login.server.closed:
                with contextlib.suppress(CodexRpcError):
                    await login.server.request("account/login/cancel", {"loginId": login.codex_login_id}, timeout=5)
            await self._finish(login)

    async def close(self) -> None:
        async with self._lock:
            logins, self._logins = list(self._logins.values()), {}
        for login in logins:
            await self._finish(login)

    async def _watch(self, login: _CodexLogin, completion: NotificationWaiter) -> None:
        try:
            completed = await completion.wait(timeout=self._ttl)
            if not completed.get("success"):
                login.result = DeviceLoginResult(
                    status="failed", error_code="login_rejected", error_detail=str(completed.get("error") or "")
                )
                return
            account = await login.server.request("account/read", {"refreshToken": False}, timeout=15)
            secret = await asyncio.to_thread(_read_auth_json, login.home)
            if not secret:
                login.result = DeviceLoginResult(status="failed", error_code="credentials_missing")
                return
            login.result = DeviceLoginResult(status="succeeded", secret=secret, account_label=_account_label(account))
        except CodexRpcError as exc:
            expired = "timed out" in str(exc)
            login.result = DeviceLoginResult(
                status="failed", error_code="login_expired" if expired else "login_failed", error_detail=str(exc)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 意外错误也要让页面看到失败，而不是一直等
            logger.exception("codex login watcher failed")
            login.result = DeviceLoginResult(status="failed", error_code="login_failed", error_detail=str(exc))
        finally:
            await login.server.close()
            await asyncio.to_thread(_remove_home, login.home)

    async def _finish(self, login: _CodexLogin) -> None:
        if login.watcher is not None and not login.watcher.done():
            login.watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await login.watcher
        await login.server.close()
        await asyncio.to_thread(_remove_home, login.home)

    async def _sweep(self) -> None:
        """丢掉过期太久、结果也没人来拿的登录。"""
        now = time.monotonic()
        async with self._lock:
            stale = [item for item in self._logins.values() if now - item.started_at > self._ttl + 60]
            for login in stale:
                self._logins.pop(login.login_id, None)
        for login in stale:
            await self._finish(login)


def _read_auth_json(home: str) -> str | None:
    path = Path(home) / "auth.json"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _remove_home(home: str) -> None:
    shutil.rmtree(home, ignore_errors=True)  # hard-delete: temp -- 这次登录专用的临时 CODEX_HOME


def _account_label(response: object) -> str | None:
    if not isinstance(response, dict):
        return None
    account = response.get("account")
    if not isinstance(account, dict):
        return None
    email = account.get("email")
    plan = account.get("planType")
    if email and plan:
        return f"{email} ({plan})"
    return str(email or plan) if (email or plan) else None
