"""订阅连线的凭证放在哪里、怎么放。

Claude 订阅的长效令牌不会刷新，存在 ``provider_credential.api_key``。ChatGPT（Codex）与 Grok 的凭证会被 CLI 自己
刷新，所以放在连线专属的 HOME（:meth:`DataRootLayout.subscription_home`），用这条连线的进程都以它为 HOME，让 CLI
原地刷新；数据库不存这两家的凭证，也就没有「各自复制、各自刷新、互相覆盖」的问题。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from lib.infra.data_root_layout import DataRootLayout
from lib.subscriptions.grok_login import restore_grok_credentials

#: 凭证放在连线 HOME 里的供应商
HOME_BASED_PROVIDERS = frozenset({"chatgpt-subscription", "grok-subscription"})


def connection_home(provider_id: str, credential_id: int) -> Path:
    return DataRootLayout.current().subscription_home(provider_id, credential_id)


def install_credentials(provider_id: str, credential_id: int, secret: str) -> Path:
    """把登录换来的凭证放进连线 HOME（会先清空旧内容，重新登录同一账号时用新凭证），返回该目录。"""
    if provider_id not in HOME_BASED_PROVIDERS:
        raise ValueError(f"{provider_id} keeps its credential in the database")
    home = connection_home(provider_id, credential_id)
    if home.exists():
        shutil.rmtree(home)  # hard-delete: out-of-scope -- 同一连线重新登录，旧凭证作废
    home.mkdir(parents=True, mode=0o700)
    os.chmod(home, 0o700)
    if provider_id == "chatgpt-subscription":
        target = home / "auth.json"
        target.write_text(secret, encoding="utf-8")
        target.chmod(0o600)
    else:
        restore_grok_credentials(secret, str(home))
    return home


def remove_credentials(provider_id: str, credential_id: int) -> None:
    """删除连线时一并删掉它的 HOME；没有时什么都不做。"""
    if provider_id not in HOME_BASED_PROVIDERS:
        return
    shutil.rmtree(
        connection_home(provider_id, credential_id), ignore_errors=True
    )  # hard-delete: out-of-scope -- 连线已删除，凭证不属于项目
