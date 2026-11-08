"""Grok 订阅登录（device code）：用印出与真 CLI 相同提示的假 ``grok`` 走完整流程，不碰真账号。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from lib.subscriptions.device_login import SubscriptionLoginError
from lib.subscriptions.grok_login import (
    GrokLoginManager,
    bundle_grok_credentials,
    restore_grok_credentials,
)

# 与 grok 1.0.77 实测输出相同的提示；最后按旁边 outcome 文件决定结果
_FAKE_CLI = f"""#!{sys.executable}
import os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
assert sys.argv[1:] == ["--no-auto-update", "login", "--device-auth"], sys.argv
outcome = open(os.path.join(here, "outcome")).read().strip()
home = os.environ["HOME"]
print("\\nTo sign in, open this URL in your browser:\\n")
print("  https://accounts.x.ai/oauth2/device?user_code=WXYZ-9876\\n")
print("Confirm this code in your browser:\\n\\n  WXYZ-9876\\n")
print("\\x1b[90mOnly continue with a code you requested.\\x1b[0m\\n\\nWaiting for authorization...", flush=True)
if outcome == "success":
    os.makedirs(os.path.join(home, ".grok", "logs"))
    open(os.path.join(home, ".grok", "auth.json"), "w").write('{{"access_token": "a", "refresh_token": "r"}}')
    open(os.path.join(home, ".grok", "logs", "unified.jsonl"), "w").write("noise")
    print("Logged in as me@example.com", flush=True)
    sys.exit(0)
if outcome == "rejected":
    print("Authorization denied", flush=True)
    sys.exit(1)
time.sleep(60)
"""


@pytest.fixture
def fake_grok(tmp_path: Path):
    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()
    cli = fake_dir / "grok"
    cli.write_text(_FAKE_CLI, encoding="utf-8")
    cli.chmod(0o755)

    def configure(outcome: str) -> str:
        (fake_dir / "outcome").write_text(outcome, encoding="utf-8")
        return str(cli)

    return configure


async def _wait_until_done(manager: GrokLoginManager, login_id: str):
    for _ in range(250):
        result = await manager.status(login_id)
        if result.status != "pending":
            return result
        await asyncio.sleep(0.02)
    raise AssertionError("login never finished")


async def test_device_login_returns_url_and_code_then_the_credential_files(fake_grok) -> None:
    manager = GrokLoginManager(cli_path=fake_grok("success"))

    login_id, url, code = await manager.start()
    result = await _wait_until_done(manager, login_id)

    assert url == "https://accounts.x.ai/oauth2/device?user_code=WXYZ-9876"
    assert code == "WXYZ-9876"
    assert result.status == "succeeded"
    assert json.loads(result.secret or "") == {"auth.json": '{"access_token": "a", "refresh_token": "r"}'}
    assert result.account_label == "me@example.com"


async def test_a_rejected_login_reports_failure(fake_grok) -> None:
    manager = GrokLoginManager(cli_path=fake_grok("rejected"))
    login_id, _, _ = await manager.start()

    result = await _wait_until_done(manager, login_id)

    assert result.status == "failed"
    assert result.error_code == "login_rejected"


async def test_a_login_nobody_finishes_expires(fake_grok) -> None:
    manager = GrokLoginManager(cli_path=fake_grok("never"), ttl_seconds=0.5)
    login_id, _, _ = await manager.start()

    result = await _wait_until_done(manager, login_id)

    assert (result.status, result.error_code) == ("failed", "login_expired")


async def test_cancel_stops_the_cli_and_removes_the_temporary_home(fake_grok) -> None:
    manager = GrokLoginManager(cli_path=fake_grok("never"))
    login_id, _, _ = await manager.start()
    login = manager._logins[login_id]

    await manager.cancel(login_id)

    assert login.process.returncode is not None
    assert not await asyncio.to_thread(Path(login.home).exists)
    with pytest.raises(SubscriptionLoginError):
        await manager.status(login_id)


async def test_a_missing_cli_is_a_clear_error(tmp_path: Path) -> None:
    manager = GrokLoginManager(cli_path=str(tmp_path / "missing-grok"))

    with pytest.raises(SubscriptionLoginError) as exc:
        await manager.start()
    assert exc.value.code == "cli_unavailable"


def test_credentials_round_trip_into_a_fresh_home(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / ".grok" / "nested").mkdir(parents=True)
    (source / ".grok" / "auth.json").write_text("{}", encoding="utf-8")
    (source / ".grok" / "nested" / "x.toml").write_text("a = 1", encoding="utf-8")
    bundle = bundle_grok_credentials(str(source))
    assert bundle is not None

    target = tmp_path / "target"
    restore_grok_credentials(bundle, str(target))

    assert (target / ".grok" / "auth.json").read_text(encoding="utf-8") == "{}"
    assert (target / ".grok" / "nested" / "x.toml").read_text(encoding="utf-8") == "a = 1"
    assert (target / ".grok" / "auth.json").stat().st_mode & 0o777 == 0o600


def test_restoring_refuses_paths_outside_the_grok_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        restore_grok_credentials(json.dumps({"../evil": "x"}), str(tmp_path))


def test_private_files_are_never_readable_by_others(tmp_path: Path) -> None:
    from lib.subscriptions.grok_login import write_private_file

    target = tmp_path / "auth.json"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)

    write_private_file(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert target.stat().st_mode & 0o777 == 0o600
