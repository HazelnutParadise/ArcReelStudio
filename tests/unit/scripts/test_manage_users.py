"""账号管理命令行：在独立的临时库与数据根上以子进程运行，与服务端一样按 ``DATABASE_URL`` 连库。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pwdlib import PasswordHash

_REPO = Path(__file__).resolve().parents[3]
_TIMEOUT = 180


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}",
        "ARCREEL_DATA_DIR": str(tmp_path / "data"),
        "AUTH_USERNAME": "admin",
        "AUTH_PASSWORD": "bootstrap-pass",
    }
    setup = (
        "import asyncio\n"
        "from lib.db import async_session_factory, init_db\n"
        "from lib.infra.data_root_layout import DataRootLayout\n"
        "from server.services.accounts import bootstrap_admin\n"
        "async def main():\n"
        "    await init_db()\n"
        "    await bootstrap_admin(async_session_factory,"
        " initial_password_path=DataRootLayout.current().initial_admin_password_path)\n"
        "asyncio.run(main())\n"
    )
    subprocess.run([sys.executable, "-c", setup], cwd=_REPO, env=env, check=True, timeout=_TIMEOUT)
    return env


def _cli(env: dict[str, str], *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.manage_users", *args],
        cwd=_REPO,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


def _password_matches(env: dict[str, str], username: str, password: str) -> bool:
    """直接读库里的密码哈希比对，不再多起一个子进程。"""
    db_path = env["DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(db_path) as conn:
        (password_hash,) = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    return PasswordHash.recommended().verify(password, password_hash)


def test_reset_password_then_list_accounts(cli_env):
    reset = _cli(cli_env, "reset-password", "ADMIN", "--password", "recovered-pass")
    listed = _cli(cli_env, "list")
    missing = _cli(cli_env, "reset-password", "nobody")

    assert reset.returncode == 0, reset.stderr
    assert _password_matches(cli_env, "admin", "recovered-pass")
    assert "新密码" not in reset.stdout
    assert listed.returncode == 0, listed.stderr
    assert "admin\tadmin\t启用" in listed.stdout
    assert missing.returncode == 1
    assert "找不到账号" in missing.stderr


def test_reset_password_reads_the_new_password_twice_without_printing_it(cli_env):
    reset = _cli(cli_env, "reset-password", "admin", stdin="typed-password\ntyped-password\n")

    assert reset.returncode == 0, reset.stderr
    assert _password_matches(cli_env, "admin", "typed-password")
    assert "typed-password" not in reset.stdout + reset.stderr


def test_reset_password_keeps_the_old_password_when_the_two_entries_differ(cli_env):
    reset = _cli(cli_env, "reset-password", "admin", stdin="first-password\nsecond-password\n")

    assert reset.returncode == 1
    assert "不一致" in reset.stderr
    assert _password_matches(cli_env, "admin", "bootstrap-pass")
