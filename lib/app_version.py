"""应用版本与兼容的上游 ArcReel 版本。

应用版本取自仓库根的 ``pyproject.toml``（release-please 维护），是本 fork 自己的版本号，用于显示与发版。
官方模型目录和市场条目的 ``min_app_version`` 按上游 ArcReel 的版本号标注，与之比较的是
:data:`UPSTREAM_COMPAT_VERSION`，见 ADR 0136。
"""

from __future__ import annotations

import functools
import tomllib
from pathlib import Path
from typing import Final

#: 本 fork 已包含其内容的上游 ArcReel 版本，用来和目录、市场里的 ``min_app_version`` 比较。
#: 从上游同步代码后按 ADR 0136 的步骤更新；不随本 fork 发版改动。
UPSTREAM_COMPAT_VERSION: Final = "0.35.1"

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def load_app_version(pyproject_path: Path) -> str:
    """从给定 pyproject 读版本号；不缓存。读不到或为空时抛错。"""
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    version = str(data["project"]["version"]).strip()
    if not version:
        raise RuntimeError("project.version is empty")
    return version


@functools.cache
def app_version() -> str:
    """当前应用版本，进程内只读一次。"""
    return load_app_version(PYPROJECT_PATH)


def reset_for_tests() -> None:
    """清掉 :func:`app_version` 的进程级缓存，只供测试使用。"""
    app_version.cache_clear()


def upstream_compat_version() -> str:
    """与 ``min_app_version`` 比较时使用的上游 ArcReel 版本。"""
    return UPSTREAM_COMPAT_VERSION
