"""生成时没有默认模型：任务失败原因落成带媒体类型的结构化代码，各语言都指引到默认模型设置（docs/adr/0130）。"""

from __future__ import annotations

import re

import pytest

from lib.config.resolver import NoAvailableProviderError
from lib.generation.generation_result import GenerationAction, problem_from_task_failure
from lib.generation.task_failure import parse_failure, render_failure
from lib.generation.task_failure_encoding import encode_task_failure_message
from lib.i18n import _ as translate_message
from tests.factories import make_display_names

LOCALES = ["zh", "zh-TW", "en", "vi", "ru"]
#: 各语言里「默认模型设置」的说法，指引必须落到这里，不是只说「配置供应商」。
SETTINGS_NAME = {
    "zh": "默认模型",
    "zh-TW": "預設模型",
    "en": "Default models",
    "vi": "Mô hình mặc định",
    "ru": "Модели по умолчанию",
}
_CJK = re.compile(r"[一-鿿]")


def _missing(media_type: str) -> NoAvailableProviderError:
    return NoAvailableProviderError(
        f"没有设置 {media_type} 默认模型。请在「全局设置 → 默认模型」中选择。", media_type=media_type
    )


def _render(message: str, locale: str) -> str:
    def translate(key: str, **kwargs):
        return translate_message(key, locale=locale, **kwargs)

    rendered = render_failure(message, translate, make_display_names(locale))
    assert rendered is not None
    return rendered


@pytest.mark.parametrize("media_type", ["text", "image", "video", "audio"])
def test_a_missing_default_model_is_stored_as_a_code_with_its_media_type(media_type: str) -> None:
    message = encode_task_failure_message(_missing(media_type))

    assert parse_failure(message) == ("default_model_not_set", {"media_type": media_type})


def test_the_failure_asks_the_user_to_configure_models() -> None:
    message = encode_task_failure_message(_missing("image"))

    assert problem_from_task_failure(message).action is GenerationAction.CONFIGURE_PROVIDER


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("media_type", ["text", "image", "video", "audio", "something_new"])
def test_every_locale_points_to_the_default_model_settings(locale: str, media_type: str) -> None:
    """渲染出读者语言的文案，指向默认模型设置；未知的媒体类型用不点名媒体的通用文案，不留未替换的占位。"""
    rendered = _render(encode_task_failure_message(_missing(media_type)), locale)

    assert SETTINGS_NAME[locale] in rendered
    assert "{" not in rendered
    assert not rendered.startswith("[")
    if locale in ("en", "vi", "ru"):
        assert not _CJK.search(rendered), rendered


@pytest.mark.parametrize("locale", LOCALES)
def test_each_media_type_is_named_in_its_own_wording(locale: str) -> None:
    rendered = {
        media_type: _render(encode_task_failure_message(_missing(media_type)), locale)
        for media_type in ("text", "image", "video", "audio", "something_new")
    }

    assert len(set(rendered.values())) == len(rendered)
