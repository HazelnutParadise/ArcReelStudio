"""简体与繁体中文消息的标点与字形，与前端 frontend/src/i18n/locale-wording.test.ts 保持同一口径。"""

import re

import pytest

from lib.i18n import MESSAGES

# 对应前端的 \p{Script=Han}：基本区、扩展 A 区、兼容区与扩展 B 区以后
HAN = r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]"

ZH_RULES = [
    ("中文后用全角冒号", re.compile(rf"{HAN}\s?:")),
    ("省略号用「…」", re.compile(r"\.\.\.|……")),
    # 只查成对的引号：列举非法字符时单独出现的 " 是字符本身
    ("引号用「」", re.compile(r'"[^"]*"')),
    # 端点含占位符或百分号、或后接单位的才算范围；两端都是裸数字的是用户照样输入的语法
    (
        "数值范围用「～」",
        re.compile(
            rf"\{{\w+\}}\s?[-–]\s?(\d|\{{)|\d\s?[-–]\s?\{{|\d%\s?[-–]\s?\d|\d\s?[-–]\s?\d+(\.\d+)?(%|\s?({HAN}|[A-Za-z]))"
        ),
    ),
]


#: 只在简体中文里出现的常用字；繁体消息里出现即说明有文案没有转成繁体。
SIMPLIFIED_ONLY = re.compile(
    "[们这个设视频项时为于与说对进会发动务类页选码号应关开当无将让还从网络数据图显输删编辑览载传导级链帮请确认]"
)


@pytest.mark.parametrize("locale", ["zh", "zh-TW"])
@pytest.mark.parametrize(("rule", "pattern"), ZH_RULES, ids=[r for r, _ in ZH_RULES])
def test_zh_messages_follow_punctuation_rule(rule, pattern, locale):
    offenders = {key: text for key, text in MESSAGES[locale].items() if pattern.search(text)}
    assert offenders == {}, rule


def test_zh_tw_messages_are_traditional_chinese():
    offenders = {key: text for key, text in MESSAGES["zh-TW"].items() if SIMPLIFIED_ONLY.search(text)}
    assert offenders == {}
