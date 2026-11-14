"""旧版 v5→v6 目录交换留下的中间目录的命名约定。

迁移链已不再做目录交换（项目最早从 v19 接起，ADR 0131）；数据根布局迁移仍按这条约定认出
``projects/`` 下的 rollback / staging 遗留目录（``.<项目名>.v6-rollback-<uuid>`` 与
``.<项目名>.v6-<uuid>``），不把它们当成项目。
"""

from __future__ import annotations

import os

_ROLLBACK_INFIX = ".v6-rollback-"
_STAGING_INFIX = ".v6-"
# 两类目录名的后缀都取自 uuid4().hex，反解端据此判定一个隐藏目录是否属于本约定。
_SUFFIX_CHARS = "0123456789abcdef"
_SUFFIX_LENGTH = 32  # uuid4().hex 定长；仅校验字符集会把「恰好以十六进制字符结尾的自定义目录」误判为本约定产物


def _project_name_from_swap_dir(dir_name: str, infix: str) -> str | None:
    """从交换中间目录名反解项目名；不匹配命名约定或名字不安全时返回 None。"""
    if not dir_name.startswith("."):
        return None
    head, separator, suffix = dir_name.rpartition(infix)
    if not separator or len(suffix) != _SUFFIX_LENGTH or not all(char in _SUFFIX_CHARS for char in suffix):
        return None
    name = head[1:]
    if not name or name in {".", ".."} or "/" in name or "\\" in name or os.sep in name:
        return None
    return name


def rollback_project_name(dir_name: str) -> str | None:
    """rollback 目录名 → 项目名；非 rollback 目录返回 None。"""
    return _project_name_from_swap_dir(dir_name, _ROLLBACK_INFIX)


def staging_project_name(dir_name: str) -> str | None:
    """staging 目录名 → 项目名；rollback 目录与非 staging 目录返回 None。"""
    if rollback_project_name(dir_name) is not None:
        return None
    return _project_name_from_swap_dir(dir_name, _STAGING_INFIX)


__all__ = [
    "rollback_project_name",
    "staging_project_name",
]
