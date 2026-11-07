import { fromBase64, toBase64 } from "lib0/buffer";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as awarenessProtocol from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

import { API_BASE } from "@/api/transport";
import i18n from "@/i18n";
import { getToken } from "@/utils/auth";

import { applyJson, jsonEqual, unitJson, type UnitJson } from "./ydoc-json";

/**
 * 多人即时协作的连线：每个分页一条 WebSocket，所有编辑单元的房间共用。
 *
 * - 连上后先送登录令牌，收到 `ready` 才加入房间；断线后按退避重连，重连时重新加入、互换状态向量，
 *   离线期间打的字随之补送。
 * - 连不上（服务端没有协作端点、认证失败、浏览器不支持）时把房间标成不可用，编辑区退回原来的「改完保存」方式。
 * - 本机的修改以 {@link LOCAL_ORIGIN} 为来源写进文档，撤销只撤自己的修改。
 */

export interface CollabRef {
  project: string;
  kind: string;
  key: string;
}

export type RoomPhase = "connecting" | "synced" | "offline" | "unavailable" | "removed";
export type RoomSaveState = "saved" | "saving" | "error";

export interface RoomSnapshot {
  phase: RoomPhase;
  saveState: RoomSaveState;
  error: { code: string; message: string } | null;
  /** 文档当前内容；还没同步完成时为 null。 */
  json: UnitJson | null;
  /** 有还没送到服务端的本机修改（离线时）。 */
  pending: boolean;
  peers: CollabPeer[];
}

export interface CollabPeer {
  clientId: number;
  userId: string;
  name: string;
  color: string;
  /** 正在编辑的字段路径（如 `synopsis`、`utterances.0.text`）；不在任何字段里时为 null。 */
  field: string | null;
  /** 光标与选区在该字段文字里的位置（Yjs 相对位置，经本机文档解析成下标）。 */
  selection: { anchor: number; head: number } | null;
  /** 鼠标指针（页面房间才有）：相对某个锚点元素的位置，见 `live-pointers`。 */
  pointer: PointerPosition | null;
}

/** 鼠标指针相对锚点元素的位置：`x`、`y` 是锚点内容区的比例（0–1）。 */
export interface PointerPosition {
  anchor: string;
  x: number;
  y: number;
}

export const LOCAL_ORIGIN = Symbol("collab-local");
const REMOTE_ORIGIN = Symbol("collab-remote");

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;
const CLOSE_UNAUTHORIZED = 4401;
/** 首次连线在这段时间内没有就绪，就当作服务端没有协作功能，编辑区退回原来的方式。 */
const FIRST_READY_TIMEOUT_MS = 5000;
const MAX_BACKOFF_MS = 30_000;
/** 离开编辑区后稍等再退出房间：同一单元在切页、重新挂载时不必重新同步。 */
const LEAVE_DELAY_MS = 3000;

const PEER_COLORS = ["#e11d48", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#4d7c0f"];

function roomId(ref: CollabRef): string {
  return `${ref.project}\u0000${ref.kind}\u0000${ref.key}`;
}

function colorFor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0;
  return PEER_COLORS[Math.abs(hash) % PEER_COLORS.length];
}

type Listener = () => void;

interface LocalPresence {
  field: string | null;
  anchor: Y.RelativePosition | null;
  head: Y.RelativePosition | null;
}

export class CollabRoom {
  readonly ref: CollabRef;
  readonly id: string;
  readonly doc = new Y.Doc();
  readonly awareness: awarenessProtocol.Awareness;
  readonly undoManager: Y.UndoManager;
  private readonly client: CollabClient;
  private listeners = new Set<Listener>();
  private snapshot: RoomSnapshot;
  private synced = false;
  private flushWaiters = new Map<number, (ok: boolean) => void>();
  refCount = 0;
  leaveTimer: ReturnType<typeof setTimeout> | null = null;
  /** 界面最近一次渲染所依据的内容与文档状态，本机修改以它为基准算差异。 */
  private rendered: { json: UnitJson; update: Uint8Array; stateVector: Uint8Array } | null = null;

