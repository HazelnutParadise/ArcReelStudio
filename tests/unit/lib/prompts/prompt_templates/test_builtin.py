"""内置目录扫描通过加载接口执行语法、槽位、变体族完整性、判重开启范围与共享片段门槛约束。"""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from jinja2 import Environment, nodes

from lib.agent.profile_manifest import VALID_CONTENT_MODES
from lib.episode.source_kinds import SOURCE_KINDS
from lib.project.project_manager import VALID_GENERATION_MODES
from lib.prompts.prompt_builders_ad import AD_DURATION_TIERS
from lib.prompts.prompt_templates import PromptTemplates
from lib.prompts.prompt_templates.builtin import BUILTIN_DIRECTORY


def test_builtin_directory_has_valid_slots_variants_and_template_syntax():
    templates = PromptTemplates(BUILTIN_DIRECTORY)
    metadata = templates.list_templates()
    assert metadata
    for entry in metadata:
        body, partials = templates.read_source(entry.id)
        assert body.strip()
        # 行距写在引用处，片段只写措辞本身。
        assert not [partial.name for partial in partials if partial.source.startswith("\n")]
    # 判重只给存在纯文本回贴形态的模版开启，其余模版多处引用同一数据片段时不能被吞掉。
    assert {entry.id for entry in metadata if entry.idempotent} == {"storyboard/image", "storyboard/video"}
    asset = next(entry for entry in metadata if entry.id == "asset/sheet")
    assert set(asset.applies_to["asset_type"]) == {"character", "character_derivative", "scene", "prop", "product"}
    for asset_type in asset.applies_to["asset_type"]:
        rendered = templates.render(
            asset.id,
            asset_type=asset_type,
            name="测试资产",
            description="外观描述",
            style="水彩",
            style_description="柔和笔触",
        )
        assert "外观描述" in rendered
        assert "Avoid:" in rendered
        if asset_type in {"character_derivative", "product"}:
            assert "Style:" not in rendered
            assert "Visual style:" not in rendered
        else:
            assert rendered.count("Style: 水彩") == 1
            assert rendered.count("Visual style: 柔和笔触") == 1


def test_builtin_applies_to_values_are_real_project_values():
    """设置页原样展示轴值，项目里不存在的取值会误导用户以为有这种模式。"""
    known = {
        "content_mode": set(VALID_CONTENT_MODES),
        "generation_mode": set(VALID_GENERATION_MODES),
        "source_kind": set(SOURCE_KINDS),
        "ad_duration_tier": {str(tier) for tier in AD_DURATION_TIERS},
    }
    for entry in PromptTemplates(BUILTIN_DIRECTORY).list_templates():
        for axis, values in entry.applies_to.items():
            if axis in known:
                assert set(values) <= known[axis], (entry.id, axis, values)


def test_builtin_templates_declare_stage_and_trigger_and_lock_structural_partials():
    templates = PromptTemplates(BUILTIN_DIRECTORY)
    metadata = templates.list_templates()
    styles = [entry for entry in metadata if entry.category == "style"]
    assert len(styles) == 36
    for entry in styles:
        assert entry.stage == "style"
        assert entry.invoked_by.model_dump() == {"kind": "user_action", "name": "style_selection"}
    catalog = {partial.name: partial for entry in metadata for partial in templates.read_source(entry.id)[1]}
    assert {name for name, partial in catalog.items() if partial.protected} == {
        "shared/overview_block",
        "shared/media_style",
        "shared/text_style",
        "shared/lists/asset_name_blocks",
        "shared/lists/asset_registry_blocks",
        "shared/lists/asset_appearance_blocks",
        "shared/additional_instructions",
        "shared/writing_syntax",
    }
    # 引用方含经由资产图变体间接引用的模版，按注册顺序排列。
    assert catalog["shared/media_style"].referenced_by == [
        "asset/sheet",
        "reference_video/unit",
        "storyboard/grid",
        "storyboard/image",
    ]


