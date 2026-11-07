"""ArcReel Agent（内嵌 Claude Agent SDK）adapter。

项目由会话决定，schema 不含 ``project``；无 scope 声明不接会话项目。结构化结果以 JSON 文本块写进 content、
排在摘要之后，不依赖 ``structuredContent`` 是否会被转给模型；图片块（如有）排在最后。

内嵌 server 关闭 MCP 层的 inputSchema 预校验：已声明工具的参数一律由请求模型校验，
坏参数与远程宿主一样得到 ``invalid_request`` problem，而不是 MCP 的纯文本校验错误。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from claude_agent_sdk import McpSdkServerConfig
from mcp import types
from mcp.server import Server

from server.agent_toolset.declaration import (
    AgentToolDeclaration,
    UnscopedToolDeclaration,
    invoke_declaration,
    invoke_unscoped_declaration,
    tool_description,
)
from server.agent_toolset.envelope import encode_outcome
from server.tool_runtime import CallerContext, ProjectScope, Services, ToolOutcome

logger = logging.getLogger(__name__)


def embedded_result(declaration: AgentToolDeclaration, outcome: ToolOutcome[Any]) -> types.CallToolResult:
    envelope = encode_outcome(declaration, outcome)
    return types.CallToolResult(
        content=[
            *(types.TextContent(type="text", text=text) for text in envelope.texts),
            *(
                types.ImageContent(type="image", data=image.base64_data, mime_type=image.mime_type)
                for image in envelope.images
            ),
        ],
        is_error=envelope.is_error,
    )


def embedded_server(
    declarations: Iterable[AgentToolDeclaration],
    *,
    name: str,
    version: str,
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
) -> McpSdkServerConfig:
    """以会话项目暴露已声明工具的 in-process MCP server。"""
    declared = {declaration.name: declaration for declaration in declarations}
    listed = types.ListToolsResult(
        tools=[
            types.Tool(
                name=declaration.name,
                description=tool_description(declaration),
                input_schema=declaration.input_schema,
            )
            for declaration in declared.values()
        ]
    )

    async def on_list_tools(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        del ctx, params
        return listed

    async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        del ctx
        declaration = declared.get(params.name)
        # 低层 Server 不再把处理函数的异常转成 is_error 结果；未知工具与意外异常在此转换，模型照旧读到错误文本
        if declaration is None:
            return _error_result(f"Tool '{params.name}' not found")
        arguments = params.arguments or {}
        try:
            if isinstance(declaration, UnscopedToolDeclaration):
                outcome = await invoke_unscoped_declaration(declaration, arguments, caller, services)
            else:
                outcome = await invoke_declaration(declaration, arguments, scope, caller, services)
        except Exception as exc:
            logger.exception("内嵌工具 %s 抛出意外异常", params.name)
            return _error_result(str(exc))
        return embedded_result(declaration, outcome)

    # 不传 get_tool_input_schema：低层 Server 不做 inputSchema 预校验，参数由声明的请求模型校验
    server = Server(name, version=version, on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    return McpSdkServerConfig(type="sdk", name=name, instance=server)


def _error_result(text: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)


__all__ = ["embedded_result", "embedded_server"]