  constructor(client: CollabClient, ref: CollabRef) {
    this.client = client;
    this.ref = ref;
    this.id = roomId(ref);
    this.awareness = new awarenessProtocol.Awareness(this.doc);
    this.undoManager = new Y.UndoManager(this.doc.getMap("unit"), { trackedOrigins: new Set([LOCAL_ORIGIN]) });
    this.snapshot = {
      phase: client.unavailable ? "unavailable" : "connecting",
      saveState: "saved",
      error: null,
      json: null,
      pending: false,
      peers: [],
    };
    this.doc.on("update", this.handleDocUpdate);
    this.awareness.on("update", this.handleAwarenessUpdate);
    this.awareness.on("change", this.handleAwarenessChange);
  }

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): RoomSnapshot => this.snapshot;

  private update(patch: Partial<RoomSnapshot>): void {
    const next = { ...this.snapshot, ...patch };
    if (
      next.phase === this.snapshot.phase &&
      next.saveState === this.snapshot.saveState &&
      next.error === this.snapshot.error &&
      next.json === this.snapshot.json &&
      next.pending === this.snapshot.pending &&
      next.peers === this.snapshot.peers
    ) {
      return;
    }
    this.snapshot = next;
    for (const listener of this.listeners) listener();
  }

  /** 界面渲染完这份内容后调用：之后的本机修改以它为基准。 */
  markRendered(json: UnitJson): void {
    if (this.rendered && this.rendered.json === json) return;
    if (!jsonEqual(json, unitJson(this.doc))) {
      // 渲染的是旧内容（远端更新已到、界面还没重绘）：保留上一份基准
      if (this.rendered) return;
    }
    this.rendered = {
      json,
      update: Y.encodeStateAsUpdate(this.doc),
      stateVector: Y.encodeStateVector(this.doc),
    };
  }

  /**
   * 本机把内容从界面上看到的样子改成 `next`。界面看到的就是文档当前内容时直接套差异；
   * 远端更新已经到了、界面还没重绘时，从界面看到的那份状态出发算出本机的增量，再与远端更新合并，
   * 不会把刚到的远端修改改回去。
   */
  change(next: UnitJson): void {
    if (!this.synced) return;
    const current = unitJson(this.doc);
    const base = this.rendered;
    if (!base || jsonEqual(base.json, current)) {
      applyJson(this.doc, next, LOCAL_ORIGIN);
      return;
    }
    const fork = new Y.Doc();
    Y.applyUpdate(fork, base.update);
    applyJson(fork, next);
    const delta = Y.encodeStateAsUpdate(fork, base.stateVector);
    fork.destroy();
    Y.applyUpdate(this.doc, delta, LOCAL_ORIGIN);
  }

  /** 立即写回（生成、预览前调用）；返回写回是否成功。不可用或离线时返回 false。 */
  flush(): Promise<boolean> {
    return this.client.flush(this);
  }

  setPointer(pointer: PointerPosition | null): void {
    this.awareness.setLocalStateField("pointer", pointer);
  }

  setPresence(presence: LocalPresence | null): void {
    if (!presence) {
      this.awareness.setLocalStateField("focus", null);
      return;
    }
    this.awareness.setLocalStateField("focus", {
      field: presence.field,
      anchor: presence.anchor ? Y.relativePositionToJSON(presence.anchor) : null,
      head: presence.head ? Y.relativePositionToJSON(presence.head) : null,
    });
  }

  // ── 由连线调用 ──────────────────────────────────────────────

  onConnected(user: { user_id: string; username: string }): void {
    this.awareness.setLocalStateField("user", { id: user.user_id, name: user.username, color: colorFor(user.user_id) });
    this.client.send({ type: "join", room: this.ref });
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, this.doc);
    this.client.sendData("sync", this.ref, encoding.toUint8Array(encoder));
    this.sendAwareness([this.doc.clientID]);
  }

  onDisconnected(unavailable: boolean): void {
    for (const resolve of this.flushWaiters.values()) resolve(false);
    this.flushWaiters.clear();
    awarenessProtocol.removeAwarenessStates(
      this.awareness,
      Array.from(this.awareness.getStates().keys()).filter((id) => id !== this.doc.clientID),
      REMOTE_ORIGIN,
    );
    this.update({ phase: unavailable && !this.synced ? "unavailable" : "offline" });
  }

  onMessage(message: ServerMessage): void {
    switch (message.type) {
      case "joined":
        return;
      case "sync": {
        const decoder = decoding.createDecoder(fromBase64(message.data));
        const encoder = encoding.createEncoder();
        if (decoding.readVarUint(decoder) !== MESSAGE_SYNC) return;
        encoding.writeVarUint(encoder, MESSAGE_SYNC);
        const syncType = syncProtocol.readSyncMessage(decoder, encoder, this.doc, REMOTE_ORIGIN);
        if (encoding.length(encoder) > 1) this.client.sendData("sync", this.ref, encoding.toUint8Array(encoder));
        // 服务端回给本机 step1 的 step2 到达：本机已拥有服务端的全部内容
        if (syncType === syncProtocol.messageYjsSyncStep2) this.markSynced();
        return;
      }
      case "awareness": {
        const decoder = decoding.createDecoder(fromBase64(message.data));
        if (decoding.readVarUint(decoder) !== MESSAGE_AWARENESS) return;
        awarenessProtocol.applyAwarenessUpdate(this.awareness, decoding.readVarUint8Array(decoder), REMOTE_ORIGIN);
        return;
      }
      case "status":
        this.update({ saveState: message.state, error: message.error ?? null });
        return;
      case "flushed": {
        const resolve = this.flushWaiters.get(message.id);
        this.flushWaiters.delete(message.id);
        resolve?.(message.ok);
        return;
      }
      case "removed":
        this.update({ phase: "removed" });
        return;
    }
  }

  registerFlush(id: number): Promise<boolean> {
    return new Promise((resolve) => this.flushWaiters.set(id, resolve));
  }

  destroy(): void {
    this.doc.off("update", this.handleDocUpdate);
    this.awareness.off("update", this.handleAwarenessUpdate);
    this.awareness.off("change", this.handleAwarenessChange);
    this.undoManager.destroy();
    this.awareness.destroy();
    this.doc.destroy();
    this.listeners.clear();
  }

  private markSynced(): void {
    this.synced = true;
    this.update({ phase: "synced", json: unitJson(this.doc), pending: false });
  }

  private handleDocUpdate = (update: Uint8Array, origin: unknown): void => {
    if (this.synced) this.update({ json: unitJson(this.doc) });
    if (origin === REMOTE_ORIGIN) return;
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    if (!this.client.sendData("sync", this.ref, encoding.toUint8Array(encoder))) {
      // 离线：重连后经状态向量互换补送
      this.update({ pending: true });
    }
  };

  private handleAwarenessUpdate = (
    { added, updated, removed }: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ): void => {
    if (origin === REMOTE_ORIGIN) return;
    const changed = [...added, ...updated, ...removed].filter((id) => id === this.doc.clientID);
    if (changed.length > 0) this.sendAwareness(changed);
  };

  private handleAwarenessChange = (): void => {
    const peers: CollabPeer[] = [];
    for (const [clientId, state] of this.awareness.getStates()) {
      if (clientId === this.doc.clientID) continue;
      const user = state.user as { id?: string; name?: string; color?: string } | undefined;
      if (!user?.id || !user.name) continue;
      const focus = state.focus as { field?: string | null; anchor?: unknown; head?: unknown } | null | undefined;
      peers.push({
        clientId,
        userId: user.id,
        name: user.name,
        color: user.color ?? colorFor(user.id),
        field: typeof focus?.field === "string" ? focus.field : null,
        selection: this.resolveSelection(focus),
        pointer: parsePointer(state.pointer),
      });
    }
    this.update({ peers });
  };

  private resolveSelection(
    focus: { anchor?: unknown; head?: unknown } | null | undefined,
  ): { anchor: number; head: number } | null {
    if (!focus?.anchor || !focus.head) return null;
    try {
      const anchor = Y.createAbsolutePositionFromRelativePosition(
        Y.createRelativePositionFromJSON(focus.anchor),
        this.doc,
      );
      const head = Y.createAbsolutePositionFromRelativePosition(Y.createRelativePositionFromJSON(focus.head), this.doc);
      if (!anchor || !head) return null;
      return { anchor: anchor.index, head: head.index };
    } catch {
      return null;
    }
  }

  private sendAwareness(clientIds: number[]): void {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(encoder, awarenessProtocol.encodeAwarenessUpdate(this.awareness, clientIds));
    this.client.sendData("awareness", this.ref, encoding.toUint8Array(encoder));
  }
}

