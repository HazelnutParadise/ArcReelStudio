---
status: accepted
---

# Claude 引擎只用应用选定的连线：没有连线不启动，CLI 用数据根下自己的配置目录

Claude 引擎原本只把 `ANTHROPIC_*` 置空，CLI 的配置目录仍是宿主用户的 `~/.claude`。没有生效的 Agent 连线时，CLI 会退回宿主用户自己的 Claude Code 登录（macOS 钥匙圈、`~/.claude` 里的凭证与 `apiKeyHelper`），设置页写着 Agent 无法对话，实际却在用别人的账号产生费用。决定：

- **没有可用连线就不启动**：Claude 引擎没有 API Key、订阅令牌或网关地址，Codex、Grok 引擎找不到连线时，发送、接续与改写在起任何进程之前就被拒绝（`AgentConnectionMissing`，HTTP 409 `agent_connection_missing`）。改写先查连线，再中断运行中的轮次。
- **配置目录属于应用**：每个 Claude 引擎进程都以数据根下的 `runtime/claude-agent-config`（`DataRootLayout.claude_agent_config_dir`）为 `CLAUDE_CONFIG_DIR`；服务启动时把本进程的 `CLAUDE_CONFIG_DIR` 钉到同一目录，SDK 的本地会话读写、键对齐与项目恢复时的改键、tool-results 读放行都以它为准。lib 与 server 不再读写宿主的 `~/.claude`。
- **宿主环境按前缀围堵**：SDK 把整个父进程环境传给 CLI，只用 `options.env` 覆盖。凡 `ANTHROPIC_`、`CLAUDE_CODE_` 前缀、应用没有自己设值的变量一律置空（名单维护在 `lib/config/env_keys.py`），只放行 `CLAUDE_CODE_GIT_BASH_PATH` 这类找程序用的变量。
- 应用内登录的 Claude 订阅令牌存在数据库，经 `CLAUDE_CODE_OAUTH_TOKEN` 注入，不受配置目录影响。

## Considered Options

- **切换 HOME**：Codex、Grok 引擎这样做，但 Claude 引擎的 Bash 工具与 skill 脚本依赖真实 HOME；`CLAUDE_CONFIG_DIR` 已足以让 CLI 读不到宿主的登录与设置，SDK 也说明改了它钥匙圈服务名会换掉。
- **把宿主 `~/.claude` 里的旧会话复制过来**：这个分支从未部署，没有需要保留的旧会话；复制还会读进宿主用户的个人历史。不迁移。

## Consequences

- 取代 `docs/adr/0074` 中「不切 `CLAUDE_CONFIG_DIR`」与「`claude_projects_dir` 的 tool-results 读例外不改」两条；记忆目录的重定向方式不变。
- 机器级的受管设置（macOS `/Library/Application Support/ClaudeCode/managed-settings.json`、Linux `/etc/claude-code/`）由 CLI 按策略强制加载，不受配置目录与 `setting_sources` 影响，应用无法关掉；需要时由机器管理员处理。
- Docker 部署里挂到 `/root/.claude` 的 `claude_data/` 不再被 Agent 使用，会话数据随数据根保存。
