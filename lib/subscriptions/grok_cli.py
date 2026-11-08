"""Grok CLI 从哪来：PATH 上有就用；没有时按固定版本与校验和从 x.ai 下载到数据根。

Grok CLI 没有允许再分发的许可，所以不放进镜像；由各部署自己在第一次登录 Grok 订阅时下载官方发布的二进制，等同在
那台机器上执行 xAI 的安装脚本。只支持 Linux（x86_64、aarch64）；其他平台请自行安装并放到 PATH 上。
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import os
import platform
import shutil
import tempfile
from pathlib import Path

import httpx2

from lib.infra.data_root_layout import DataRootLayout

GROK_VERSION = "1.0.77"
#: 官方发布的 ``grok-<版本>-linux-<架构>.gz`` 的 sha256
GROK_SHA256 = {
    "x86_64": "243a669421d0af2c3a56b4283601d8c22815312224feb38a0059396659926250",
    "aarch64": "ad0bdf44d84197f4a746d7f3fb949724c63023b89baefc54a4132303da7bff87",
}
_DOWNLOAD_URL = "https://x.ai/cli/grok-{version}-linux-{arch}.gz"
_ARCH_ALIASES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}

_install_lock = asyncio.Lock()


class GrokCliUnavailable(Exception):
    """这台机器拿不到 Grok CLI（不是 Linux、下载失败或校验和不符）。"""


def installed_grok_path() -> Path:
    return DataRootLayout.current().root / "tools" / f"grok-{GROK_VERSION}" / "grok"


async def ensure_grok_cli(*, client: httpx2.AsyncClient | None = None) -> str:
    """返回可执行的 grok 路径；PATH 上没有时下载固定版本。"""
    on_path = shutil.which("grok")
    if on_path:
        return on_path
    target = installed_grok_path()
    if await asyncio.to_thread(target.is_file):
        return str(target)
    if platform.system() != "Linux":
        raise GrokCliUnavailable("grok CLI is not on PATH; install it from https://x.ai/cli on this platform")
    arch = _ARCH_ALIASES.get(platform.machine().lower())
    if arch is None:
        raise GrokCliUnavailable(f"unsupported architecture: {platform.machine()}")
    async with _install_lock:
        if await asyncio.to_thread(target.is_file):
            return str(target)
        url = _DOWNLOAD_URL.format(version=GROK_VERSION, arch=arch)
        owned = client is None
        http = client or httpx2.AsyncClient(timeout=httpx2.Timeout(300.0, connect=15.0), follow_redirects=True)
        try:
            response = await http.get(url)
            response.raise_for_status()
            payload = response.content
        except httpx2.HTTPError as exc:
            raise GrokCliUnavailable(f"failed to download grok CLI: {exc}") from exc
        finally:
            if owned:
                await http.aclose()
        await asyncio.to_thread(_install, payload, GROK_SHA256[arch], target)
    return str(target)


def _install(payload: bytes, expected_sha256: str, target: Path) -> None:
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise GrokCliUnavailable("grok CLI download failed checksum verification")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".grok-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(gzip.decompress(payload))
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
