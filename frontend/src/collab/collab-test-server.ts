import { fromBase64, toBase64 } from "lib0/buffer";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

import { applyJson, type UnitJson } from "./ydoc-json";

/**
 * 测试用的协作服务端：替换全局 WebSocket，按 `server/routers/collab.py` 的消息格式应答，每个房间一份 Yjs 文档。
 * 只实现单元测试要用到的部分：认证、加入、同步、写回（flush 直接应答成功）。
 */
export class FakeCollabServer {
  readonly sockets: FakeSocket[] = [];
  readonly docs = new Map<string, Y.Doc>();
  /** 认证时接受的令牌；为 null 时拒绝一切连线（关闭码 4401）。 */
  acceptToken: string | null = "token";
  /** 收到的全部消息，便于断言。 */
  readonly received: Array<Record<string, unknown>> = [];

  constructor(private readonly contents: Record<string, UnitJson> = {}) {}

  install(): () => void {
    const original = globalThis.WebSocket;
    class Socket extends FakeSocket {
      static owner: FakeCollabServer;
      constructor(url: string) {
        super(url, Socket.owner);
        Socket.owner.sockets.push(this);
      }
    }
    Socket.owner = this;
    (globalThis as { WebSocket: unknown }).WebSocket = Socket;
    return () => {
      (globalThis as { WebSocket: unknown }).WebSocket = original;
    };
  }

  docFor(room: { project: string; kind: string; key: string }): Y.Doc {
    const id = `${room.project}/${room.kind}/${room.key}`;
    let doc = this.docs.get(id);
    if (!doc) {
      doc = new Y.Doc();
      applyJson(doc, this.contents[id] ?? {});
      this.docs.set(id, doc);
    }
    return doc;
  }

  /** 服务端（如 Agent 的改动）直接改文档，并推给所有连线。 */
  externalChange(room: { project: string; kind: string; key: string }, value: UnitJson): void {
    const doc = this.docFor(room);
    const before = Y.encodeStateVector(doc);
    applyJson(doc, value);
    const update = Y.encodeStateAsUpdate(doc, before);
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, 0);
    syncProtocol.writeUpdate(encoder, update);
    for (const socket of this.sockets) {
      socket.deliver({ type: "sync", room, data: toBase64(encoding.toUint8Array(encoder)) });
    }
  }

  handle(socket: FakeSocket, message: Record<string, unknown>): void {
    this.received.push(message);
    const room = message.room as { project: string; kind: string; key: string } | undefined;
    switch (message.type) {
      case "auth":
        if (this.acceptToken === null || message.token !== this.acceptToken) {
          socket.serverClose(4401);
          return;
        }
        socket.deliver({ type: "ready", user: { user_id: "u-me", username: "me" } });
        return;
      case "join": {
        if (!room) return;
        const doc = this.docFor(room);
        socket.deliver({ type: "joined", room });
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, 0);
        syncProtocol.writeSyncStep1(encoder, doc);
        socket.deliver({ type: "sync", room, data: toBase64(encoding.toUint8Array(encoder)) });
        socket.deliver({ type: "status", room, state: "saved" });
        return;
      }
      case "sync": {
        if (!room) return;
        const doc = this.docFor(room);
        const decoder = decoding.createDecoder(fromBase64(message.data as string));
        decoding.readVarUint(decoder);
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, 0);
        syncProtocol.readSyncMessage(decoder, encoder, doc, "client");
        if (encoding.length(encoder) > 1) {
          socket.deliver({ type: "sync", room, data: toBase64(encoding.toUint8Array(encoder)) });
        }
        return;
      }
      case "flush":
        socket.deliver({ type: "flushed", room, id: message.id, ok: true });
        return;
    }
  }
}

export class FakeSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(
    readonly url: string,
    private readonly server: FakeCollabServer,
  ) {
    queueMicrotask(() => {
      if (this.readyState !== FakeSocket.CONNECTING) return;
      this.readyState = FakeSocket.OPEN;
      this.onopen?.();
    });
  }

  send(raw: string): void {
    if (this.readyState !== FakeSocket.OPEN) throw new Error("socket not open");
    const message = JSON.parse(raw) as Record<string, unknown>;
    queueMicrotask(() => this.server.handle(this, message));
  }

  deliver(message: Record<string, unknown>): void {
    if (this.readyState !== FakeSocket.OPEN) return;
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  serverClose(code: number): void {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code });
  }

  close(): void {
    if (this.readyState === FakeSocket.CLOSED) return;
    this.readyState = FakeSocket.CLOSED;
    queueMicrotask(() => this.onclose?.({ code: 1000 }));
  }
}
