import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { CollabClient, scriptItemRef, type CollabRoom } from "./collab-client";
import { setToken } from "@/utils/auth";

import { FakeCollabServer } from "./collab-test-server";
import { applyJson, unitJson } from "./ydoc-json";

const REF = { project: "demo", kind: "overview", key: "" };

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

function waitFor(room: CollabRoom, phase: string): Promise<void> {
  return new Promise((resolve) => {
    const check = () => {
      if (room.getSnapshot().phase === phase) {
        unsubscribe();
        resolve();
      }
    };
    const unsubscribe = room.subscribe(check);
    check();
  });
}

describe("CollabClient", () => {
  let server: FakeCollabServer;
  let restore: () => void;

  beforeEach(() => {
    setToken("token");
    server = new FakeCollabServer({ "demo/overview/": { synopsis: "雨夜" } });
    restore = server.install();
  });

  afterEach(() => {
    restore();
    vi.useRealTimers();
  });

  it("authenticates, joins and receives the stored content", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);

    await waitFor(room, "synced");

    expect(server.received[0]).toMatchObject({ type: "auth", token: "token" });
    expect(room.getSnapshot().json).toEqual({ synopsis: "雨夜" });
  });

  it("sends local changes to the server", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    room.markRendered(room.getSnapshot().json!);

    room.change({ synopsis: "雨夜的街口" });
    await settle();

    expect(unitJson(server.docFor(REF))).toEqual({ synopsis: "雨夜的街口" });
  });

  it("does not undo a remote change that arrived before the screen re-rendered", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    // 界面渲染的是「雨夜」
    room.markRendered(room.getSnapshot().json!);

    // 远端在开头加了字，界面还没重绘，本机基于「雨夜」在结尾打字
    server.externalChange(REF, { synopsis: "深夜，雨夜" });
    await settle();
    room.change({ synopsis: "雨夜。" });
    await settle();

    expect(room.getSnapshot().json).toEqual({ synopsis: "深夜，雨夜。" });
    expect(unitJson(server.docFor(REF))).toEqual({ synopsis: "深夜，雨夜。" });
  });

  it("undoes only its own edits", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    room.markRendered(room.getSnapshot().json!);

    room.change({ synopsis: "雨夜！" });
    await settle();
    server.externalChange(REF, { synopsis: "深夜，雨夜！" });
    await settle();
    room.undoManager.undo();

    expect(room.getSnapshot().json).toEqual({ synopsis: "深夜，雨夜" });
  });

  it("moves another member's caret along when their text grows behind it", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    room.markRendered(room.getSnapshot().json!);

    // 另一位成员把光标停在「雨夜」结尾，接着打字：光标的相对位置不变，不会再送一次在线状态
    const peerDoc = server.docFor(REF);
    const text = peerDoc.getMap("unit").get("synopsis") as Y.Text;
    const end = Y.relativePositionToJSON(Y.createRelativePositionFromTypeIndex(text, text.length));
    const peer = new Awareness(peerDoc);
    peer.setLocalState({ user: { id: "u-bob", name: "bob" }, focus: { field: "synopsis", anchor: end, head: end } });
    server.deliverAwareness(REF, peer);
    await settle();
    expect(room.getSnapshot().peers[0]?.selection).toEqual({ anchor: 2, head: 2 });

    server.externalChange(REF, { synopsis: "雨夜的街口" });
    await settle();

    expect(room.getSnapshot().peers[0]?.selection).toEqual({ anchor: 5, head: 5 });
  });

  it("records which member changed which field", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    room.markRendered(room.getSnapshot().json!);

    // 服务端替身的文档就是这位成员写入时用的文档：更新里的客户端编号与在线状态一致
    const peer = new Awareness(server.docFor(REF));
    peer.setLocalState({ user: { id: "u-bob", name: "bob", color: "#2563eb" }, focus: null });
    server.deliverAwareness(REF, peer);
    await settle();

    server.externalChange(REF, { synopsis: "雨夜的街口" });
    await settle();

    expect(room.getSnapshot().remoteEdits.synopsis).toMatchObject({ userId: "u-bob", name: "bob" });
  });

  it("does not attribute a change nobody in the room made", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");

    server.externalChange(REF, { synopsis: "雨夜的街口" });
    await settle();

    expect(room.getSnapshot().remoteEdits).toEqual({});
  });

  describe("who changed a field", () => {
    /** 一位成员：有自己的文档（客户端编号）与在线状态，从服务端当前内容出发。 */
    function member(id: string, name: string) {
      const doc = new Y.Doc();
      Y.applyUpdate(doc, Y.encodeStateAsUpdate(server.docFor(REF)));
      const awareness = new Awareness(doc);
      awareness.setLocalState({ user: { id, name, color: "#2563eb" }, focus: null });
      return {
        doc,
        announce: () => server.deliverAwareness(REF, awareness),
        /** 在自己的文档上改内容，把增量经服务端推出去。 */
        write(value: Record<string, string>) {
          Y.applyUpdate(doc, Y.encodeStateAsUpdate(server.docFor(REF)));
          const before = Y.encodeStateVector(doc);
          applyJson(doc, value);
          const update = Y.encodeStateAsUpdate(doc, before);
          server.deliverUpdate(REF, update);
          return update;
        },
      };
    }

    async function joined() {
      const client = new CollabClient("ws://test/collab");
      const room = client.acquire(REF);
      await waitFor(room, "synced");
      room.markRendered(room.getSnapshot().json!);
      return room;
    }

    it("credits the member who wrote the new value, not the one whose value was replaced", async () => {
      const bob = member("u-bob", "bob");
      const amy = member("u-amy", "amy");
      const room = await joined();
      bob.announce();
      amy.announce();
      bob.write({ synopsis: "bob 的版本" });
      await settle();

      amy.write({ synopsis: "amy 的版本" });
      await settle();

      expect(room.getSnapshot().remoteEdits.synopsis).toMatchObject({ userId: "u-amy" });
    });

    it("does not credit anyone for a pure deletion, least of all the author of the deleted text", async () => {
      const bob = member("u-bob", "bob");
      const amy = member("u-amy", "amy");
      const room = await joined();
      bob.announce();
      amy.announce();
      bob.write({ synopsis: "bob 的版本" });
      await settle();
      const before = room.getSnapshot().remoteEdits;

      amy.write({ synopsis: "" });
      await settle();

      expect(room.getSnapshot().json).toEqual({ synopsis: "" });
      expect(room.getSnapshot().remoteEdits).toBe(before);
    });

    it("does not credit a member whose value the server overwrote", async () => {
      const bob = member("u-bob", "bob");
      const room = await joined();
      bob.announce();
      bob.write({ synopsis: "bob 的版本" });
      await settle();
      const before = room.getSnapshot().remoteEdits;

      server.externalChange(REF, { synopsis: "Agent 改写" });
      await settle();

      expect(room.getSnapshot().remoteEdits).toBe(before);
    });

    it("does not guess when one update carries several members' writing", async () => {
      const bob = member("u-bob", "bob");
      const amy = member("u-amy", "amy");
      const room = await joined();
      bob.announce();
      amy.announce();
      await settle();

      // 重连补送：两人的修改合在同一份更新里到达
      const merged = new Y.Doc();
      Y.applyUpdate(merged, Y.encodeStateAsUpdate(server.docFor(REF)));
      const base = Y.encodeStateVector(merged);
      bob.doc.getMap("unit").set("title", new Y.Text("bob"));
      amy.doc.getMap("unit").set("note", new Y.Text("amy"));
      Y.applyUpdate(merged, Y.encodeStateAsUpdate(bob.doc));
      Y.applyUpdate(merged, Y.encodeStateAsUpdate(amy.doc));
      server.deliverUpdate(REF, Y.encodeStateAsUpdate(merged, base));
      await settle();

      expect(room.getSnapshot().remoteEdits).toEqual({});
    });

    it("does not present my own edits from another tab as someone else's", async () => {
      const otherTab = member("u-me", "me");
      const room = await joined();
      otherTab.announce();
      await settle();

      otherTab.write({ synopsis: "另一个分页" });
      await settle();

      expect(room.getSnapshot().remoteEdits).toEqual({});
    });
  });

  it("answers flush requests", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");

    await expect(room.flush()).resolves.toBe(true);
  });

  it("falls back when the server refuses the login", async () => {
    server.acceptToken = null;
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);

    await waitFor(room, "unavailable");

    expect(client.unavailable).toBe(true);
  });

  it("falls back when no collaboration endpoint answers in time", async () => {
    vi.useFakeTimers();
    restore();
    class SilentSocket {
      readyState = 0;
      onopen = null;
      onmessage = null;
      onclose: ((event: { code: number }) => void) | null = null;
      onerror = null;
      send() {}
      close() {
        this.onclose?.({ code: 1006 });
      }
    }
    restore = (() => {
      const original = globalThis.WebSocket;
      (globalThis as { WebSocket: unknown }).WebSocket = SilentSocket;
      return () => {
        (globalThis as { WebSocket: unknown }).WebSocket = original;
      };
    })();
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);

    vi.advanceTimersByTime(5000);

    expect(room.getSnapshot().phase).toBe("unavailable");
  });

  it("goes offline and catches up after reconnecting", async () => {
    const client = new CollabClient("ws://test/collab");
    const room = client.acquire(REF);
    await waitFor(room, "synced");
    room.markRendered(room.getSnapshot().json!);

    server.sockets[0].serverClose(1006);
    expect(room.getSnapshot().phase).toBe("offline");
    // 离线期间打的字留在本机
    room.change({ synopsis: "雨夜（离线）" });
    expect(room.getSnapshot().pending).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 1100));
    await waitFor(room, "synced");
    await settle();

    expect(unitJson(server.docFor(REF))).toEqual({ synopsis: "雨夜（离线）" });
  });
});

describe("scriptItemRef", () => {
  it("drops the scripts/ prefix so both spellings share a room", () => {
    expect(scriptItemRef("demo", "scripts/episode_1.json", "E1S01")).toEqual(
      scriptItemRef("demo", "episode_1.json", "E1S01"),
    );
  });
});
