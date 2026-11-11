"""免版权素材库的路由：密钥按来源的归属存取，搜索带上当前成员可用的密钥，音乐与音效导入项目时记下授权与来源。"""

from __future__ import annotations

from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.db import get_async_session
from lib.project.project_manager import ProjectManager
from lib.stock.model import KeyScope, ResolvedStockItem, StockError, StockItem, StockKind
from lib.stock.service import StockLibraryService
from server.auth import EMBEDDED_AGENT_SUB, CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import files, stock
from server.services.stock_access import stock_library
from tests.auth_deps import AUTH_DEPENDENCIES
from tests.factories import wav_bytes
from tests.fakes import use_project_manager

BASE = "/api/v1/stock"


class _FakeSource:
    """记下每次调用拿到的密钥；素材档案放在 ``https://files.test/<id><ext>``。"""

    key_url: str | None = None

    def __init__(self, source_id: str, kinds: set[StockKind], key_scope: KeyScope, extension: str) -> None:
        self.id = source_id
        self.display_name = source_id.title()
        self.kinds: frozenset[StockKind] = frozenset(kinds)
        self.key_scope: KeyScope = key_scope
        self.extension = extension
        self.seen_keys: list[str | None] = []

    def _item(self, kind: StockKind, item_id: str) -> StockItem:
        return StockItem(
            source=self.id,
            id=item_id,
            kind=kind,
            title="rain / on a tin roof v1.2",
            creator="someone",
            license="cc0",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/",
            page_url=f"https://{self.id}.test/items/{item_id}",
        )

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]:
        self.seen_keys.append(key)
        return [self._item(kind, f"{query}-{page}")]

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem:
        self.seen_keys.append(key)
        if item_id == "gone":
            raise StockError("stock_item_not_found", "没有这条素材", source=self.id)
        return ResolvedStockItem(
            item=self._item(kind, item_id),
            download_url=f"https://files.test/{item_id}{self.extension}",
            extension=self.extension,
        )


async def _download(url: str) -> bytes:
    return wav_bytes(1, tone_hz=440) if url.endswith(".wav") else b"\x89PNG-bytes"


class _Stock:
    def __init__(self) -> None:
        self.free = _FakeSource("free", {"music", "sfx", "image"}, "none", ".wav")
        self.shared = _FakeSource("shared", {"image"}, "workspace", ".png")
        self.personal = _FakeSource("personal", {"sfx"}, "member", ".wav")
        self.library = StockLibraryService(
            sources={source.id: source for source in (self.free, self.shared, self.personal)},
            download=_download,
        )


@pytest.fixture
def stock_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Stock:
    manager = ProjectManager(str(tmp_path / "projects"))
    manager.create_project("demo")
    manager.create_project_metadata("demo", "Demo", "Anime", "narration")
    use_project_manager(monkeypatch, manager)
    return _Stock()


