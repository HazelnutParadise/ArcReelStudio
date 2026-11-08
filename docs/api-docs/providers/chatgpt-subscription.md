# chatgpt-subscription

用 ChatGPT 订阅账号经 Codex 登录的连线；凭证放在连线专属的 `CODEX_HOME`，由 Codex 原地刷新。

- 登录：[Codex authentication](https://learn.chatgpt.com/docs/auth)、[Codex app-server](https://learn.chatgpt.com/docs/app-server.md)（`account/login/start` 的 `chatgptDeviceCode`）
- 生图：[Codex image generation](https://learn.chatgpt.com/docs/image-generation.md)
- 代码：`lib/config/registry.py::PROVIDER_REGISTRY["chatgpt-subscription"]`、`lib/agent/codex_app_server.py`、`lib/subscriptions/codex_login.py`、`lib/subscriptions/connection_home.py`
