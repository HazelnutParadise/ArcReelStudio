# grok-subscription

用 Grok 订阅账号经 Grok CLI 登录的连线；凭证放在连线专属的 HOME（`~/.grok`），由 CLI 原地刷新。

- 登录与 CLI：[Grok CLI reference](https://docs.x.ai/build/cli/reference.md)（`grok login --device-auth`）、[Headless & scripting](https://docs.x.ai/build/cli/headless-scripting.md)
- 订阅额度：[Grok FAQ](https://docs.x.ai/grok/faq.md)、[Use Grok in OpenCode](https://x.ai/news/grok-opencode)
- 代码：`lib/config/registry.py::PROVIDER_REGISTRY["grok-subscription"]`、`lib/subscriptions/grok_login.py`、`lib/subscriptions/connection_home.py`
