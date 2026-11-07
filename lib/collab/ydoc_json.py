"""编辑单元内容（JSON）与协作文档（pycrdt / Yjs）互转，以及把新内容以最小差异套进文档。

文档的根是名为 ``unit`` 的 Map，结构规则与前端 ``frontend/src/collab/ydoc-json.ts`` 一致：

- 对象 → ``Map``；清单 → ``Array``；
- 对象上的字符串 → ``Text``，多人可以同时在同一段文字里打字；
- 清单里的字符串（如出场角色名）保持原子值，整项增删；
- 数字、布尔、``None`` 原样存放。

套用新内容（:func:`apply_json`）时只改动有差异的部分：文字按公共前后缀算出变动区间，清单按公共前后缀找出
变动段，长度相同的变动段逐项递归。这样外部改动（Agent、其他接口）插进来时，正在打字的人不会被整段覆盖。

pycrdt 的文字位置按 UTF-8 字节计（Yjs 按 UTF-16 码元计），本模块内部负责换算，调用方只处理 Python 字符串。
"""

from __future__ import annotations

from typing import Any

from pycrdt import Array, Doc, Map, Text

ROOT = "unit"

JSONValue = Any


def new_unit_doc(value: dict[str, JSONValue]) -> Doc:
    """以 ``value`` 为内容新建文档。"""
    doc = Doc()
    root = doc.get(ROOT, type=Map)
    with doc.transaction():
        for key, item in value.items():
            root[key] = _to_shared(item, in_list=False)
    return doc


def unit_root(doc: Doc) -> Map:
    return doc.get(ROOT, type=Map)


def unit_json(doc: Doc) -> dict[str, JSONValue]:
    """文档当前内容的 JSON 形态；整数值的浮点数还原为整数（CRDT 里数字一律存成双精度）。"""
    return _normalize(unit_root(doc).to_py() or {})


def apply_json(doc: Doc, value: dict[str, JSONValue], *, origin: object = None) -> None:
    """把文档改成 ``value``，只改有差异的部分；内容相同时不产生任何更新。"""
    root = unit_root(doc)
    if unit_json(doc) == _normalize(value):
        return
    with doc.transaction(origin=origin):
        _reconcile_map(root, value)


# ── 构建 ─────────────────────────────────────────────────────────


def _to_shared(value: JSONValue, *, in_list: bool) -> Any:
    if isinstance(value, dict):
        return Map({k: _to_shared(v, in_list=False) for k, v in value.items()})
    if isinstance(value, list):
        return Array([_to_shared(v, in_list=True) for v in value])
    if isinstance(value, str) and not in_list:
        return Text(value)
    return value


def _normalize(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ── 套差异 ───────────────────────────────────────────────────────


def _reconcile_map(target: Map, value: dict[str, JSONValue]) -> None:
    for key in [k for k in target if k not in value]:
        del target[key]
    for key, new in value.items():
        if key not in target:
            target[key] = _to_shared(new, in_list=False)
            continue
        current = target[key]
        if not _reconcile_in_place(current, new, in_list=False) and _normalize(_plain(current)) != _normalize(new):
            target[key] = _to_shared(new, in_list=False)


def _reconcile_in_place(current: Any, new: JSONValue, *, in_list: bool) -> bool:
    """能在原有共享类型上改到 ``new`` 时就地修改并返回 True；类型不合时返回 False，交给调用方整项替换。"""
    if isinstance(current, Text) and isinstance(new, str) and not in_list:
        _reconcile_text(current, new)
        return True
    if isinstance(current, Map) and isinstance(new, dict):
        _reconcile_map(current, new)
        return True
    if isinstance(current, Array) and isinstance(new, list):
        _reconcile_array(current, new)
        return True
    return False


def _reconcile_text(text: Text, new: str) -> None:
    old = str(text)
    if old == new:
        return
    start = 0
    limit = min(len(old), len(new))
    while start < limit and old[start] == new[start]:
        start += 1
    old_end, new_end = len(old), len(new)
    while old_end > start and new_end > start and old[old_end - 1] == new[new_end - 1]:
        old_end -= 1
        new_end -= 1
    byte_start = len(old[:start].encode("utf-8"))
    removed = len(old[start:old_end].encode("utf-8"))
    if removed:
        del text[byte_start : byte_start + removed]
    inserted = new[start:new_end]
    if inserted:
        text.insert(byte_start, inserted)


def _reconcile_array(array: Array, new: list[JSONValue]) -> None:
    old = [_normalize(_plain(item)) for item in array]
    target = [_normalize(item) for item in new]
    if old == target:
        return
    start = 0
    limit = min(len(old), len(target))
    while start < limit and old[start] == target[start]:
        start += 1
    old_end, new_end = len(old), len(target)
    while old_end > start and new_end > start and old[old_end - 1] == target[new_end - 1]:
        old_end -= 1
        new_end -= 1
    if old_end - start == new_end - start:
        # 等长的变动段逐项递归：改的是清单里某一项的内容（如某句台词），别人在其他项上的修改不受影响
        for offset in range(old_end - start):
            index = start + offset
            if not _reconcile_in_place(array[index], new[index], in_list=True):
                del array[index]
                array.insert(index, _to_shared(new[index], in_list=True))
        return
    if old_end > start:
        del array[start:old_end]
    for offset, item in enumerate(new[start:new_end]):
        array.insert(start + offset, _to_shared(item, in_list=True))


def _plain(value: Any) -> JSONValue:
    if isinstance(value, Text):
        return str(value)
    if isinstance(value, (Map, Array)):
        return value.to_py()
    return value
