---
status: accepted
---

# Grok 引擎经本机会话端点拿到工具

Agent 要能用 Grok 订阅或 xAI API Key 跑。Grok 订阅只能经官方 Grok CLI 使用，所以第三个引擎驱动 `grok agent stdio`（ACP），接缝与帧协定沿用 ADR 0124：`server/agent_runtime/grok_client.py` 的 `GrokAgentClient` 继承 `EngineClient`，产出 Claude CLI 的原始帧。决定如下。

**工具经本机 HTTP MCP 端点**：ACP 只能经 MCP 接客户端的工具，Grok CLI 的 MCP 能力是 HTTP 与 SSE。`server/agent_runtime/session_tool_endpoint.py` 在 `POST /internal/agent-tools` 开一个 MCP streamable HTTP 端点（只回 JSON，不开 SSE）；每个会话登记一组工具与一个随机令牌，`session/new` 以 HTTP MCP 把网址与 `Authorization: Bearer` 交给 Grok。端点只接受本机连线，会话结束即作废令牌。工具与 Codex 引擎同一份（`build_session_tools`），在本进程执行，scope、caller 与等待批次都与 Claude 引擎相同。Grok 的 `x.ai/mcp/sdk` 看起来能把工具呼叫转回客户端，但没有公开文件，不采用。

**tool_use / tool_result 由端点回呼产生**：端点在呼叫前后通知 client，client 写出带同一个呼叫 id 的两个帧，不依赖 Grok 的 `tool_call` 更新格式。

**Grok 自带工具多层关闭**：`--disallowed-tools` 移除 xAI 内建文件列出的档案、命令、子 Agent 与网路工具，加 `--no-subagents`、`--disable-web-search`；连线 HOME 的 `.grok/config.toml` 写入权限 deny 规则；Grok 来要权限（`session/request_permission`）时只批准 ArcReel 工具，其余拒绝；不声明 `fs`、`terminal` 客户端能力。这几层要等真的 Grok 帐号才能验证实际效果（未登入时 Grok 不开会话，看不到给模型的工具清单），所以 Grok 引擎在验证前标为实验性。

**规则与会话**：语言规则、项目上下文与使用者记忆经 `--rules` 附加；会话 id 即 ACP `sessionId`，恢复先用 `session/resume`，不支援时退回 `session/load` 并丢掉回放的更新。xAI API Key 连线（供应商 `grok`）经 `XAI_API_KEY` 认证，用自己的持久 HOME。

**v1 不支援**：与 Codex 引擎相同（ADR 0124）。用量：ACP 的 prompt 响应不带 token 数，Grok 会话只记录呼叫，不记 token。
