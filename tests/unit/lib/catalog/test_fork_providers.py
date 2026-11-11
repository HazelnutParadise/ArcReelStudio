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


def test_ai_studio_no_longer_lists_the_veo_previews_google_shut_down():
    snapshot = catalog.factory_snapshot()
    ai_studio = snapshot.builtin_providers["gemini-aistudio"]
    names = {model.api_model_name for model in ai_studio.models}

    assert not {name for name in names if name.startswith("veo-")}
    assert all(not name.startswith("veo-") for name in ai_studio.defaults.values())
    # Vertex 上的 Veo 不受影响
    assert any(m.api_model_name.startswith("veo-") for m in snapshot.builtin_providers["gemini-vertex"].models)


def test_a_sync_that_brings_the_veo_previews_back_drops_them_again():
    snapshot = catalog.factory_snapshot()
    listing = snapshot.builtin_providers["gemini-aistudio"]
    brought_back = replace(
        listing,
        models=(*listing.models, replace(listing.models[0], api_model_name="veo-3.1-generate-preview")),
        defaults={**listing.defaults, "video": "veo-3.1-generate-preview"},
    )
    synced = with_fork_providers(
        replace(snapshot, builtin_providers={**snapshot.builtin_providers, "gemini-aistudio": brought_back})
    )

    again = synced.builtin_providers["gemini-aistudio"]
    assert "veo-3.1-generate-preview" not in {model.api_model_name for model in again.models}
    assert again.defaults["video"] == "gemini-omni-1.1-flash"


def test_ai_studio_video_is_served_by_gemini_omni():
    ai_studio = catalog.factory_snapshot().builtin_providers["gemini-aistudio"]
    omni = next(model for model in ai_studio.models if model.api_model_name == "gemini-omni-1.1-flash")

    assert omni.endpoint == "gemini-interactions-video"
    assert ai_studio.defaults["video"] == "gemini-omni-1.1-flash"
    listed = catalog.list_models("gemini-aistudio")["gemini-omni-1.1-flash"]
    assert listed.media_type == "video"
