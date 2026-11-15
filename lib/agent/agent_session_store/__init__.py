"""Agent SessionStore — SDK transcript mirror to project DB."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from lib.agent.agent_session_store.models import AgentSessionEntry, AgentSessionSummary

_ENV_VAR = "ARCREEL_SDK_SESSION_STORE"
_VALID_MODES = frozenset({"db", "off", ""})

logger = logging.getLogger("arcreel.session_store.config")

FlushMode = Literal["eager", "batched"]

_FLUSH_ENV_VAR = "ARCREEL_SDK_SESSION_STORE_FLUSH"
_VALID_FLUSH_MODES = frozenset({"eager", "batched"})


def make_project_key(project_cwd: Path | str) -> str:
    """Derive the SessionStore project_key for a project cwd.

    Thin wrapper around SDK's public ``project_key_for_directory`` so adapter
    callers and SDK live-mirror writes agree on the key. SDK import is local
    so module-level callers (`session_store_enabled` in app.py lifespan) stay
    importable when claude_agent_sdk is missing.
    """
    from claude_agent_sdk import project_key_for_directory

    return project_key_for_directory(str(project_cwd))


def default_sdk_config_dir() -> Path:
    """Claude SDK 的配置目录：数据根下应用自己的目录（:attr:`DataRootLayout.claude_agent_config_dir`）。

    Claude 引擎进程以它为 ``CLAUDE_CONFIG_DIR``，本地会话数据在其下的 ``projects/``。不读宿主环境，也从不指向
    宿主用户的 ``~/.claude``；旧版写在宿主 ``~/.claude`` 里的会话不迁移（这个分支从未部署）。
    """
    from lib.infra.data_root_layout import DataRootLayout

    return DataRootLayout.current().claude_agent_config_dir


def pin_sdk_config_dir() -> Path:
    """把本进程的 ``CLAUDE_CONFIG_DIR`` 钉到应用目录并建好它，返回该目录。

    SDK 的本地文件读取（``list_sessions``、``get_session_messages``，会话存储关闭时的读取路径与启动时的本地导入）
    只认进程环境，不收参数；不钉的话它们会去读宿主用户的 ``~/.claude``。服务启动时调用一次。
    """
    config_dir = default_sdk_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(config_dir, 0o700)
    os.environ["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return config_dir


def session_store_enabled() -> bool:
    """True when ARCREEL_SDK_SESSION_STORE is anything but 'off' (case-insensitive).

    Single source of truth for the kill-switch parsed at every read site
    (lifespan migration, SessionManager). Unknown values default to enabled
    with a warning in callers that care to log it.
    """
    mode = os.getenv(_ENV_VAR, "db").strip().lower()
    return mode != "off"


def session_store_mode() -> str:
    """Return the raw normalized mode string (`db`, `off`, or other)."""
    return os.getenv(_ENV_VAR, "db").strip().lower()


def is_known_session_store_mode(mode: str) -> bool:
    return mode in _VALID_MODES


def session_store_flush_mode() -> FlushMode:
    """Return SDK ClaudeAgentOptions.session_store_flush value.

    Defaults to "eager" so transcript writes are durable across crashes
    and visible mid-turn for reconnect snapshots. Set
    ARCREEL_SDK_SESSION_STORE_FLUSH=batched for the legacy end-of-turn
    flush behavior (rollback path).
    """
    raw = os.getenv(_FLUSH_ENV_VAR, "").strip().lower()
    if raw == "batched":
        return "batched"
    if raw and raw not in _VALID_FLUSH_MODES:
        logger.warning(
            "Unknown %s=%r; defaulting to eager",
            _FLUSH_ENV_VAR,
            raw,
        )
    return "eager"


__all__ = [
    "AgentSessionEntry",
    "AgentSessionSummary",
    "default_sdk_config_dir",
    "is_known_session_store_mode",
    "make_project_key",
    "pin_sdk_config_dir",
    "session_store_enabled",
    "session_store_flush_mode",
    "session_store_mode",
]
