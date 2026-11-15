"""Claude 引擎只用应用选定的连线：没有连线时不起任何进程；起进程时配置目录是应用自己的，宿主的登录与认证变量都带不进去。"""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from lib.agent.credential_tiers import AgentPricing
from lib.config.service import AnthropicEnv
from server.agent_runtime.models import AgentConnectionMissing
from server.agent_runtime.options_assembler import load_provider_env_overrides
from server.agent_runtime.session_manager import SessionManager
from server.agent_runtime.session_store import SessionMetaStore
from tests.factories import make_session_meta
from tests.fakes import use_provider_env, use_sdk_client

_HOST_AUTH_ENV = {
    "ANTHROPIC_API_KEY": "sk-host-personal",
    "ANTHROPIC_AUTH_TOKEN": "host-auth-token",
    "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-host",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_USE_VERTEX": "1",
    "CLAUDE_CONFIG_DIR": "/Users/host/.claude",
}


@pytest.fixture
def manager(tmp_path: Path) -> SessionManager:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    manager = SessionManager(project_root, SessionMetaStore())
    project_dir = manager.layout.projects_dir / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text('{"title": "t"}', encoding="utf-8")
    return manager


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """记下 SessionManager 建过的每个 SDK 客户端（即每个将要起的 CLI 进程）的 options。"""
    created: list[Any] = []

    def factory(options: Any) -> Any:
        created.append(options)
        raise AssertionError("no CLI process may start without an Agent connection")

    use_sdk_client(monkeypatch, factory)
    return created


async def _no_connection() -> dict[str, str]:
    return await _real_overrides(AnthropicEnv(env={}, pricing=AgentPricing()))


async def _real_overrides(anthropic: AnthropicEnv) -> dict[str, str]:
    async def fake_build(_session: Any) -> AnthropicEnv:
        return anthropic

    with patch("lib.config.service.build_anthropic_env", side_effect=fake_build):
        return await load_provider_env_overrides()


@pytest.mark.asyncio
async def test_new_session_without_a_connection_is_refused_before_any_process(
    manager: SessionManager, spawned: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in _HOST_AUTH_ENV.items():
        monkeypatch.setenv(key, value)
    use_provider_env(monkeypatch, _no_connection)

    with pytest.raises(AgentConnectionMissing):
        await manager.send_new_session("demo", "你好")

    assert spawned == []
    assert manager.sessions == {}


@pytest.mark.asyncio
async def test_resuming_without_a_connection_is_refused_before_any_process(
    manager: SessionManager, spawned: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_provider_env(monkeypatch, _no_connection)
    meta = make_session_meta(id="old-session", project_name="demo", status="idle")

    with pytest.raises(AgentConnectionMissing):
        await manager.get_or_connect("old-session", meta=meta)

    assert spawned == []
    assert "old-session" not in manager.sessions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("anthropic", "expected"),
    [
        pytest.param(
            AnthropicEnv(env={"ANTHROPIC_API_KEY": "sk-app-selected"}, pricing=AgentPricing(credential_id=1)),
            {"ANTHROPIC_API_KEY": "sk-app-selected", "CLAUDE_CODE_OAUTH_TOKEN": ""},
            id="api-key",
        ),
        pytest.param(
            AnthropicEnv(
                env={"ANTHROPIC_API_KEY": "", "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-app-login"},
                pricing=AgentPricing(multiplier=0.0, subscription_credential_id=2),
                source="subscription",
            ),
            {"ANTHROPIC_API_KEY": "", "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-app-login"},
            id="app-subscription-login",
        ),
    ],
)
async def test_the_cli_gets_an_app_owned_config_dir_and_only_the_selected_connection(
    manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
    anthropic: AnthropicEnv,
    expected: dict[str, str],
) -> None:
    for key, value in _HOST_AUTH_ENV.items():
        monkeypatch.setenv(key, value)

    async def selected() -> dict[str, str]:
        return await _real_overrides(anthropic)

    use_provider_env(monkeypatch, selected)

    options = await manager._build_options("demo")

    config_dir = Path(options.env["CLAUDE_CONFIG_DIR"])
    assert config_dir == manager.layout.claude_agent_config_dir
    mode = (await asyncio.to_thread(config_dir.stat)).st_mode
    assert stat.S_ISDIR(mode)
    assert stat.S_IMODE(mode) == 0o700
    for key, value in expected.items():
        assert options.env[key] == value
    # 宿主的旁路认证与云账号开关一律被空值覆盖（SDK 用 options.env 覆盖继承的进程环境）
    for key in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        assert options.env[key] == ""
    assert "sk-host-personal" not in options.env.values()
    assert "sk-ant-oat01-host" not in options.env.values()


@pytest.mark.asyncio
async def test_no_inherited_claude_or_anthropic_variable_reaches_the_cli(
    manager: SessionManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SDK 把整个宿主环境传给 CLI、只用 options.env 覆盖：宿主的 ANTHROPIC_* / CLAUDE_CODE_* 一律按前缀置空。"""
    host = {
        "CLAUDE_CODE_USE_FOUNDRY": "1",
        "ANTHROPIC_FOUNDRY_API_KEY": "foundry-host",
        "ANTHROPIC_FOUNDRY_RESOURCE": "host-resource",
        "ANTHROPIC_CUSTOM_HEADERS": "X-Host: 1",
        "ANTHROPIC_VERTEX_PROJECT_ID": "host-gcp",
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "1",
        "CLAUDE_CODE_SOME_FUTURE_ROUTING": "host",
    }
    for key, value in host.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", r"C:\Git\bin\bash.exe")

    async def selected() -> dict[str, str]:
        return await _real_overrides(
            AnthropicEnv(env={"ANTHROPIC_API_KEY": "sk-app-selected"}, pricing=AgentPricing(credential_id=1))
        )

    use_provider_env(monkeypatch, selected)

    env = (await manager._build_options("demo")).env

    for key in host:
        assert env[key] == "", key
    assert env["ANTHROPIC_API_KEY"] == "sk-app-selected"
    assert env["CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS"] == "1"
    # 只为在宿主机器上找到程序的变量不涉及认证与路由，照常继承
    assert "CLAUDE_CODE_GIT_BASH_PATH" not in env


@pytest.mark.asyncio
async def test_require_connection_checks_without_starting_anything(
    manager: SessionManager, spawned: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_provider_env(monkeypatch, _no_connection)
    with pytest.raises(AgentConnectionMissing):
        await manager.require_connection("claude")
    assert spawned == []
