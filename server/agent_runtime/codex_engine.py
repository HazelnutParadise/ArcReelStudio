"""Agent 用 Codex 引擎时的会话装配：选哪条连线、它的 CODEX_HOME、系统提示、工具与计价。

Claude 引擎的对应物是 :class:`server.agent_runtime.options_assembler.OptionsAssembler`；两者产出的会话都由
:class:`server.agent_runtime.session_actor.SessionActor` 驱动，事件日志、用量与前端不分引擎（docs/adr/0124）。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, get_args

from lib.agent.agent_auth import AuthSource
from lib.agent.credential_tiers import AgentPricing
from lib.backends.subscription_shared import PROVIDER_CHATGPT_SUBSCRIPTION
from lib.db.models.credential import ProviderCredential
from lib.db.repositories.credential_repository import CredentialRepository
from lib.subscriptions.connection_home import connection_home
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.codex_client import CodexSessionConfig
from server.agent_runtime.codex_file_tools import FILE_TOOL_NAMES, FILE_TOOL_SPECS, CodexFileTools
from server.agent_runtime.codex_tools import build_arcreel_codex_tools

AgentEngine = Literal["claude", "codex"]
AGENT_ENGINES: tuple[AgentEngine, ...] = get_args(AgentEngine)
DEFAULT_AGENT_ENGINE: AgentEngine = "claude"
#: system_settings 键：新会话用哪个引擎、Codex 用哪条连线与哪个模型
AGENT_ENGINE_SETTING_KEY = "agent_engine"
CODEX_CREDENTIAL_SETTING_KEY = "agent_codex_credential_id"
CODEX_MODEL_SETTING_KEY = "agent_codex_model"
DEFAULT_CODEX_MODEL = "gpt-5.5"
#: Codex 引擎能用的连线供应商：ChatGPT 订阅与 OpenAI API Key
CODEX_PROVIDERS = frozenset({PROVIDER_CHATGPT_SUBSCRIPTION, "openai"})


class CodexConnectionMissing(RuntimeError):
    """设定选了 Codex 引擎，但找不到能用的 ChatGPT 订阅或 OpenAI 连线。"""


def parse_agent_engine(raw: str | None) -> AgentEngine:
    value = (raw or "").strip()
    return cast("AgentEngine", value) if value in AGENT_ENGINES else DEFAULT_AGENT_ENGINE


@dataclass(frozen=True)
class CodexLaunch:
    config: CodexSessionConfig
    pricing: AgentPricing
    auth_source: AuthSource


async def codex_connection(session: Any, settings: Mapping[str, str]) -> ProviderCredential | None:
    """Codex 会话用的连线：设定指定的那条（须是 ChatGPT 订阅或 OpenAI），没指定或已删除时取 ChatGPT 订阅的预设连线，
    再没有时取 OpenAI 的预设连线。"""
    repo = CredentialRepository(session)
    raw = (settings.get(CODEX_CREDENTIAL_SETTING_KEY) or "").strip()
    if raw.isdigit():
        chosen = await repo.get_by_id(int(raw))
        if chosen is not None and chosen.provider in CODEX_PROVIDERS:
            return chosen
    for provider in (PROVIDER_CHATGPT_SUBSCRIPTION, "openai"):
        default = await repo.get_active(provider)
        if default is not None:
            return default
    return None


def _prepare_home(provider_id: str, credential_id: int) -> Path:
    home = connection_home(provider_id, credential_id)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(home, 0o700)
    return home


async def build_codex_launch(
    *,
    project_name: str,
    project_cwd: Path,
    data_root: Path,
    user_id: str,
    policy: AgentAccessPolicy,
    settings: Mapping[str, str],
    connection: ProviderCredential,
    developer_instructions: str,
    resume_thread_id: str | None,
) -> CodexLaunch:
    """一个 Codex 会话的启动参数。ChatGPT 订阅用登录时存下的 CODEX_HOME；OpenAI API Key 连线用自己的持久 CODEX_HOME
    （恢复会话要读回 Codex 的对话纪录）并以 apiKey 登入。"""
    home = await asyncio.to_thread(_prepare_home, connection.provider, connection.id)
    # 工具集的 ProjectManager 会建目录，与 Claude 引擎装配 MCP server 一样卸到线程
    arcreel = await asyncio.to_thread(
        build_arcreel_codex_tools, project_name=project_name, data_root=data_root, user_id=user_id
    )
    files = CodexFileTools(policy=policy, project_cwd=project_cwd, user_id=user_id)
    callers: dict[str, Callable[[str, Any], Awaitable[dict[str, Any]]]] = dict.fromkeys(arcreel.names, arcreel.call)
    for name in FILE_TOOL_NAMES:
        callers[name] = _file_caller(files)
    model = (settings.get(CODEX_MODEL_SETTING_KEY) or "").strip() or DEFAULT_CODEX_MODEL
    is_subscription = connection.provider == PROVIDER_CHATGPT_SUBSCRIPTION
    config = CodexSessionConfig(
        codex_home=home,
        project_cwd=project_cwd,
        model=model,
        developer_instructions=developer_instructions,
        tool_specs=[*arcreel.specs, *FILE_TOOL_SPECS],
        tool_callers=callers,
        arcreel_tool_names=arcreel.names,
        skill_roots=(project_cwd / ".claude" / "skills",),
        resume_thread_id=resume_thread_id,
        api_key=None if is_subscription else (connection.api_key or None),
    )
    pricing = AgentPricing(
        multiplier=0.0 if is_subscription else 1.0,
        provider_id=connection.provider,
        provider_credential_id=connection.id,
    )
    return CodexLaunch(config=config, pricing=pricing, auth_source="subscription" if is_subscription else "api_key")


def _file_caller(files: CodexFileTools) -> Callable[[str, Any], Awaitable[dict[str, Any]]]:
    async def call(tool: str, arguments: Any) -> dict[str, Any]:
        return await files.call(tool, arguments if isinstance(arguments, dict) else {})

    return call


__all__ = [
    "AGENT_ENGINES",
    "AGENT_ENGINE_SETTING_KEY",
    "CODEX_CREDENTIAL_SETTING_KEY",
    "CODEX_MODEL_SETTING_KEY",
    "CODEX_PROVIDERS",
    "DEFAULT_AGENT_ENGINE",
    "DEFAULT_CODEX_MODEL",
    "AgentEngine",
    "CodexConnectionMissing",
    "CodexLaunch",
    "build_codex_launch",
    "codex_connection",
    "parse_agent_engine",
]
