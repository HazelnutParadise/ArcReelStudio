"""编辑单元内容与协作文档的互转：对象、清单、文字都能多人同时改，外部改动只套差异。"""

from __future__ import annotations

from pycrdt import Doc, Map, Text

from lib.collab.ydoc_json import apply_json, new_unit_doc, unit_json


def _doc(value: dict) -> Doc:
    return new_unit_doc(value)


def test_round_trips_nested_json_and_keeps_integers() -> None:
    value = {
        "synopsis": "第一章",
        "duration_seconds": 5,
        "ratio": 2.5,
        "segment_break": True,
        "note": None,
        "characters": ["Alice", "Bob"],
        "image_prompt": {"scene": "雨夜", "lighting": "冷光"},
        "utterances": [{"speaker": "Alice", "text": "你好"}],
    }

    assert unit_json(_doc(value)) == value
    assert isinstance(unit_json(_doc(value))["duration_seconds"], int)


def test_strings_on_objects_become_shared_text_but_list_items_stay_atomic() -> None:
    doc = _doc({"synopsis": "abc", "characters": ["Alice"]})
    unit = doc.get("unit", type=Map)

    assert isinstance(unit["synopsis"], Text)
    assert unit["characters"].to_py() == ["Alice"]


def test_text_change_only_touches_the_changed_span_so_concurrent_typing_merges() -> None:
    server = _doc({"synopsis": "你好世界"})
    client = Doc()
    client.apply_update(server.get_update())

    # 客户端在开头打字的同时，服务端把外部改动（结尾加字）套进来
    client_unit = client.get("unit", type=Map)
    client_unit["synopsis"].insert(0, "嗨，")
    apply_json(server, {"synopsis": "你好世界！"})

    client.apply_update(server.get_update())
    server.apply_update(client.get_update())

    assert unit_json(server)["synopsis"] == "嗨，你好世界！"
    assert unit_json(client)["synopsis"] == "嗨，你好世界！"


def test_text_diff_handles_multibyte_characters_in_the_middle() -> None:
    doc = _doc({"synopsis": "雨夜的街道"})

    apply_json(doc, {"synopsis": "雨夜😀的老街道"})

    assert unit_json(doc)["synopsis"] == "雨夜😀的老街道"


def test_keys_are_added_removed_and_replaced() -> None:
    doc = _doc({"a": "x", "b": 1, "c": {"d": "e"}})

    apply_json(doc, {"a": "x", "c": "now text", "f": [1, 2]})

    assert unit_json(doc) == {"a": "x", "c": "now text", "f": [1, 2]}


def test_list_items_of_equal_length_are_reconciled_in_place() -> None:
    server = _doc({"utterances": [{"text": "早安"}, {"text": "晚安"}]})
    client = Doc()
    client.apply_update(server.get_update())
    unit = client.get("unit", type=Map)
    # 客户端改第一句，服务端同时改第二句，两边都保留
    # pycrdt 的文字位置按 UTF-8 字节计：「早安」占 6 个字节
    unit["utterances"][0]["text"].insert(6, "啊")
    apply_json(server, {"utterances": [{"text": "早安"}, {"text": "晚安呀"}]})

    client.apply_update(server.get_update())
    server.apply_update(client.get_update())

    assert unit_json(server)["utterances"] == [{"text": "早安啊"}, {"text": "晚安呀"}]


def test_list_insertions_and_deletions_keep_the_untouched_items() -> None:
    doc = _doc({"characters": ["A", "B", "C"]})

    apply_json(doc, {"characters": ["A", "X", "Y", "C"]})
    assert unit_json(doc)["characters"] == ["A", "X", "Y", "C"]

    apply_json(doc, {"characters": ["C"]})
    assert unit_json(doc)["characters"] == ["C"]


def test_applying_the_same_value_produces_no_update() -> None:
    doc = _doc({"synopsis": "x", "n": 3})
    before = doc.get_state()

    apply_json(doc, {"synopsis": "x", "n": 3})

    assert doc.get_state() == before
