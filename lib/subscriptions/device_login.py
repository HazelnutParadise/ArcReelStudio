"""订阅登录共用的结果类型：device code 登录（ChatGPT、Grok）在后台等用户在浏览器授权，页面轮询结果。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LoginStatus = Literal["pending", "succeeded", "failed"]


class SubscriptionLoginError(Exception):
    """登录没能开始或已不存在。``code`` 是给界面本地化用的稳定键。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class DeviceLoginResult:
    status: LoginStatus
    #: 成功时是要保存的凭证全文：Codex 是 ``auth.json``，Grok 是 ``~/.grok`` 里凭证文件打包成的 JSON
    secret: str | None = None
    #: 成功时用来给连线命名的账号说明，例如 ``someone@example.com (plus)``
    account_label: str | None = None
    error_code: str | None = None
    error_detail: str = ""
