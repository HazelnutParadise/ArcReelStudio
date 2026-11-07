"""Agent 会话用哪种认证：Claude 订阅（长效 OAuth 令牌）还是 API Key。

选择在会话连接时做一次，这段连接的轮次都用它。「优先」模式下，正在用的一方额度用完或认证失败时记下
不可用，下一段连接改用另一方；额度窗口重置（或重新登录订阅）后回到优先的一方。不可用标记只存在进程内存里，
服务重启后重新从优先的一方开始，用完了会再标记一次。
"""

from __future__ import annotations

import threading
import time
from typing import Literal, cast, get_args

AuthMode = Literal["api_key", "subscription", "prefer_subscription", "prefer_api_key"]
AuthSource = Literal["api_key", "subscription"]

AUTH_MODES: tuple[AuthMode, ...] = get_args(AuthMode)
DEFAULT_AUTH_MODE: AuthMode = "prefer_subscription"
#: system_settings 里保存认证方式的键
AUTH_MODE_SETTING_KEY = "agent_auth_mode"
#: 额度用完但 CLI 没报重置时间时，多久后再试回优先的一方
DEFAULT_RETRY_AFTER_SECONDS = 60 * 60


def parse_auth_mode(raw: str | None) -> AuthMode:
    value = (raw or "").strip()
    return cast("AuthMode", value) if value in AUTH_MODES else DEFAULT_AUTH_MODE


class AuthAvailability:
    """进程内记录哪一方暂时不能用。``until`` 为 ``None`` 表示要等重新配置（例如订阅令牌失效）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._marks: dict[AuthSource, float | None] = {}

    def mark_unavailable(self, source: AuthSource, *, until: float | None) -> None:
        with self._lock:
            self._marks[source] = until

    def clear(self, source: AuthSource) -> None:
        with self._lock:
            self._marks.pop(source, None)

    def unavailable_until(self, source: AuthSource, *, now: float | None = None) -> float | None:
        """不可用时返回到期时间（等重新配置时为 ``inf``），可用时返回 ``None``；过期的标记顺手清掉。"""
        current = time.time() if now is None else now
        with self._lock:
            if source not in self._marks:
                return None
            until = self._marks[source]
            if until is None:
                return float("inf")
            if until <= current:
                del self._marks[source]
                return None
            return until

    def is_available(self, source: AuthSource, *, now: float | None = None) -> bool:
        return self.unavailable_until(source, now=now) is None


#: 整个进程共用的一份标记
auth_availability = AuthAvailability()


def _preferred_and_other(mode: AuthMode) -> tuple[AuthSource, AuthSource]:
    if mode in ("subscription", "prefer_subscription"):
        return "subscription", "api_key"
    return "api_key", "subscription"


def choose_auth_source(
    mode: AuthMode,
    *,
    has_api_key: bool,
    has_subscription: bool,
    availability: AuthAvailability = auth_availability,
    now: float | None = None,
) -> AuthSource:
    """按认证方式与目前配置挑这次连接用哪一方。

    「只用」模式不切换。「优先」模式下优先的一方没配置或暂时不可用、而另一方已配置且可用时改用另一方；两边都
    不可用时仍用优先的一方，让 CLI 照实报错。什么都没配时走 API Key 路径（回落到系统设置），与以往一致。
    """
    if mode == "api_key":
        return "api_key"
    if mode == "subscription":
        return "subscription"
    preferred, other = _preferred_and_other(mode)
    configured = {"api_key": has_api_key, "subscription": has_subscription}
    if not configured[preferred] and not configured[other]:
        return "api_key"
    preferred_ok = configured[preferred] and availability.is_available(preferred, now=now)
    if preferred_ok:
        return preferred
    if configured[other] and availability.is_available(other, now=now):
        return other
    return preferred if configured[preferred] else other


def fallback_source(
    mode: AuthMode, current: AuthSource, *, has_api_key: bool, has_subscription: bool
) -> AuthSource | None:
    """``current`` 不能用时这个模式允许改用的另一方；「只用」模式或另一方没配置时为 ``None``。"""
    if mode not in ("prefer_subscription", "prefer_api_key"):
        return None
    other: AuthSource = "api_key" if current == "subscription" else "subscription"
    configured = has_api_key if other == "api_key" else has_subscription
    return other if configured else None
