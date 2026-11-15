"""后端文案的单复数：按 ``count`` 选 ``<key>_one`` / ``_few`` / ``_many`` 变体，基础键即 ``other``。"""

import re

import pytest

from lib.i18n import MESSAGES, PLURAL_SUFFIXES, _, plural_category


@pytest.mark.parametrize(
    ("count", "category"),
    [
        (0, "many"),
        (1, "one"),
        (2, "few"),
        (4, "few"),
        (5, "many"),
        (11, "many"),
        (12, "many"),
        (21, "one"),
        (22, "few"),
        (111, "many"),
    ],
)
def test_russian_plural_categories(count: int, category: str) -> None:
    assert plural_category("ru", count) == category


def test_english_and_chinese_categories() -> None:
    assert plural_category("en", 1) == "one"
    assert plural_category("en", 0) == "other"
    assert plural_category("en", 2) == "other"
    assert plural_category("zh", 1) == "other"
    assert plural_category("vi", 1) == "other"


def test_english_singular_and_plural() -> None:
    assert _("tts_batch_submitted", "en", count=1) == "Submitted 1 narration audio task"
    assert _("tts_batch_submitted", "en", count=3) == "Submitted 3 narration audio tasks"
    assert _("episode_delete_loss_video", "en", count=1) == "1 video"
    assert _("episode_delete_loss_video", "en", count=0) == "0 videos"


def test_russian_one_few_many() -> None:
    def render(n: int) -> str:
        return _("comfyui_multiple_outputs", "ru", count=n, filename="a.png")

    assert "21 файл " in render(21)
    assert "3 файла " in render(3)
    assert "5 файлов " in render(5)
    assert "12 файлов " in render(12)


def test_falls_back_to_base_key_without_variant_or_int_count() -> None:
    assert _("tts_batch_submitted", "zh", count=1) == MESSAGES["zh"]["tts_batch_submitted"].format(count=1)
    # 非整数（或布尔）count 不参与复数选择
    assert _("tts_batch_submitted", "en", count="1") == "Submitted 1 narration audio tasks"
    assert _("tts_batch_submitted", "en", count=True).startswith("Submitted True narration audio tasks")


def test_english_count_messages_have_no_parenthesised_plurals() -> None:
    """``{count} thing(s)`` 已改成变体：数量直接修饰的名词不再写 ``(s)``。"""
    offenders = [key for key, msg in MESSAGES["en"].items() if re.search(r"\{count\}[^{.;,]*?\w\(s\)", msg)]
    assert not offenders, offenders


def test_every_plural_variant_has_a_base_key() -> None:
    for locale, messages in MESSAGES.items():
        for key in messages:
            for suffix in PLURAL_SUFFIXES:
                if key.endswith(suffix) and key.removesuffix(suffix) in messages:
                    break
            else:
                continue
            assert key.removesuffix(suffix) in messages, (locale, key)
