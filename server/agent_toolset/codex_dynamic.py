"""ArcReel Agent 的 Codex 引擎 adapter：把 Agent 工具集声明交给 ``codex app-server`` 当 dynamic tools。

与内嵌 Claude adapter（:mod:`server.agent_toolset.embedded`）同一套声明、scope 与 caller：项目由会话决定，schema
不含 ``project``；生成类工具等到批次终态再返回。Codex 呼叫时 app-server 发 ``item/tool/call``，这里按工具名执行，
回 ``{"contentItems": [...], "success": bool}``：文字块照 envelope 顺序，图片块以 data URL 排在最后。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from server.agent_toolset.declaration import (
    AgentToolDeclaration,
    UnscopedToolDeclaration,
    invoke_declaration,
    invoke_unscoped_declaration,
    tool_description,
)
from server.agent_toolset.envelope import encode_outcome
from server.tool_runtime import CallerContext, ProjectScope, Services

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexDynamicTools:
    """``thread/start.dynamicTools`` 的工具清单与 ``item/tool/call`` 的处理函数。"""

    specs: list[dict[str, Any]]
    _declared: Mapping[str, AgentToolDeclaration]
    _scope: ProjectScope
    _caller: CallerContext
    _services: Services

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._declared)

    async def call(self, tool: str, arguments: Any) -> dict[str, Any]:
        declaration = self._declared.get(tool)
        if declaration is None:
            return _error(f"Tool '{tool}' not found")
        args = arguments if isinstance(arguments, dict) else {}
        try:
            if isinstance(declaration, UnscopedToolDeclaration):
                outcome = await invoke_unscoped_declaration(declaration, args, self._caller, self._services)
            else:
                outcome = await invoke_declaration(declaration, args, self._scope, self._caller, self._services)
        except Exception as exc:
            logger.exception("Codex dynamic tool %s 抛出意外异常", tool)
            return _error(str(exc))
        envelope = encode_outcome(declaration, outcome)
        items: list[dict[str, Any]] = [{"type": "inputText", "text": text} for text in envelope.texts]
        items += [
            {"type": "inputImage", "imageUrl": f"data:{image.mime_type};base64,{image.base64_data}"}
            for image in envelope.images
        ]
        return {"contentItems": items, "success": not envelope.is_error}


def codex_dynamic_tools(
    declarations: Iterable[AgentToolDeclaration],
    *,
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
) -> CodexDynamicTools:
    declared = {declaration.name: declaration for declaration in declarations}
    specs = [
        {
            "type": "function",
            "name": declaration.name,
            "description": tool_description(declaration),
            "inputSchema": declaration.input_schema,
        }
        for declaration in declared.values()
    ]
    return CodexDynamicTools(specs=specs, _declared=declared, _scope=scope, _caller=caller, _services=services)


def _error(text: str) -> dict[str, Any]:
    return {"contentItems": [{"type": "inputText", "text": text}], "success": False}


__all__ = ["CodexDynamicTools", "codex_dynamic_tools"]
