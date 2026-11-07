"""请求语言解析：``Accept-Language`` 里的繁体中文变体归到 zh-TW，其余中文用简体。"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from server.i18n import get_locale


def _request(accept_language: str | None) -> Request:
    headers = [] if accept_language is None else [(b"accept-language", accept_language.encode())]
    return Request({"type": "http", "headers": headers})


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("zh-TW", "zh-TW"),
        ("zh-tw,zh;q=0.9", "zh-TW"),
        ("zh-HK", "zh-TW"),
        ("zh-Hant-TW", "zh-TW"),
        ("zh-MO,en;q=0.5", "zh-TW"),
        ("zh-CN", "zh"),
        ("zh", "zh"),
        ("zh-Hans", "zh"),
        ("en-US,zh-TW;q=0.8", "en"),
        ("ja-JP,zh-TW;q=0.8", "zh-TW"),
        ("fr-FR", "zh"),
        (None, "zh"),
    ],
)
def test_accept_language_maps_to_a_supported_locale(header, expected):
    assert get_locale(_request(header)) == expected
