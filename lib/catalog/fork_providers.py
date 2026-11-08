"""ArcReelStudio 自己的内置供应商在目录里的清单。

上游目录数据（出厂快照与每日官方同步，来自 ArcReel/arcreel-catalog）只列上游的供应商，同步时整份取新；fork 新增的
供应商若写进快照文件，第一次同步就会被清掉。所以它们的清单写在代码里，由 :func:`with_fork_providers` 叠在出厂快照与
官方合成数据上：同 id 时以这里为准。清单引用的模型条目（例如 ``anthropic/claude-*``）仍来自目录数据。

订阅供应商的连线由登录流程建立，目前只供 Agent 使用；文字与图片生成接上后再在这里登记模型。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from arcreel_catalog_core.model import BuiltinProviderListing, CatalogData

FORK_PROVIDER_LISTINGS: Mapping[str, BuiltinProviderListing] = MappingProxyType(
    {
        "claude-subscription": BuiltinProviderListing(models=()),
        "chatgpt-subscription": BuiltinProviderListing(models=()),
        "grok-subscription": BuiltinProviderListing(models=()),
    }
)


def with_fork_providers(data: CatalogData) -> CatalogData:
    """在目录数据上叠加 fork 的供应商清单（同 id 时以 fork 为准）。"""
    if all(data.builtin_providers.get(pid) is listing for pid, listing in FORK_PROVIDER_LISTINGS.items()):
        return data
    return replace(data, builtin_providers={**data.builtin_providers, **FORK_PROVIDER_LISTINGS})