function parsePointer(value: unknown): PointerPosition | null {
  if (!value || typeof value !== "object") return null;
  const { anchor, x, y } = value as Record<string, unknown>;
  if (typeof anchor !== "string" || typeof x !== "number" || typeof y !== "number") return null;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { anchor, x, y };
}

type ServerMessage =
  | { type: "ready"; user: { user_id: string; username: string } }
  | { type: "joined"; room: CollabRef }
  | { type: "sync" | "awareness"; room: CollabRef; data: string }
  | { type: "status"; room: CollabRef; state: RoomSaveState; error?: { code: string; message: string } }
  | { type: "flushed"; room: CollabRef; id: number; ok: boolean }
  | { type: "removed"; room: CollabRef; reason: string }
  | { type: "error"; code: string };

export class CollabClient {
  private socket: WebSocket | null = null;
  private ready = false;
  private everReady = false;
  private user: { user_id: string; username: string } | null = null;
  private rooms = new Map<string, CollabRoom>();
  private backoff = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readyTimer: ReturnType<typeof setTimeout> | null = null;
  private nextFlushId = 1;
  /** 服务端没有协作功能、认证失败或浏览器不支持：编辑区退回原来的方式。 */
  unavailable = typeof WebSocket === "undefined";
  private readonly url: string;

