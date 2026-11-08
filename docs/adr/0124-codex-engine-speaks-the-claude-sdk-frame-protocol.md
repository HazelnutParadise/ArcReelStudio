---
status: accepted
---

# Codex 引擎说 Claude SDK 的帧协定

Agent 要能用 ChatGPT 订阅或 OpenAI API Key 跑。订阅只能经官方客户端使用（ADR 0123），所以第二个引擎驱动官方 `codex app-server`。决定如下。

**接缝在 client，不在会话层**：`SessionActor` 只依赖 client 的 `query`、`interrupt` 与 `sdk_frames` 的两个入口。`server/agent_runtime/codex_client.py` 的 `CodexAgentClient` 实作同样的介面，并把 Codex 的通知转成 Claude CLI 的原始帧（`system/init`、`assistant`、`user` 工具结果、`result`、`session_state_changed`、`command_lifecycle`），由 SDK 自己的 `parse_message` 解析。事件日志、用量、改动通知与前端都不分引擎。`sdk_frames` 对 Codex client 走它的公开方法，不假造 SDK 私有属性。

**工具用 dynamicTools，在本进程跑**：`thread/start.dynamicTools` 交出 `AGENT_TOOLSET`（`server/agent_toolset/codex_dynamic.py`），呼叫经 `item/tool/call` 回到本进程，scope、caller 与「生成类工具等到批次终态」都与 Claude 引擎的 in-process MCP 相同。不走 `/mcp`：那条路要签发新的会话凭证、修改 ADR 0065，且远端工具不等批次。dynamicTools 是 app-server 的实验 API，靠 ADR 0123 固定的 CLI 版本控制风险。

**Codex 自带工具全部关掉**：`features.shell_tool` 等设为关闭，沙盒 `read-only`、不批准任何请求。档案读写改由 `codex_file_tools.py` 的 Read/Write/Edit/Glob/Grep 提供，每次都过 `AgentAccessPolicy.check_path_access`，Glob/Grep 列出的每个档案也要通过；Codex 的 `workspace-write` 只限写、不限读，挡不住读其他项目。

**指引与技能用原生机制**：`project_doc_fallback_filenames=["CLAUDE.md"]` 让 Codex 载入物化到项目的 `CLAUDE.md`，`skills/extraRoots/set` 指到 `.claude/skills`；语言规则、项目上下文与使用者记忆放 `developerInstructions`，与 Claude 引擎的 append prompt 同一份。

**排队与中断由 client 模拟**：Codex 在轮次进行中再 `turn/start` 是并入当前轮，不是排队，所以 client 自己持有佇列、发 `command_lifecycle`；中断用 `turn/interrupt` 加记下的 turn id。

**会话记住引擎**：`agent_sessions.engine`；新会话照设定 `agent_engine`，恢复照会话自己的引擎，`thread/resume` 用存下的 thread id。ChatGPT 订阅用登录时的连线 HOME；OpenAI API Key 连线用自己的持久 HOME 并以 apiKey 登入，重启后才能恢复。用量记在连线的供应商与 id 名下，订阅倍率 0。

**v1 不支援**：从较早的讯息改写分叉、AskUserQuestion、唯读审查子 Agent、订阅与 API Key 之间的自动切换（只在 Claude 引擎）。
