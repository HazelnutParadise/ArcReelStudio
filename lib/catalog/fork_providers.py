"""ArcReelStudio 自己的内置供应商在目录里的清单。

上游目录数据（出厂快照与每日官方同步，来自 ArcReel/arcreel-catalog）只列上游的供应商，同步时整份取新；fork 新增的
供应商若写进快照文件，第一次同步就会被清掉。所以它们的清单写在代码里，由 :func:`with_fork_providers` 叠在出厂快照与
官方合成数据上：同 id 时以这里为准。清单引用的模型条目（例如 ``anthropic/claude-*``）仍来自目录数据。

订阅供应商的连线由登录流程建立。三家的模型引用目录里的官方条目，挂接只在订阅凭证下成立的调用端点（见
``arcreel_catalog_core.BUILTIN_PROVIDER_ENDPOINTS``）；模型名是官方 CLI 认得的名字。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from arcreel_catalog_core.model import BuiltinProviderListing, BuiltinProviderModel, CatalogData


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


def with_fork_providers(data: CatalogData) -> CatalogData:
    """在目录数据上叠加 fork 的供应商清单（同 id 时以 fork 为准）。"""
    if all(data.builtin_providers.get(pid) is listing for pid, listing in FORK_PROVIDER_LISTINGS.items()):
        return data
    return replace(data, builtin_providers={**data.builtin_providers, **FORK_PROVIDER_LISTINGS})