def _app(db_factory, env: _Stock, user: CurrentUserInfo) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    async def override_session():
        async with db_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[stock_library] = lambda: env.library
    app.include_router(stock.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    app.include_router(files.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    return app


def _client(db_factory, env: _Stock, *, account: str, role: str) -> AsyncClient:
    user = CurrentUserInfo(id=account, sub=account, role=role, username=account)
    return AsyncClient(transport=ASGITransport(app=_app(db_factory, env, user)), base_url="http://t")


def _by_id(body: dict) -> dict[str, dict]:
    return {source["id"]: source for source in body["sources"]}


async def test_sources_say_which_ones_the_member_can_use_and_whose_key_they_need(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-bob", role="user") as bob:
        sources = _by_id((await bob.get(f"{BASE}/sources")).json())

    assert {key: (value["available"], value["can_set_key"]) for key, value in sources.items()} == {
        "free": (True, False),
        "shared": (False, False),
        "personal": (False, True),
    }
    assert sources["free"]["kinds"] == ["image", "music", "sfx"]


async def test_a_workspace_key_is_set_by_an_admin_and_used_by_every_member(db_factory, stock_env) -> None:
    async with (
        _client(db_factory, stock_env, account="default", role="admin") as admin,
        _client(db_factory, stock_env, account="u-bob", role="user") as bob,
    ):
        refused = await bob.put(f"{BASE}/sources/shared/key", json={"api_key": "bob-tries"})
        saved = await admin.put(f"{BASE}/sources/shared/key", json={"api_key": "workspace-secret-key"})
        seen_by_bob = _by_id((await bob.get(f"{BASE}/sources")).json())["shared"]
        await bob.get(f"{BASE}/search", params={"kind": "image", "q": "sea"})

    assert refused.status_code == 403
    assert saved.status_code == 200
    assert "workspace-secret-key" not in saved.text
    assert seen_by_bob["available"] is True
    assert seen_by_bob["key_masked"]
    assert seen_by_bob["key_masked"] != "workspace-secret-key"
    assert stock_env.shared.seen_keys == ["workspace-secret-key"]


async def test_a_member_key_is_only_used_for_that_member(db_factory, stock_env) -> None:
    async with (
        _client(db_factory, stock_env, account="u-alice", role="user") as alice,
        _client(db_factory, stock_env, account="u-bob", role="user") as bob,
    ):
        await alice.put(f"{BASE}/sources/personal/key", json={"api_key": "alice-token"})
        alice_result = (await alice.get(f"{BASE}/search", params={"kind": "sfx", "q": "door"})).json()
        bob_result = (await bob.get(f"{BASE}/search", params={"kind": "sfx", "q": "door"})).json()
        bob_sources = _by_id((await bob.get(f"{BASE}/sources")).json())

    assert {entry["source"]: entry["status"] for entry in alice_result["sources"]} == {"free": "ok", "personal": "ok"}
    assert {entry["source"]: entry["status"] for entry in bob_result["sources"]} == {
        "free": "ok",
        "personal": "key_missing",
    }
    assert [item["source"] for item in bob_result["items"]] == ["free"]
    assert stock_env.personal.seen_keys == ["alice-token"]
    assert bob_sources["personal"]["available"] is False


async def test_removing_a_key_makes_the_source_unavailable_again(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-alice", role="user") as alice:
        await alice.put(f"{BASE}/sources/personal/key", json={"api_key": "alice-token"})
        removed = await alice.delete(f"{BASE}/sources/personal/key")
        no_key_needed = await alice.put(f"{BASE}/sources/free/key", json={"api_key": "x"})
        unknown = await alice.put(f"{BASE}/sources/nowhere/key", json={"api_key": "x"})

    assert _by_id(removed.json())["personal"]["available"] is False
    assert no_key_needed.status_code == 400
    assert unknown.status_code == 404


async def test_an_image_is_served_with_its_media_type(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="default", role="admin") as admin:
        await admin.put(f"{BASE}/sources/shared/key", json={"api_key": "workspace-secret-key"})
        response = await admin.get(f"{BASE}/image", params={"source": "shared", "id": "42"})
        missing = await admin.get(f"{BASE}/image", params={"source": "shared", "id": "gone"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"\x89PNG-bytes"
    assert missing.status_code == 404


async def test_importing_music_registers_it_as_bgm_with_its_license_and_source_page(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-bob", role="user") as bob:
        response = await bob.post(
            "/api/v1/projects/demo/stock/import", json={"source": "free", "id": "t1", "kind": "music"}
        )
        listed = (await bob.get("/api/v1/projects/demo/bgm")).json()["bgm"]

    assert response.status_code == 200, response.text
    track = response.json()["bgm"]
    assert track["name"] == "rain   on a tin roof v1.2"
    assert (track["source"], track["license"], track["source_url"]) == (
        "library",
        "cc0",
        "https://free.test/items/t1",
    )
    assert [entry["id"] for entry in listed] == [track["id"]]


async def test_importing_a_sound_effect_uses_the_members_own_key(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-alice", role="user") as alice:
        without_key = await alice.post(
            "/api/v1/projects/demo/stock/import", json={"source": "personal", "id": "s1", "kind": "sfx"}
        )
        await alice.put(f"{BASE}/sources/personal/key", json={"api_key": "alice-token"})
        response = await alice.post(
            "/api/v1/projects/demo/stock/import", json={"source": "personal", "id": "s1", "kind": "sfx"}
        )
        listed = (await alice.get("/api/v1/projects/demo/sfx")).json()["sfx"]

    assert without_key.status_code == 400
    assert response.status_code == 200, response.text
    sound = response.json()["sfx"]
    assert (sound["source"], sound["license"]) == ("library", "cc0")
    assert sound["id"] in [entry["id"] for entry in listed]
    assert stock_env.personal.seen_keys == ["alice-token"]
    assert len(listed) == 1


async def test_importing_an_item_the_source_no_longer_offers_adds_nothing(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-bob", role="user") as bob:
        response = await bob.post(
            "/api/v1/projects/demo/stock/import", json={"source": "free", "id": "gone", "kind": "music"}
        )
        wrong_kind = await bob.post(
            "/api/v1/projects/demo/stock/import", json={"source": "shared", "id": "1", "kind": "music"}
        )
        listed = (await bob.get("/api/v1/projects/demo/bgm")).json()["bgm"]

    assert response.status_code == 404
    assert wrong_kind.status_code == 400
    assert listed == []


async def test_the_embedded_agent_cannot_use_or_change_a_members_key(db_factory, stock_env) -> None:
    # 内嵌 Agent 的令牌解析出的 id 就是预设管理员的账号 id：它不能因此用到那位管理员自己的密钥
    admin_user = CurrentUserInfo(id="default", sub="default", role="admin", username="admin")
    agent_user = CurrentUserInfo(id="default", sub=EMBEDDED_AGENT_SUB, role="user")
    async with (
        AsyncClient(transport=ASGITransport(app=_app(db_factory, stock_env, admin_user)), base_url="http://t") as admin,
        AsyncClient(transport=ASGITransport(app=_app(db_factory, stock_env, agent_user)), base_url="http://t") as agent,
    ):
        await admin.put(f"{BASE}/sources/personal/key", json={"api_key": "admin-token"})
        sources = _by_id((await agent.get(f"{BASE}/sources")).json())
        searched = (await agent.get(f"{BASE}/search", params={"kind": "sfx", "q": "door"})).json()
        imported = await agent.post(
            "/api/v1/projects/demo/stock/import", json={"source": "personal", "id": "s1", "kind": "sfx"}
        )
        overwritten = await agent.put(f"{BASE}/sources/personal/key", json={"api_key": "agent-token"})
        removed = await agent.delete(f"{BASE}/sources/personal/key")
        still_there = _by_id((await admin.get(f"{BASE}/sources")).json())["personal"]

    assert (sources["personal"]["available"], sources["personal"]["can_set_key"]) == (False, False)
    assert sources["personal"]["key_masked"] is None
    assert {entry["source"]: entry["status"] for entry in searched["sources"]}["personal"] == "key_missing"
    assert imported.status_code == 400
    assert (overwritten.status_code, removed.status_code) == (403, 403)
    assert still_there["available"] is True
    assert stock_env.personal.seen_keys == []


async def test_saving_a_key_twice_replaces_it(db_factory, stock_env) -> None:
    async with _client(db_factory, stock_env, account="u-alice", role="user") as alice:
        await alice.put(f"{BASE}/sources/personal/key", json={"api_key": "first-token"})
        second = await alice.put(f"{BASE}/sources/personal/key", json={"api_key": "second-token"})
        await alice.get(f"{BASE}/search", params={"kind": "sfx", "q": "door"})

    assert second.status_code == 200
    assert stock_env.personal.seen_keys == ["second-token"]
