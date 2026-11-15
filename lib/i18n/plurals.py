"""文案的单复数选择。不依赖项目其余部分：只装子包的市场工作流（``scripts/market.py``）也按路径加载它。"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["PLURAL_SUFFIXES", "pick_plural", "plural_category"]


#: 复数变体的键后缀，与前端 i18next 同名：``<key>_one`` / ``<key>_few`` / ``<key>_many``。
#: 基础键 ``<key>`` 本身就是 ``other`` 形式，所以每种语言都只需按需补变体，键集合仍一一对应。
PLURAL_SUFFIXES = ("_one", "_few", "_many")


def plural_category(locale: str, count: int) -> str:
    """按 CLDR 基数规则返回 ``count`` 在该语言里的复数类别。中文、越南语没有单复数，恒为 ``other``。"""
    n = abs(count)
    if locale == "en":
        return "one" if n == 1 else "other"
    if locale == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "other"


def pick_plural(msg_map: Mapping[str, str], key: str, locale: str, count: object) -> str | None:
    if not isinstance(count, int) or isinstance(count, bool):
        return None
    category = plural_category(locale, count)
    if category == "other":
        return None
    return msg_map.get(f"{key}_{category}")
