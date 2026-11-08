"""用 Grok 订阅登录（device code）：后台跑 ``grok login --device-auth``，把网址与一次性代码交给页面，用户在自己的
浏览器授权后 CLI 退出，我们把它写进 ``~/.grok`` 的凭证文件打包存起来。

CLI 没公开凭证文件的名称，所以登录成功后收下 ``~/.grok`` 里除日志、文档、会话以外的全部文件，用的时候原样放回
连线专属的临时 HOME。每次登录用一个临时 HOME，结束（成功、失败、取消或过期）都会结束进程并删掉目录。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from lib.subscriptions.device_login import DeviceLoginResult, SubscriptionLoginError

logger = logging.getLogger(__name__)

LOGIN_TTL_SECONDS = 15 * 60
START_TIMEOUT_SECONDS = 30.0
#: ``~/.grok`` 里不是凭证的目录与文件，打包时略过
_SKIPPED_TOP_LEVEL = frozenset({"logs", "docs", "sessions", "worktrees", "memory", "cache", "tmp"})
#: 打包的凭证文件总大小上限：防止误收大文件
_MAX_BUNDLE_BYTES = 256 * 1024

_URL = re.compile(r"https://accounts\.x\.ai/\S+")
_CODE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def grok_cli_path() -> str | None:
    return shutil.which("grok")


@dataclass
class _GrokLogin:
    login_id: str
    home: str
    process: asyncio.subprocess.Process
    verification_url: str
    user_code: str
    output: list[str]
    started_at: float = field(default_factory=time.monotonic)
    result: DeviceLoginResult = field(default_factory=lambda: DeviceLoginResult(status="pending"))
    watcher: asyncio.Task[None] | None = None


class GrokLoginManager:
    def __init__(self, cli_path: str | None = None, *, ttl_seconds: float = LOGIN_TTL_SECONDS) -> None:
        self._cli_path = cli_path
        self._ttl = ttl_seconds
        self._logins: dict[str, _GrokLogin] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> tuple[str, str, str]:
        """开始一次登录，返回 ``(login_id, 验证网址, 一次性代码)``。"""
        await self._sweep()
        cli = self._cli_path or grok_cli_path()
        if not cli:
            raise SubscriptionLoginError("cli_unavailable", "grok CLI not found on PATH")
        home = await asyncio.to_thread(tempfile.mkdtemp, prefix="grok-login-")
        env = {
            "HOME": home,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": "dumb",
            "NO_COLOR": "1",
            # 容器里没有浏览器：让 CLI 打不开浏览器，直接给网址
            "BROWSER": "true",
        }
        try:
            process = await asyncio.create_subprocess_exec(
                cli,
                "--no-auto-update",
                "login",
                "--device-auth",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=home,
                start_new_session=True,
            )
        except OSError as exc:
            await asyncio.to_thread(_remove_home, home)
            raise SubscriptionLoginError("cli_unavailable", str(exc)) from exc
        output: list[str] = []
        try:
            url, code = await asyncio.wait_for(_read_url_and_code(process, output), timeout=START_TIMEOUT_SECONDS)
        except (TimeoutError, SubscriptionLoginError) as exc:
            await _stop(process)
            await asyncio.to_thread(_remove_home, home)
            detail = _tail(output)
            raise SubscriptionLoginError("login_start_failed", detail or str(exc)) from exc
        login = _GrokLogin(
            login_id=secrets.token_urlsafe(16),
            home=home,
            process=process,
            verification_url=url,
            user_code=code,
            output=output,
        )
        login.watcher = asyncio.create_task(self._watch(login), name=f"grok-login-{login.login_id[:6]}")
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
            await self._finish(login)

    async def close(self) -> None:
        async with self._lock:
            logins, self._logins = list(self._logins.values()), {}
        for login in logins:
            await self._finish(login)

    async def _watch(self, login: _GrokLogin) -> None:
        try:
            try:
                returncode = await asyncio.wait_for(_drain_until_exit(login.process, login.output), timeout=self._ttl)
            except TimeoutError:
                login.result = DeviceLoginResult(status="failed", error_code="login_expired")
                return
            if returncode != 0:
                login.result = DeviceLoginResult(
                    status="failed", error_code="login_rejected", error_detail=_tail(login.output)
                )
                return
            bundle = await asyncio.to_thread(bundle_grok_credentials, login.home)
            if not bundle:
                login.result = DeviceLoginResult(status="failed", error_code="credentials_missing")
                return
            login.result = DeviceLoginResult(
                status="succeeded", secret=bundle, account_label=_account_label(login.output)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 意外错误也要让页面看到失败，而不是一直等
            logger.exception("grok login watcher failed")
            login.result = DeviceLoginResult(status="failed", error_code="login_failed", error_detail=str(exc))
        finally:
            await _stop(login.process)
            await asyncio.to_thread(_remove_home, login.home)

    async def _finish(self, login: _GrokLogin) -> None:
        if login.watcher is not None and not login.watcher.done():
            login.watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await login.watcher
        await _stop(login.process)
        await asyncio.to_thread(_remove_home, login.home)

    async def _sweep(self) -> None:
        now = time.monotonic()
        async with self._lock:
            stale = [item for item in self._logins.values() if now - item.started_at > self._ttl + 60]
            for login in stale:
                self._logins.pop(login.login_id, None)
        for login in stale:
            await self._finish(login)


def bundle_grok_credentials(home: str) -> str | None:
    """把 ``HOME/.grok`` 里的凭证文件打包成 JSON（``{相对路径: 内容}``）；没有文件时为 None。"""
    root = Path(home) / ".grok"
    if not root.is_dir():
        return None
    files: dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in _SKIPPED_TOP_LEVEL:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        total += len(content)
        if total > _MAX_BUNDLE_BYTES:
            break
        files[relative.as_posix()] = content
    return json.dumps(files, ensure_ascii=False) if files else None


def restore_grok_credentials(bundle: str, home: str) -> None:
    """把 :func:`bundle_grok_credentials` 的结果放回 ``HOME/.grok``，权限只给自己读写。"""
    root = Path(home) / ".grok"
    files = json.loads(bundle)
    if not isinstance(files, dict):
        raise ValueError("grok credential bundle must be an object")
    for relative, content in files.items():
        target = (root / str(relative)).resolve()
        if root.resolve() not in target.parents:
            raise ValueError(f"grok credential path escapes .grok: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        target.chmod(0o600)


async def _read_url_and_code(process: asyncio.subprocess.Process, output: list[str]) -> tuple[str, str]:
    stdout = process.stdout
    assert stdout is not None
    url: str | None = None
    code: str | None = None
    while url is None or code is None:
        raw = await stdout.readline()
        if not raw:
            raise SubscriptionLoginError("login_start_failed", "grok exited before showing a code")
        line = _ANSI.sub("", raw.decode("utf-8", "replace"))
        output.append(line)
        if url is None and (match := _URL.search(line)):
            url = match.group(0)
            if code is None and (in_url := re.search(r"user_code=([A-Z0-9-]+)", url)):
                code = in_url.group(1)
        elif code is None and (match := _CODE.search(line)):
            code = match.group(1)
    return url, code


async def _drain_until_exit(process: asyncio.subprocess.Process, output: list[str]) -> int:
    stdout = process.stdout
    if stdout is not None:
        while raw := await stdout.readline():
            output.append(_ANSI.sub("", raw.decode("utf-8", "replace")))
            del output[:-200]
    return await process.wait()


async def _stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(process.wait(), timeout=5)


def _remove_home(home: str) -> None:
    shutil.rmtree(home, ignore_errors=True)  # hard-delete: temp -- 这次登录专用的临时 HOME


def _tail(output: list[str], limit: int = 400) -> str:
    return " ".join(" ".join(output).split())[-limit:]


def _account_label(output: list[str]) -> str | None:
    for line in reversed(output):
        if match := _EMAIL.search(line):
            return match.group(0)
    return None
