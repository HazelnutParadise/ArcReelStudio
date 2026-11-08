"""非 Claude 引擎 client 的共同基底：自己产出 CLI 原始帧、自己管理排队讯息。

:mod:`server.agent_runtime.sdk_frames` 以这个类型辨认它们，改走公开方法，而不是 Claude SDK client 的私有入口。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


class EngineClient:
    """Codex、Grok 引擎 client 的基底。"""

    def raw_frames(self) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    async def cancel_message(self, message_uuid: str) -> bool:
        raise NotImplementedError


__all__ = ["EngineClient"]
