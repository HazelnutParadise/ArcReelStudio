"""Codex 引擎会话用哪条连线、怎么装配：指定的 ChatGPT 订阅或 OpenAI 连线优先，没指定时 ChatGPT 订阅先于 OpenAI；
订阅不计费、API Key 以 apiKey 登入自己的持久 CODEX_HOME。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.db.repositories.credential_repository import CredentialRepository
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.codex_engine import (
    CODEX_CREDENTIAL_SETTING_KEY,
    CODEX_MODEL_SETTING_KEY,
    build_codex_launch,
    codex_connection,
    parse_agent_engine,
)


async def _add(session, provider: str, name: str, key: str = "secret"):
    return await CredentialRepository(session).create(provider=provider, name=name, api_key=key)


def test_unknown_engine_values_mean_claude() -> None:
    assert parse_agent_engine("codex") == "codex"
    assert parse_agent_engine("") == "claude"
    assert parse_agent_engine("gemini") == "claude"


async def test_without_connections_there_is_none(db_session) -> None:
    assert await codex_connection(db_session, {}) is None


async def test_the_chatgpt_subscription_comes_before_openai(db_session) -> None:
    await _add(db_session, "openai", "key")
    chatgpt = await _add(db_session, "chatgpt-subscription", "me")

    assert (await codex_connection(db_session, {})).id == chatgpt.id


async def test_openai_is_used_without_a_subscription(db_session) -> None:
    openai = await _add(db_session, "openai", "key")

    assert (await codex_connection(db_session, {})).id == openai.id


async def test_a_chosen_connection_wins_and_other_providers_are_ignored(db_session) -> None:
    await _add(db_session, "chatgpt-subscription", "me")
    openai = await _add(db_session, "openai", "key")
    claude = await _add(db_session, "claude-subscription", "c")

    chosen = await codex_connection(db_session, {CODEX_CREDENTIAL_SETTING_KEY: str(openai.id)})
    assert chosen.id == openai.id
    fallback = await codex_connection(db_session, {CODEX_CREDENTIAL_SETTING_KEY: str(claude.id)})
    assert fallback.provider == "chatgpt-subscription"


@pytest.fixture
def project_cwd(tmp_path: Path) -> Path:
    project = (tmp_path / "repo" / "projects" / "demo").resolve()
    project.mkdir(parents=True)
    return project


async def _launch(db_session, connection, project_cwd: Path, settings: dict[str, str]):
    return await build_codex_launch(
        project_name="demo",
        project_cwd=project_cwd,
        data_root=project_cwd.parent.parent / "projects",
        user_id="default",
        policy=AgentAccessPolicy(
            project_root=project_cwd.parent.parent,
            data_root=project_cwd.parent.parent / "projects",
            agent_profile_root=project_cwd.parent.parent / "agent_runtime_profile",
        ),
        settings=settings,
        connection=connection,
        developer_instructions="rules",
        resume_thread_id="T-1",
    )


async def test_a_subscription_launch_is_free_and_carries_no_api_key(db_session, project_cwd: Path) -> None:
    connection = await _add(db_session, "chatgpt-subscription", "me")
    launch = await _launch(db_session, connection, project_cwd, {CODEX_MODEL_SETTING_KEY: "gpt-6-sol"})

    assert launch.auth_source == "subscription"
    assert (launch.pricing.multiplier, launch.pricing.provider_id) == (0.0, "chatgpt-subscription")
    assert launch.pricing.provider_credential_id == connection.id
    config = launch.config
    assert config.api_key is None
    assert config.model == "gpt-6-sol"
    assert config.resume_thread_id == "T-1"
    assert config.developer_instructions == "rules"
    assert config.skill_roots == (project_cwd / ".claude" / "skills",)
    assert config.codex_home.is_dir()
    names = {spec["name"] for spec in config.tool_specs}
    assert {"Read", "Write", "Edit", "Glob", "Grep"} <= names
    assert config.arcreel_tool_names <= names
    assert config.arcreel_tool_names.isdisjoint({"Read", "Write"})
    assert set(config.tool_callers) == names


async def test_an_api_key_launch_logs_in_with_the_key_and_is_priced(db_session, project_cwd: Path) -> None:
    connection = await _add(db_session, "openai", "key", key="sk-test")
    launch = await _launch(db_session, connection, project_cwd, {})

    assert launch.auth_source == "api_key"
    assert (launch.pricing.multiplier, launch.pricing.provider_id) == (1.0, "openai")
    assert launch.config.api_key == "sk-test"
    assert launch.config.model == "gpt-5.5"


async def test_file_tools_in_a_launch_stay_inside_the_project(db_session, project_cwd: Path) -> None:
    connection = await _add(db_session, "chatgpt-subscription", "me")
    launch = await _launch(db_session, connection, project_cwd, {})
    outside = project_cwd.parent / "other"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")

    write = await launch.config.tool_callers["Write"]("Write", {"file_path": "notes.md", "content": "hi"})
    assert write["success"] is True
    assert (project_cwd / "notes.md").read_text(encoding="utf-8") == "hi"
    read = await launch.config.tool_callers["Read"]("Read", {"file_path": str(outside / "secret.txt")})
    assert read["success"] is False
