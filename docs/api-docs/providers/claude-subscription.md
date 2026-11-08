# claude-subscription

用 Claude 订阅账号登录的连线，目前只供 ArcReel Agent 使用。

- 登录：[Claude Code authentication](https://code.claude.com/docs/en/authentication)（`claude setup-token` 换一年期 OAuth 令牌，只能发模型请求）
- 条款：[Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)、[Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- 代码：`lib/config/registry.py::PROVIDER_REGISTRY["claude-subscription"]`、`lib/subscriptions/claude_login.py`、`lib/config/service.py::agent_claude_subscription`
