"""用 Grok 订阅跑一次性的一轮文字：经 ``grok agent stdio``（ACP，JSON-RPC 2.0 over stdio）。

流程（xAI 文档 https://docs.x.ai/build/cli/headless-scripting.md 的 ACP 一节）：
1. 起 ``grok --no-auto-update [-m <model>] agent stdio``，环境里 ``HOME`` 是连线专属的 HOME（凭证在其中的 ``.grok``）。
2. 发 ``initialize``（``protocolVersion: 1``、``clientCapabilities: {}``），再发 ``session/new``（``cwd`` 是临时工作目录、
   ``mcpServers: []``），拿 ``sessionId``。
3. 发 ``session/prompt``（``sessionId``、``prompt: [{"type": "text", "text": ...}]``）；回复文字以 ``session/update`` 通知
   陆续到达（``params.update.sessionUpdate == "agent_message_chunk"`` 时取 ``params.update.content.text``，按到达顺序拼接），
   ``session/prompt`` 的响应带 ``stopReason`` 表示这一轮结束。
4. 服务器发来的请求（例如 ``session/request_permission``、``fs/*``）一律拒绝：回 JSON-RPC 错误 ``-32601``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: 一轮最长等多久
DEFAULT_TURN_TIMEOUT_SECONDS = 10 * 60.0


class GrokTurnError(Exception):
    """这一轮没有完成。``code``：``cli_unavailable``（起不了进程）、``auth_required``（未登录或凭证失效）、
    ``usage_limit``（额度用完）、``timeout``、``empty_output``（没有任何回复文字）、``None``（其他）。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class GrokTurnResult:
    text: str
    stop_reason: str | None = None


async def run_grok_turn(
    grok_home: Path,
    prompt: str,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    cli_path: str | None = None,
    timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,  # noqa: ASYNC109 -- 一轮的等待上限，由 asyncio.wait_for 实现；仓库无 trio/anyio cancel scope
) -> GrokTurnResult:
    """跑一轮并返回拼好的回复文字。

    - ``system_prompt`` 非空时放在 ``prompt`` 前面，中间空一行，作为同一段文字送出。
    - ``cli_path`` 为 None 时用 PATH 上的 ``grok``，找不到就抛 ``GrokTurnError(code="cli_unavailable")``。
    - 进程的环境只带 ``HOME``（= ``grok_home``）、``PATH``、``LANG``，不继承其他环境变量。
    - 收到 JSON-RPC 错误或进程提前结束：错误讯息含 "sign" / "auth" / "login" 时 ``code="auth_required"``，含
      "limit" / "quota" / "rate" 时 ``code="usage_limit"``，其他 ``code=None``。
    - 超过 ``timeout``：``code="timeout"``。回复文字为空：``code="empty_output"``。
    - 不论成败，结束前都结束子进程并删除临时工作目录。
    """
    raise NotImplementedError