def _partial_calls(source: str) -> set[str]:
    return {
        call.args[0].value
        for call in Environment().parse(source).find_all(nodes.Call)
        if isinstance(call.node, nodes.Name) and call.node.name == "partial"
    }


def _single_parent_shared_partials(partials_directory: Path, template_sources: Iterable[tuple[str, str]]) -> list[str]:
    referrers: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for template_id, body in template_sources:
        for name in _partial_calls(body):
            referrers[name].add(("template", template_id))
    for path in partials_directory.rglob("*.md"):
        parent = path.relative_to(partials_directory).with_suffix("").as_posix()
        for name in _partial_calls(path.read_text(encoding="utf-8")):
            referrers[name].add(("partial", parent))
    return sorted(
        name
        for name, sources in referrers.items()
        if name.startswith("shared/") and len(sources) == 1 and next(iter(sources))[0] == "partial"
    )


def test_builtin_shared_partials_are_not_referenced_by_a_single_partial():
    """只被一个片段引用的措辞内联回该片段；变体族成员按轴值拆分，不计入。"""
    templates = PromptTemplates(BUILTIN_DIRECTORY)
    template_sources = ((entry.id, templates.read_source(entry.id)[0]) for entry in templates.list_templates())
    assert _single_parent_shared_partials(BUILTIN_DIRECTORY / "partials", template_sources) == []


def test_shared_partial_scan_includes_files_unreachable_from_templates(tmp_path: Path):
    parent = tmp_path / "shared" / "orphan_parent.md"
    parent.parent.mkdir()
    parent.write_text('{{ partial("shared/orphan_child") }}', encoding="utf-8")
    (parent.parent / "orphan_child.md").write_text("孤立措辞", encoding="utf-8")

    assert _single_parent_shared_partials(tmp_path, []) == ["shared/orphan_child"]


def test_every_builtin_template_has_localized_title_and_description():
    """设置页按界面语言显示标题与说明：简体原文之外的每种界面语言都要有译文，且不能照抄简体原文。"""
    from typing import get_args

    from lib.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES
    from lib.prompts.prompt_templates.builtin import builtin_templates
    from lib.prompts.prompt_templates.engine import TranslatedLocale

    assert set(get_args(TranslatedLocale)) == set(SUPPORTED_LOCALES) - {DEFAULT_LOCALE}
    for meta in builtin_templates.list_templates():
        assert set(meta.i18n) == set(get_args(TranslatedLocale)), meta.id
        for locale, text in meta.i18n.items():
            assert text.title.strip(), (meta.id, locale)
            assert text.description.strip(), (meta.id, locale)
            if locale != "zh-TW":
                assert text.title != meta.title or text.title.isascii(), (meta.id, locale)
            assert set(text.slots) == set(meta.slots), (meta.id, locale)
            assert all(value.strip() for value in text.slots.values()), (meta.id, locale)
            assert meta.localized(locale).title == text.title
            assert meta.localized(locale).slots == text.slots
        assert meta.localized(DEFAULT_LOCALE) == meta


def test_zh_tw_template_texts_follow_taiwan_wording():
    """繁体标题与说明套用与后端文案相同的字形、简转繁残留与标点规则。"""
    from lib.prompts.prompt_templates.builtin import builtin_templates
    from tests.unit.lib.i18n.test_locale_wording import OPENCC_ARTEFACTS, SIMPLIFIED_ONLY, ZH_RULES

    for meta in builtin_templates.list_templates():
        text = meta.i18n["zh-TW"]
        for value in (text.title, text.description, *text.slots.values()):
            # ``@图片N`` / ``@音频N`` 是提示词里的引用语法本身，照原样保留
            assert not SIMPLIFIED_ONLY.search(value.replace("@图片N", "").replace("@音频N", "")), (meta.id, value)
            assert not OPENCC_ARTEFACTS.search(value), (meta.id, value)
            for rule, pattern in ZH_RULES:
                assert not pattern.search(value), (meta.id, rule, value)
