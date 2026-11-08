"""ArcReelStudio 自己的内置供应商、模型条目与对上游供应商清单的追加。

上游目录数据（出厂快照与每日官方同步，来自 ArcReel/arcreel-catalog）只列上游的供应商，同步时整份取新；fork 新增的
供应商若写进快照文件，第一次同步就会被清掉。所以它们的清单写在代码里，由 :func:`with_fork_providers` 叠在出厂快照与
官方合成数据上：同 id 时以这里为准。清单引用的模型条目（例如 ``anthropic/claude-*``）仍来自目录数据。

订阅供应商的连线由登录流程建立。三家的模型引用目录里的官方条目，挂接只在订阅凭证下成立的调用端点（见
``arcreel_catalog_core.BUILTIN_PROVIDER_ENDPOINTS``）；模型名是官方 CLI 认得的名字。

音乐模型（docs/adr/0126）的条目上游目录没有，写在 :data:`FORK_ENTRIES`；Lyria 挂在上游已有的 AI Studio 清单上，
由 :data:`FORK_LISTING_ADDITIONS` 追加，不取代上游的清单。同一身份的条目若上游日后收录，以上游为准。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from arcreel_catalog_core import parse_entry
from arcreel_catalog_core.model import BuiltinProviderListing, BuiltinProviderModel, CatalogData, CatalogEntry


def _models(endpoint: str, maker: str, *names: str) -> tuple[BuiltinProviderModel, ...]:
    return tuple(
        # 用订阅额度，不按 token 计价
        BuiltinProviderModel(api_model_name=name, entry=f"{maker}/{name}", endpoint=endpoint, multiplier=0.0)
        for name in names
    )


FORK_PROVIDER_LISTINGS: Mapping[str, BuiltinProviderListing] = MappingProxyType(
    {
        "claude-subscription": BuiltinProviderListing(
            models=_models(
                "claude-subscription-chat",
                "anthropic",
                "claude-sonnet-5-5",
                "claude-opus-5-5",
                "claude-haiku-5-5",
                "claude-fable-5-1",
            ),
            defaults={"text": "claude-sonnet-5-5"},
        ),
        "chatgpt-subscription": BuiltinProviderListing(
            models=_models("codex-chat", "openai", "gpt-5.5", "gpt-6-sol", "gpt-6-luna")
            + _models("codex-image", "openai", "gpt-image-2"),
            defaults={"text": "gpt-5.5", "image": "gpt-image-2"},
        ),
        "grok-subscription": BuiltinProviderListing(
            models=_models("grok-cli-chat", "xai", "grok-build-0.1", "grok-4.7"),
            defaults={"text": "grok-build-0.1"},
        ),
    }
)


def _per_request(price: float) -> dict[str, object]:
    return {"currency": "USD", "meters": [{"meter": "requests", "dims": [], "rows": [{"when": {}, "price": price}]}]}


def _per_second(price: float) -> dict[str, object]:
    return {
        "currency": "USD",
        "meters": [{"meter": "output_seconds", "dims": [], "rows": [{"when": {}, "price": price}]}],
    }


#: 上游目录没有的音乐模型条目（价格取自各家官方价目页，2026-11-08）
FORK_ENTRIES: tuple[CatalogEntry, ...] = tuple(
    parse_entry(raw)
    for raw in (
        {
            "maker": "google",
            "name": "lyria-3.5",
            "media_type": "audio",
            "display_name": "Lyria 3.5",
            "facts": {"text_to_music": True},
            "price": _per_request(0.08),
        },
        {
            "maker": "google",
            "name": "lyria-3-clip-preview",
            "media_type": "audio",
            "display_name": "Lyria 3 Clip",
            "facts": {"text_to_music": True, "max_seconds": 30},
            "price": _per_request(0.04),
        },
        {
            "maker": "stability",
            "name": "stable-audio-3",
            "media_type": "audio",
            "display_name": "Stable Audio 3",
            "facts": {"text_to_music": True, "max_seconds": 380},
            "price": _per_request(0.08),
        },
        {
            "maker": "elevenlabs",
            "name": "music_v2_5",
            "media_type": "audio",
            "display_name": "Eleven Music v2.5",
            "facts": {"text_to_music": True, "max_seconds": 600},
            # $0.15 / 分钟
            "price": _per_second(0.0025),
        },
    )
)

#: 只做音乐的新供应商
FORK_MUSIC_LISTINGS: Mapping[str, BuiltinProviderListing] = MappingProxyType(
    {
        "stability": BuiltinProviderListing(
            models=(BuiltinProviderModel("stable-audio-3", "stability/stable-audio-3", endpoint="stability-audio"),),
            defaults={"audio": "stable-audio-3"},
        ),
        "elevenlabs": BuiltinProviderListing(
            models=(BuiltinProviderModel("music_v2_5", "elevenlabs/music_v2_5", endpoint="elevenlabs-music"),),
            defaults={"audio": "music_v2_5"},
        ),
    }
)

#: 追加到上游已有供应商清单的模型（不改上游的默认模型）
FORK_LISTING_ADDITIONS: Mapping[str, tuple[BuiltinProviderModel, ...]] = MappingProxyType(
    {
        "gemini-aistudio": (
            BuiltinProviderModel("lyria-3.5", "google/lyria-3.5", endpoint="gemini-lyria"),
            BuiltinProviderModel("lyria-3-clip-preview", "google/lyria-3-clip-preview", endpoint="gemini-lyria"),
        ),
    }
)


def _with_additions(
    listing: BuiltinProviderListing, additions: tuple[BuiltinProviderModel, ...]
) -> BuiltinProviderListing:
    known = {(model.api_model_name, model.entry) for model in listing.models}
    extra = tuple(model for model in additions if (model.api_model_name, model.entry) not in known)
    return replace(listing, models=(*listing.models, *extra)) if extra else listing


def with_fork_providers(data: CatalogData) -> CatalogData:
    """在目录数据上叠加 fork 的供应商清单（同 id 时以 fork 为准）、模型条目（上游已收录的同一身份以上游为准）与清单追加。"""
    if _already_applied(data):
        return data
    known_entries = {(entry.maker, entry.name, entry.media_type) for entry in data.entries}
    entries = (*data.entries, *(e for e in FORK_ENTRIES if (e.maker, e.name, e.media_type) not in known_entries))
    providers = {**data.builtin_providers, **FORK_PROVIDER_LISTINGS, **FORK_MUSIC_LISTINGS}
    for provider_id, additions in FORK_LISTING_ADDITIONS.items():
        listing = providers.get(provider_id)
        if listing is not None:
            providers[provider_id] = _with_additions(listing, additions)
    return replace(data, entries=entries, builtin_providers=providers)


def _already_applied(data: CatalogData) -> bool:
    own = {**FORK_PROVIDER_LISTINGS, **FORK_MUSIC_LISTINGS}
    if any(data.builtin_providers.get(pid) is not listing for pid, listing in own.items()):
        return False
    keys = {(entry.maker, entry.name, entry.media_type) for entry in data.entries}
    if any((e.maker, e.name, e.media_type) not in keys for e in FORK_ENTRIES):
        return False
    for provider_id, additions in FORK_LISTING_ADDITIONS.items():
        listing = data.builtin_providers.get(provider_id)
        if listing is not None and _with_additions(listing, additions) is not listing:
            return False
    return True
