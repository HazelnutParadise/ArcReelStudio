"""Claude SDK 的本地会话目录只在应用自己的数据根里，不读宿主环境，也不指向宿主的 ``~/.claude``。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib.agent.agent_session_store import default_sdk_config_dir, pin_sdk_config_dir
from lib.infra.data_root_layout import DataRootLayout


def test_the_sdk_config_dir_is_the_apps_own_and_ignores_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "host-home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-home" / ".claude"))

    assert default_sdk_config_dir() == DataRootLayout.current().claude_agent_config_dir


def test_pinning_points_the_sdks_own_file_readers_at_the_app_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SDK 的 ``list_sessions`` / ``get_session_messages`` 只认进程环境的 ``CLAUDE_CONFIG_DIR``：启动时钉到应用目录。"""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-home" / ".claude"))

    pinned = pin_sdk_config_dir()

    assert pinned == DataRootLayout.current().claude_agent_config_dir
    assert os.environ["CLAUDE_CONFIG_DIR"] == str(pinned)
    assert pinned.is_dir()


_SESSION_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR")


@pytest.mark.parametrize("round_", [1, 2])
def test_a_pin_inside_one_test_does_not_leak_into_the_next(round_: int) -> None:
    """根 conftest 在每个用例结束时还原 CLAUDE_CONFIG_DIR：两轮都从会话级的测试值开始。"""
    assert os.environ.get("CLAUDE_CONFIG_DIR") == _SESSION_CONFIG_DIR
    pin_sdk_config_dir()
    assert os.environ["CLAUDE_CONFIG_DIR"] != _SESSION_CONFIG_DIR
