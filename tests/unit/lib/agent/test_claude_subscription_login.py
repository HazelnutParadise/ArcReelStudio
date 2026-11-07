"""网页上的 Claude 订阅登录：用一个模仿 ``claude setup-token`` 的假 CLI 走完整流程，不碰真账号。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from lib.agent.claude_subscription_login import ClaudeLoginError, ClaudeLoginManager

AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize?code=true&client_id=x&state=abc"
TOKEN = "sk-ant-oat01-Abc_def-123"

# 与真 CLI 一样：链接放在 OSC 8 超链接里，提示后等一行验证码，正确时印出令牌
_FAKE_CLI = f"""#!{sys.executable}
import os, sys
if sys.argv[1:] != ["setup-token"]:
    sys.exit(2)
home = os.environ["HOME"]
open(os.path.join(home, "seen-home"), "w").write(home)
sys.stdout.write("Opening browser to sign in...\\n")
sys.stdout.write("\\x1b]8;id=1;{AUTHORIZE_URL}\\x07{AUTHORIZE_URL[:20]}\\x1b]8;;\\x07\\n")
sys.stdout.write("Paste code here if prompted > ")
sys.stdout.flush()
code = sys.stdin.readline().strip()
if code == "good-code":
    sys.stdout.write("\\n\\x1b[32mYour OAuth token (valid for 1 year):\\x1b[0m\\n\\n{TOKEN}\\n")
    sys.stdout.flush()
    sys.stdin.readline()
else:
    sys.stdout.write("\\nOAuth error: invalid code\\n")
    sys.exit(1)
"""


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    path = tmp_path / "claude"
    path.write_text(_FAKE_CLI, encoding="utf-8")
    path.chmod(0o755)
    return path


async def test_login_returns_the_link_then_exchanges_the_code_for_a_token(fake_cli) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))

    login_id, url = await manager.start()
    token = await manager.submit_code(login_id, "  good-code  ")

    assert url == AUTHORIZE_URL
    assert token == TOKEN


async def test_the_cli_runs_in_a_throwaway_home_that_is_removed_afterwards(fake_cli) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))

    login_id, _ = await manager.start()
    home = manager._login.home
    # 每次登录专用的临时目录，不是容器里正在用的 HOME
    assert Path(home).name.startswith("claude-login-")
    await manager.submit_code(login_id, "good-code")

    assert not await asyncio.to_thread(Path(home).exists)


async def test_a_rejected_code_reports_why_without_leaking_a_token(fake_cli) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))
    login_id, _ = await manager.start()

    with pytest.raises(ClaudeLoginError) as exc_info:
        await manager.submit_code(login_id, "bad-code")

    assert exc_info.value.code == "code_rejected"
    assert "invalid code" in exc_info.value.detail


async def test_a_code_for_another_login_is_refused(fake_cli) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))
    await manager.start()

    with pytest.raises(ClaudeLoginError) as exc_info:
        await manager.submit_code("someone-else", "good-code")

    assert exc_info.value.code == "login_not_found"
    await manager.cancel()


async def test_a_new_login_replaces_the_previous_one(fake_cli) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))
    first_id, _ = await manager.start()
    first_home = manager._login.home

    second_id, _ = await manager.start()

    assert not await asyncio.to_thread(Path(first_home).exists)
    with pytest.raises(ClaudeLoginError):
        await manager.submit_code(first_id, "good-code")
    assert await manager.submit_code(second_id, "good-code") == TOKEN


@pytest.mark.parametrize("code", ["", "   ", "a\nb"])
async def test_empty_or_multiline_codes_are_refused_before_reaching_the_cli(fake_cli, code) -> None:
    manager = ClaudeLoginManager(cli_path=str(fake_cli))
    login_id, _ = await manager.start()

    with pytest.raises(ClaudeLoginError) as exc_info:
        await manager.submit_code(login_id, code)

    assert exc_info.value.code == "invalid_code"
    await manager.cancel()


async def test_a_missing_cli_is_reported(tmp_path) -> None:
    manager = ClaudeLoginManager(cli_path=str(tmp_path / "nope"))

    with pytest.raises(ClaudeLoginError) as exc_info:
        await manager.start()

    assert exc_info.value.code == "cli_not_found"
