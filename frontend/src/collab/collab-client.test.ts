import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { CollabClient, scriptItemRef, type CollabRoom } from "./collab-client";
import { setToken } from "@/utils/auth";

import { FakeCollabServer } from "./collab-test-server";
import { unitJson } from "./ydoc-json";

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
