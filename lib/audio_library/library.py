"""项目级音频库（BGM、音效）共用的读取规则（``docs/adr/0127``）。

两个库在 ``project.json`` 里的形态一样：一个字段下以条目 ID 为键，值是条目元数据；文件放在 ``<目录>/<ID><扩展名>``。
读取时形态不对的条目一律不计：ID 不合格式、元数据校验不过，或文件路径不是「ID 加允许的扩展名」。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError


class AudioItem(Protocol):
    """一个已登记的音频条目：库里以 ``id`` 为键，文件在 ``file``，``content_digest`` 是登记时的字节指纹。"""

    @property
    def id(self) -> str: ...

    @property
    def file(self) -> str: ...

    @property
    def content_digest(self) -> str: ...


def read_audio_library[Item: AudioItem](
    project: Mapping[str, Any],
    *,
    field: str,
    is_id: Callable[[object], bool],
    validate: Callable[[dict[str, Any]], Item],
    allowed_files: Callable[[str], Iterable[str]],
    order: Callable[[Item], str],
) -> dict[str, Item]:
    """``project[field]`` 里登记的条目，按 ``order`` 排列；形态不对的条目不计。"""
    bucket = project.get(field)
    if not isinstance(bucket, Mapping):
        return {}
    items: list[Item] = []
    for item_id, raw in bucket.items():
        if not is_id(item_id) or not isinstance(raw, Mapping):
            continue
        try:
            item = validate({**raw, "id": item_id})
        except ValidationError:
            continue
        if item.file in set(allowed_files(item.id)):
            items.append(item)
    return {item.id: item for item in sorted(items, key=order)}


def audio_display_name(filename: str, *, max_length: int, fallback: str) -> str:
    """显示名取文件名去掉扩展名，过长截断；取不出时用 ``fallback``。"""
    stem = unicodedata.normalize("NFC", Path(filename).stem).strip()
    return stem[:max_length].strip() or fallback


__all__ = ["AudioItem", "audio_display_name", "read_audio_library"]