  constructor(url?: string) {
    const scheme = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
    const host = typeof location !== "undefined" ? location.host : "localhost";
    this.url = url ?? `${scheme}://${host}${API_BASE}/collab`;
  }

  /** 加入房间；同一单元重复加入共用同一个房间。用完调用 {@link release}。 */
  acquire(ref: CollabRef): CollabRoom {
    const id = roomId(ref);
    let room = this.rooms.get(id);
    if (!room) {
      room = new CollabRoom(this, ref);
      this.rooms.set(id, room);
      if (this.ready && this.user) room.onConnected(this.user);
      else this.connect();
    }
    if (room.leaveTimer) {
      clearTimeout(room.leaveTimer);
      room.leaveTimer = null;
    }
    room.refCount++;
    return room;
  }

  release(room: CollabRoom): void {
    room.refCount--;
    if (room.refCount > 0) return;
    room.leaveTimer = setTimeout(() => {
      if (room.refCount > 0) return;
      this.rooms.delete(room.id);
      this.send({ type: "leave", room: room.ref });
      room.destroy();
      if (this.rooms.size === 0) this.disconnect();
    }, LEAVE_DELAY_MS);
  }

  send(message: Record<string, unknown>): boolean {
    if (!this.socket || !this.ready || this.socket.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  sendData(type: "sync" | "awareness", ref: CollabRef, data: Uint8Array): boolean {
    return this.send({ type, room: ref, data: toBase64(data) });
  }

  flush(room: CollabRoom): Promise<boolean> {
    const id = this.nextFlushId++;
    const waiting = room.registerFlush(id);
    if (!this.send({ type: "flush", room: room.ref, id })) {
      room.onMessage({ type: "flushed", room: room.ref, id, ok: false });
    }
    return waiting;
  }

  private connect(): void {
    if (this.unavailable || this.socket || this.reconnectTimer) return;
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch {
      this.markUnavailable();
      return;
    }
    this.socket = socket;
    if (!this.everReady) {
      this.readyTimer = setTimeout(() => {
        if (!this.everReady) {
          this.markUnavailable();
          socket.close();
        }
      }, FIRST_READY_TIMEOUT_MS);
    }
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: "auth", token: getToken() ?? "", locale: i18n.language || "zh" }));
    };
    socket.onmessage = (event) => this.handleMessage(event.data);
    socket.onclose = (event) => this.handleClose(socket, event.code);
    socket.onerror = () => {
      // 关闭事件随后到达，在那里处理
    };
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== "string") return;
    let message: ServerMessage;
    try {
      message = JSON.parse(raw) as ServerMessage;
    } catch {
      return;
    }
    if (message.type === "ready") {
      this.ready = true;
      this.everReady = true;
      this.backoff = 1000;
      this.user = message.user;
      if (this.readyTimer) clearTimeout(this.readyTimer);
      for (const room of this.rooms.values()) room.onConnected(message.user);
      return;
    }
    if (message.type === "error") return;
    this.rooms.get(roomId(message.room))?.onMessage(message);
  }

  private handleClose(socket: WebSocket, code: number): void {
    if (this.socket !== socket) return;
    this.socket = null;
    this.ready = false;
    if (code === CLOSE_UNAUTHORIZED || !this.everReady) {
      this.markUnavailable();
      return;
    }
    for (const room of this.rooms.values()) room.onDisconnected(false);
    if (this.rooms.size === 0) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.backoff);
    this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
  }

  private markUnavailable(): void {
    this.unavailable = true;
    if (this.readyTimer) clearTimeout(this.readyTimer);
    for (const room of this.rooms.values()) room.onDisconnected(true);
  }

  private disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const socket = this.socket;
    this.socket = null;
    this.ready = false;
    socket?.close();
  }

  /** 登录身份变了（登出、换账号）时重建连线。 */
  reset(): void {
    this.disconnect();
    this.unavailable = typeof WebSocket === "undefined";
    this.everReady = false;
    if (this.rooms.size > 0) this.connect();
  }
}

let shared: CollabClient | null = null;
let enabled = import.meta.env.MODE !== "test";

/** 单元测试默认不连协作端点；需要时由测试打开。 */
export function setCollabEnabled(value: boolean, client?: CollabClient): void {
  enabled = value;
  shared = client ?? null;
}

export function collabClient(): CollabClient | null {
  if (!enabled) return null;
  shared ??= new CollabClient();
  return shared;
}

/** 剧本里一格的房间键：剧本文件名统一去掉 `scripts/` 前缀，同一格不会因写法不同被分成两个房间。 */
export function scriptItemRef(project: string, scriptFile: string, itemId: string): CollabRef {
  const normalized = scriptFile.replaceAll("\\", "/").replace(/^scripts\//, "");
  return { project, kind: "script_item", key: `${normalized}#${itemId}` };
}
