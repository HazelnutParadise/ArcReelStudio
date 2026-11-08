"""ChatGPT 订阅登录（Codex device code）：用模仿 ``codex app-server`` 的假 CLI 走完整流程，不碰真账号。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from lib.subscriptions.codex_login import CodexLoginManager, SubscriptionLoginError

VERIFY_URL = "https://auth.openai.com/codex/device"
AUTH_JSON = {"auth_mode": "chatgpt", "tokens": {"access_token": "at", "refresh_token": "rt", "account_id": "acc"}}

# 与真 app-server 一样：一行一条 JSON-RPC；login/start 回网址和代码，之后按 FAKE_OUTCOME 结束登录。
_FAKE_CLI = f"""#!{sys.executable}
import json, os, sys, time
assert sys.argv[1] == "app-server", sys.argv
home = os.environ["CODEX_HOME"]
outcome = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "outcome")).read().strip()
def send(o):
    sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
for line in sys.stdin:
    m = json.loads(line)
    method, mid = m.get("method"), m.get("id")
    if method == "initialize":
        send({{"id": mid, "result": {{"codexHome": home}}}})
    elif method == "account/login/start":
        assert m["params"] == {{"type": "chatgptDeviceCode"}}
        send({{"id": mid, "result": {{"type": "chatgptDeviceCode", "loginId": "L1", "verificationUrl": "{VERIFY_URL}", "userCode": "ABCD-1234"}}}})
        if outcome == "success":
            open(os.path.join(home, "auth.json"), "w").write({json.dumps(json.dumps(AUTH_JSON))})
            send({{"method": "account/login/completed", "params": {{"loginId": "L1", "success": True}}}})
        elif outcome == "rejected":
            send({{"method": "account/login/completed", "params": {{"loginId": "L1", "success": False, "error": "denied"}}}})
    elif method == "account/read":
        send({{"id": mid, "result": {{"account": {{"type": "chatgpt", "email": "me@example.com", "planType": "plus"}}}}}})
    elif method == "account/login/cancel":
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cancelled"), "w").write("1")
        send({{"id": mid, "result": {{"status": "canceled"}}}})
    elif mid is not None:
        send({{"id": mid, "result": {{}}}})
"""


@pytest.fixture
def fake_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()
    cli = fake_dir / "codex"
    cli.write_text(_FAKE_CLI, encoding="utf-8")
    cli.chmod(0o755)

    def configure(outcome: str) -> str:
        (fake_dir / "outcome").write_text(outcome, encoding="utf-8")
        return str(cli)

    configure.dir = fake_dir  # type: ignore[attr-defined]
    return configure


async def _wait_until_done(manager: CodexLoginManager, login_id: str):
    for _ in range(200):
        result = await manager.status(login_id)
        if result.status != "pending":
            return result
        await asyncio.sleep(0.02)
    raise AssertionError("login never finished")


async def test_device_login_returns_url_and_code_then_the_auth_json(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("success"))

    login_id, url, code = await manager.start()
    result = await _wait_until_done(manager, login_id)

    assert (url, code) == (VERIFY_URL, "ABCD-1234")
    assert result.status == "succeeded"
    assert json.loads(result.secret or "") == AUTH_JSON
    assert result.account_label == "me@example.com (plus)"


async def test_a_finished_result_is_handed_out_once(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("success"))
    login_id, _, _ = await manager.start()
    await _wait_until_done(manager, login_id)

    with pytest.raises(SubscriptionLoginError) as exc:
        await manager.status(login_id)
    assert exc.value.code == "login_not_found"


async def test_a_rejected_login_reports_failure(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("rejected"))
    login_id, _, _ = await manager.start()

    result = await _wait_until_done(manager, login_id)

    assert result.status == "failed"
    assert result.error_code == "login_rejected"
    assert result.secret is None


async def test_a_login_nobody_finishes_expires(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("never"), ttl_seconds=0.3)
    login_id, _, _ = await manager.start()

    result = await _wait_until_done(manager, login_id)

    assert result.status == "failed"
    assert result.error_code == "login_expired"


async def test_cancel_tells_codex_and_removes_the_temporary_home(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("never"))
    login_id, _, _ = await manager.start()
    home = manager._logins[login_id].home

    await manager.cancel(login_id)

    assert await asyncio.to_thread((fake_codex.dir / "cancelled").exists)
    assert not await asyncio.to_thread(Path(home).exists)
    with pytest.raises(SubscriptionLoginError):
        await manager.status(login_id)


async def test_the_temporary_home_is_removed_after_success(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("success"))
    login_id, _, _ = await manager.start()
    home = manager._logins[login_id].home

    await _wait_until_done(manager, login_id)

    assert not await asyncio.to_thread(Path(home).exists)


async def test_two_logins_run_side_by_side(fake_codex) -> None:
    manager = CodexLoginManager(cli_path=fake_codex("success"))

    first, _, _ = await manager.start()
    second, _, _ = await manager.start()

    assert first != second
    assert (await _wait_until_done(manager, first)).status == "succeeded"
    assert (await _wait_until_done(manager, second)).status == "succeeded"


async def test_a_missing_cli_is_a_clear_error(tmp_path: Path) -> None:
    manager = CodexLoginManager(cli_path=str(tmp_path / "missing-codex"))

    with pytest.raises(SubscriptionLoginError) as exc:
        await manager.start()
    assert exc.value.code == "cli_unavailable"
