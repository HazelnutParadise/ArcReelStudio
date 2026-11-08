"""Agent 用 Grok 引擎时的会话装配：选哪条连线、它的 HOME、规则、工具与计价（docs/adr/0125）。

Grok 订阅用登录时存下的连线 HOME；xAI API Key 连线（供应商 ``grok``）用自己的持久 HOME，并以 ``XAI_API_KEY`` 认证。
工具与 Codex 引擎同一份，经 :mod:`server.agent_runtime.session_tool_endpoint` 的本机端点交给 Grok。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from lib.agent.agent_auth import AuthSource
from lib.agent.credential_tiers import AgentPricing
from lib.backends.subscription_shared import PROVIDER_GROK_SUBSCRIPTION
from lib.db.models.credential import ProviderCredential
from lib.db.repositories.credential_repository import CredentialRepository
from lib.subscriptions.connection_home import connection_home
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.codex_engine import build_session_tools
from server.agent_runtime.grok_client import GrokSessionConfig
from server.agent_runtime.session_tool_endpoint import SESSION_TOOL_PATH

GROK_CREDENTIAL_SETTING_KEY = "agent_grok_credential_id"
GROK_MODEL_SETTING_KEY = "agent_grok_model"
DEFAULT_GROK_MODEL = "grok-4.6"
#: Grok 引擎可选的模型（Grok CLI 1.0.77 的模型目录）
GROK_MODELS: tuple[str, ...] = ("grok-4.6", "grok-4.5")
#: Grok 引擎能用的连线供应商：Grok 订阅与 xAI API Key
GROK_PROVIDERS = frozenset({PROVIDER_GROK_SUBSCRIPTION, "grok"})


class GrokConnectionMissing(RuntimeError):
    """设定选了 Grok 引擎，但找不到能用的 Grok 订阅或 xAI 连线。"""


@dataclass(frozen=True)
class GrokLaunch:
    config: GrokSessionConfig
    pricing: AgentPricing
    auth_source: AuthSource


async def grok_connection(session: Any, settings: Mapping[str, str]) -> ProviderCredential | None:
    """Grok 会话用的连线：设定指定的那条（须是 Grok 订阅或 xAI），没指定或已删除时取 Grok 订阅的预设连线，再没有时取 xAI 的预设连线。"""
    repo = CredentialRepository(session)
    raw = (settings.get(GROK_CREDENTIAL_SETTING_KEY) or "").strip()
    if raw.isdigit():
        chosen = await repo.get_by_id(int(raw))
        if chosen is not None and chosen.provider in GROK_PROVIDERS:
            return chosen
    for provider in (PROVIDER_GROK_SUBSCRIPTION, "grok"):
        default = await repo.get_active(provider)
        if default is not None:
            return default
    return None


def tool_endpoint_url() -> str:
    """Grok 进程连回本服务的工具端点：取 ``ARCREEL_API_BASE`` 的来源（与内嵌 Agent 呼叫 REST 的位址相同）。"""
    base = os.environ.get("ARCREEL_API_BASE") or "http://127.0.0.1:1241/api/v1"
    parts = urlsplit(base)
    return f"{parts.scheme}://{parts.netloc}{SESSION_TOOL_PATH}"


def _prepare_home(provider_id: str, credential_id: int) -> Path:
    home = connection_home(provider_id, credential_id)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(home, 0o700)
    return home


async def build_grok_launch(
    *,
    project_name: str,
    project_cwd: Path,
    data_root: Path,
    user_id: str,
    policy: AgentAccessPolicy,
    settings: Mapping[str, str],
    connection: ProviderCredential,
    rules: str,
    resume_session_id: str | None,
) -> GrokLaunch:
    home = await asyncio.to_thread(_prepare_home, connection.provider, connection.id)
    specs, callers, arcreel_names = await build_session_tools(
        project_name=project_name, project_cwd=project_cwd, data_root=data_root, user_id=user_id, policy=policy
    )
    model = (settings.get(GROK_MODEL_SETTING_KEY) or "").strip() or DEFAULT_GROK_MODEL
    is_subscription = connection.provider == PROVIDER_GROK_SUBSCRIPTION
    config = GrokSessionConfig(
        grok_home=home,
        project_cwd=project_cwd,
        model=model,
        rules=rules,
        tool_specs=specs,
        tool_callers=callers,
        arcreel_tool_names=arcreel_names,
        tool_endpoint_url=tool_endpoint_url(),
        resume_session_id=resume_session_id,
        api_key=None if is_subscription else (connection.api_key or None),
    )
    pricing = AgentPricing(
        multiplier=0.0 if is_subscription else 1.0,
        provider_id=connection.provider,
        provider_credential_id=connection.id,
    )
    return GrokLaunch(config=config, pricing=pricing, auth_source="subscription" if is_subscription else "api_key")


__all__ = [
    "DEFAULT_GROK_MODEL",
    "GROK_CREDENTIAL_SETTING_KEY",
    "GROK_MODELS",
    "GROK_MODEL_SETTING_KEY",
    "GROK_PROVIDERS",
    "GrokConnectionMissing",
    "GrokLaunch",
    "build_grok_launch",
    "grok_connection",
    "tool_endpoint_url",
]
