"""Codex 引擎会话的 ArcReel 工具：与 Claude 引擎的 in-process MCP server（:mod:`server.agent_runtime.arcreel_mcp`）同一份
工具集、同一个会话项目 scope、同一种「生成类工具等到批次终态」的 caller，只是以 Codex dynamic tools 交给 app-server。"""

from __future__ import annotations

from pathlib import Path

from lib.db.base import DEFAULT_USER_ID
from lib.generation.generation_queue_client import batch_enqueue_and_wait
from lib.project.project_manager import ProjectManager
from server.agent_toolset.codex_dynamic import CodexDynamicTools, codex_dynamic_tools
from server.agent_toolset.toolset import AGENT_TOOLSET
from server.tool_runtime import CallerContext, ProjectScope, Services


def build_arcreel_codex_tools(
    *,
    project_name: str,
    data_root: Path,
    user_id: str = DEFAULT_USER_ID,
) -> CodexDynamicTools:
    return codex_dynamic_tools(
        AGENT_TOOLSET,
        scope=ProjectScope(project_name=project_name, data_root=data_root),
        caller=CallerContext(user_id=user_id, source="embedded", batch_waiter=batch_enqueue_and_wait),
        services=Services.defaults(ProjectManager(data_root)),
    )


__all__ = ["build_arcreel_codex_tools"]
