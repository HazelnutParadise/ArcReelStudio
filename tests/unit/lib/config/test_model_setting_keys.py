"""模型设置值 ``provider/model`` 的供应商部分：全局默认模型页、项目设置与推荐切换共用同一口径。"""

import pytest

from lib.config.model_setting_keys import provider_of


@pytest.mark.parametrize(
    ("value", "provider"),
    [
        ("gemini-aistudio/gemini-3-flash", "gemini-aistudio"),
        ("custom-3/vendor/model-x", "custom-3"),
        ("ark", "ark"),
        (" ark /seedance", "ark"),
        ("", ""),
        (None, ""),
        (42, ""),
    ],
)
def test_provider_of(value: object, provider: str) -> None:
    assert provider_of(value) == provider
