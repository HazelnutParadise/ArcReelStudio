"""Fork 自己的内置供应商（订阅登录）不在上游目录数据里：出厂快照与官方同步合成后都要带上，不会被每日同步清掉。"""

from __future__ import annotations

from dataclasses import replace

from lib.catalog import query as catalog
from lib.catalog.fork_providers import FORK_PROVIDER_LISTINGS, with_fork_providers


def test_the_factory_snapshot_carries_the_fork_providers():
    providers = catalog.factory_snapshot().builtin_providers
    for provider_id in FORK_PROVIDER_LISTINGS:
        assert provider_id in providers


def test_synced_data_without_the_fork_providers_still_lists_them():
    snapshot = catalog.factory_snapshot()
    upstream_only = replace(
        snapshot,
        dataset_version="2099-01-01T00:00:00Z",
        builtin_providers={k: v for k, v in snapshot.builtin_providers.items() if k not in FORK_PROVIDER_LISTINGS},
    )
    catalog.install_synced_data(upstream_only)
    try:
        assert set(FORK_PROVIDER_LISTINGS) <= set(catalog.official_data().builtin_providers)
        assert catalog.official_data().dataset_version == "2099-01-01T00:00:00Z"
    finally:
        catalog.install_synced_data(None)


def test_the_fork_listing_replaces_an_upstream_listing_of_the_same_id():
    snapshot = catalog.factory_snapshot()
    provider_id = next(iter(FORK_PROVIDER_LISTINGS))
    other = snapshot.builtin_providers["openai"]
    tampered = replace(snapshot, builtin_providers={**snapshot.builtin_providers, provider_id: other})

    assert with_fork_providers(tampered).builtin_providers[provider_id] is FORK_PROVIDER_LISTINGS[provider_id]
