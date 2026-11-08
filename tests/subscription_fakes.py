"""订阅登录的假驱动：不起真 CLI，按测试设定的结果完成登录。"""

from __future__ import annotations

import asyncio

from lib.subscriptions.claude_login import ClaudeLoginError
from lib.subscriptions.device_login import DeviceLoginResult


class FakeDevice:
    def __init__(self, result: DeviceLoginResult) -> None:
        self.result = result
        self.release = asyncio.Event()
        self.cancelled: list[str] = []

    async def start(self) -> tuple[str, str, str]:
        return "driver-1", "https://auth.example/device", "ABCD-1234"

    async def status(self, login_id: str) -> DeviceLoginResult:
        if not self.release.is_set():
            return DeviceLoginResult(status="pending")
        return self.result

    async def cancel(self, login_id: str) -> None:
        self.cancelled.append(login_id)

    async def close(self) -> None:
        return None


class FakeClaude:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def start(self) -> tuple[str, str]:
        return "claude-driver", "https://claude.com/cai/oauth/authorize"

    async def submit_code(self, login_id: str, code: str) -> str:
        if code == "bad":
            raise ClaudeLoginError("code_rejected")
        return "sk-ant-oat01-token"

    async def cancel(self, login_id: str) -> None:
        self.cancelled.append(login_id)

    async def close(self) -> None:
        return None
