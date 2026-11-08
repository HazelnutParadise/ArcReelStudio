"""订阅额度后端共用的错误与供应商 id：订阅只能经各家官方 CLI 使用，额度用完或要重新登录时抛错且不重试。"""

from __future__ import annotations

from lib.infra.retry import NonRetryableError

PROVIDER_CLAUDE_SUBSCRIPTION = "claude-subscription"
PROVIDER_CHATGPT_SUBSCRIPTION = "chatgpt-subscription"
PROVIDER_GROK_SUBSCRIPTION = "grok-subscription"


class SubscriptionCallError(NonRetryableError):
    """订阅这一轮没有完成。``code``：``usage_limit``（额度用完）、``auth_required``（要重新登录）、其他。"""

    def __init__(self, message: str, *, provider: str, code: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
