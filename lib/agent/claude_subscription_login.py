"""在网页上完成 Claude 订阅登录：在后台跑内置 CLI 的 ``claude setup-token``，把授权链接交给页面，再把用户贴回的
验证码送进去，换回长效 OAuth 令牌。

CLI 只在终端里工作，所以给它一个伪终端。每次登录用一个临时 HOME，CLI 不会读到或写进容器里正在用的
``~/.claude``；登录结束（成功、失败、取消或过期）都会结束进程并删掉临时目录。同一时间只有一个登录在进行，
新的登录会取代旧的。
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import re
import secrets
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: 授权链接在 OSC 8 超链接里（``ESC ] 8 ; params ; URL BEL``），比按屏幕折行后的文字可靠
_OSC8_URL = re.compile(rb"\x1b\]8;[^;\x07\x1b]*;(https://[^\x07\x1b]+)")
_PLAIN_URL = re.compile(rb"https://claude\.(?:com|ai)/[^\s\x07\x1b]+")
_TOKEN = re.compile(rb"sk-ant-oat\d{2}-[A-Za-z0-9_\-]+")
_ANSI = re.compile(rb"\x1b\][^\x07]*\x07|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")

URL_TIMEOUT_SECONDS = 30.0
TOKEN_TIMEOUT_SECONDS = 60.0
#: 拿到链接后多久没贴验证码就作废
LOGIN_TTL_SECONDS = 10 * 60
#: 伪终端开得够宽，链接和令牌都不会被折行
_PTY_COLUMNS = 4000


class ClaudeLoginError(Exception):
    """登录没完成。``code`` 是给界面本地化用的稳定键。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def bundled_cli_path() -> str | None:
    """Agent SDK 内置的 CLI，找不到时退回 PATH 上的 ``claude``。"""
    try:
        import claude_agent_sdk
    except ImportError:  # pragma: no cover - SDK 是硬依赖
        return shutil.which("claude")
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("claude")


@dataclass
class _Login:
    login_id: str
    process: subprocess.Popen[bytes]
    master_fd: int
    home: str
    authorize_url: str
    started_at: float = field(default_factory=time.monotonic)
    output: bytearray = field(default_factory=bytearray)

    def close(self) -> None:
        with contextlib.suppress(ProcessLookupError, OSError):
            self.process.kill()
        with contextlib.suppress(Exception):
            self.process.wait(timeout=5)
        with contextlib.suppress(OSError):
            os.close(self.master_fd)
        shutil.rmtree(self.home, ignore_errors=True)  # hard-delete: temp -- 这次登录专用的临时 HOME


def _read_until(
    fd: int, buffer: bytearray, pattern: re.Pattern[bytes], timeout: float, process: subprocess.Popen[bytes]
) -> bytes | None:
    """从伪终端读到 ``pattern`` 出现为止，返回第一个分组（没有分组时返回整段匹配）；超时或进程退出时为 None。"""
    deadline = time.monotonic() + timeout
    while True:
        match = pattern.search(bytes(buffer))
        if match:
            return match.group(1) if match.groups() else match.group(0)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                return _final_match(buffer, pattern)
            buffer.extend(chunk)
        elif process.poll() is not None:
            return _final_match(buffer, pattern)


def _final_match(buffer: bytearray, pattern: re.Pattern[bytes]) -> bytes | None:
    match = pattern.search(bytes(buffer))
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def _visible_tail(buffer: bytearray, limit: int = 400) -> str:
    # 令牌不进错误信息
    raw = _TOKEN.sub(b"[token]", _ANSI.sub(b"", bytes(buffer)))
    return " ".join(raw.decode("utf-8", "replace").split())[-limit:]


class ClaudeLoginManager:
    def __init__(self, cli_path: str | None = None) -> None:
        self._cli_path = cli_path
        self._login: _Login | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> tuple[str, str]:
        """开始一次登录，返回 ``(login_id, 授权链接)``；正在进行的登录会被取代。"""
        async with self._lock:
            await self._discard()
            cli = self._cli_path or bundled_cli_path()
            if not cli:
                raise ClaudeLoginError("cli_not_found")
            login = await asyncio.to_thread(self._spawn, cli)
            self._login = login
            return login.login_id, login.authorize_url

    async def submit_code(self, login_id: str, code: str) -> str:
        """把验证码送进 CLI，返回换到的长效令牌。登录不论成败都会结束。"""
        async with self._lock:
            login = self._login
            if login is None or login.login_id != login_id:
                raise ClaudeLoginError("login_not_found")
            if time.monotonic() - login.started_at > LOGIN_TTL_SECONDS:
                await self._discard()
                raise ClaudeLoginError("login_expired")
            cleaned = code.strip()
            if not cleaned or any(ch in cleaned for ch in "\r\n\x00"):
                raise ClaudeLoginError("invalid_code")
            self._login = None
            try:
                return await asyncio.to_thread(self._exchange, login, cleaned)
            finally:
                await asyncio.to_thread(login.close)

    async def cancel(self) -> None:
        async with self._lock:
            await self._discard()

    async def _discard(self) -> None:
        login, self._login = self._login, None
        if login is not None:
            await asyncio.to_thread(login.close)

    @staticmethod
    def _spawn(cli: str) -> _Login:
        home = tempfile.mkdtemp(prefix="claude-login-")
        master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, _PTY_COLUMNS, 0, 0))
        env = {
            "HOME": home,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "xterm-256color",
            "COLUMNS": str(_PTY_COLUMNS),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            # 容器里没有浏览器：让 CLI 打不开浏览器，直接给链接
            "BROWSER": "true",
        }
        try:
            process = subprocess.Popen(
                [cli, "setup-token"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                cwd=home,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            os.close(master_fd)
            os.close(slave_fd)
            shutil.rmtree(home, ignore_errors=True)  # hard-delete: temp -- 起进程失败，删掉刚建的临时 HOME
            raise ClaudeLoginError("cli_not_found", str(exc)) from exc
        os.close(slave_fd)
        login = _Login(
            login_id=secrets.token_urlsafe(16),
            process=process,
            master_fd=master_fd,
            home=home,
            authorize_url="",
        )
        url = _read_until(master_fd, login.output, _OSC8_URL, URL_TIMEOUT_SECONDS, process)
        if url is None:
            url = _final_match(login.output, _PLAIN_URL)
        if url is None:
            detail = _visible_tail(login.output)
            login.close()
            raise ClaudeLoginError("no_authorize_url", detail)
        login.authorize_url = url.decode("utf-8", "replace")
        return login

    @staticmethod
    def _exchange(login: _Login, code: str) -> str:
        login.output.clear()
        os.write(login.master_fd, code.encode("utf-8") + b"\r")
        token = _read_until(login.master_fd, login.output, _TOKEN, TOKEN_TIMEOUT_SECONDS, login.process)
        if token is None:
            raise ClaudeLoginError("code_rejected", _visible_tail(login.output))
        return token.decode("ascii")
