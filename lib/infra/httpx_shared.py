"""共享 httpx2 AsyncClient 单例。

由 server/app.py 的 lifespan 在启动时初始化、关闭时释放，避免每次外部请求
都新建客户端、损失连接池复用。调用方使用 `get_http_client()` 获取实例。
"""

from __future__ import annotations

import httpx2

_client: httpx2.AsyncClient | None = None


def get_http_client() -> httpx2.AsyncClient:
    if _client is None:
        raise RuntimeError("httpx2 client not initialized; call startup_http_client() first")
    return _client


async def startup_http_client(timeout: float = 5.0) -> None:  # noqa: ASYNC109 -- httpx2.AsyncClient 的 I/O 超时配置，非 async 取消 deadline
    global _client
    if _client is None:
        _client = httpx2.AsyncClient(timeout=timeout)


async def shutdown_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
