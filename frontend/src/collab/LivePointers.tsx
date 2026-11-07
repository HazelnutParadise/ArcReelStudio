import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { CollabPeer, CollabRoom, PointerPosition } from "./collab-client";
import { useCollabRoom } from "./useCollabRoom";

/** 指针位置最多每秒送这么多次。 */
const SEND_INTERVAL_MS = 50;

/**
 * 同一页面上其他成员的鼠标指针（Figma 那样的彩色箭头加名字）。
 *
 * 位置不送屏幕坐标：两个人的窗口大小、卷动位置不同。送的是「锚点元素 + 在它里面的比例」：
 * 指在协作输入框上时以那个输入框为锚点；否则以指针下方的元素为锚点（按从 body 往下的路径找）。
 * 对方那里找到同一个锚点、而且锚点在画面内才画，找不到（如对方没打开同一个面板）或卷到画面外就不画。
 */
export function LivePointers({ project, page }: { project: string | null; page: string }) {
  const ref = useMemo(() => (project ? { project, kind: "page", key: page } : null), [project, page]);
  const { room, snapshot } = useCollabRoom(ref);
  const live = room !== null && (snapshot.phase === "synced" || snapshot.phase === "offline");

  useBroadcastPointer(live ? room : null);
  const peers = snapshot.peers.filter((peer) => peer.pointer !== null);
  if (!live || peers.length === 0 || typeof document === "undefined") return null;
  return createPortal(<PeerPointers peers={peers} />, document.body);
}

function useBroadcastPointer(room: CollabRoom | null): void {
  useEffect(() => {
    if (!room) return;
    let last = 0;
    let pending: PointerPosition | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const flush = () => {
      timer = null;
      last = Date.now();
      room.setPointer(pending);
    };
    const schedule = (next: PointerPosition | null) => {
      pending = next;
      if (timer) return;
      const wait = Math.max(0, SEND_INTERVAL_MS - (Date.now() - last));
      timer = setTimeout(flush, wait);
    };
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      schedule(pointerFromEvent(event));
    };
    const onLeave = () => schedule(null);
    document.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    window.addEventListener("blur", onLeave);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      if (timer) clearTimeout(timer);
      room.setPointer(null);
    };
  }, [room]);
}

function PeerPointers({ peers }: { peers: CollabPeer[] }) {
  // 卷动、缩放窗口时重新定位
  const [, setTick] = useState(0);
  useEffect(() => {
    let frame = 0;
    const bump = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setTick((n) => n + 1));
    };
    window.addEventListener("scroll", bump, true);
    window.addEventListener("resize", bump);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", bump, true);
      window.removeEventListener("resize", bump);
    };
  }, []);

  return (
    <div aria-hidden>
      {peers.map((peer) => {
        const point = peer.pointer ? resolvePointer(peer.pointer) : null;
        if (!point) return null;
        return (
          <div
            key={peer.clientId}
            className="pointer-events-none fixed top-0 left-0 translate-x-(--pointer-x) translate-y-(--pointer-y) transition-transform duration-fast ease-emphasized"
            style={
              {
                "--peer-color": peer.color,
                "--pointer-x": `${point.left}px`,
                "--pointer-y": `${point.top}px`,
              } as CSSProperties
            }
          >
            <svg width="18" height="18" viewBox="0 0 18 18" className="drop-shadow-sm">
              <path
                d="M2 2 L2 15 L6 11 L9 17 L11.5 16 L8.5 10 L14 10 Z"
                className="fill-(--peer-color) stroke-card"
                strokeWidth="1.2"
              />
            </svg>
            <span className="absolute top-4 left-3.5 rounded-sm bg-(--peer-color) px-1.5 py-0.5 text-xs leading-none whitespace-nowrap text-white shadow-sm">
              {peer.name}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── 锚点 ──────────────────────────────────────────────────────

const FIELD_SELECTOR = "[data-collab-field],[data-collab-frame]";

export function pointerFromEvent(event: {
  target: EventTarget | null;
  clientX: number;
  clientY: number;
}): PointerPosition | null {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return null;
  const field = target.closest(FIELD_SELECTOR);
  if (field) {
    const name = field.getAttribute("data-collab-field") ?? field.getAttribute("data-collab-frame") ?? "";
    const rect = field.getBoundingClientRect();
    return {
      anchor: `field:${name}`,
      x: ratio(event.clientX - rect.left, rect.width),
      y: ratio(event.clientY - rect.top, rect.height),
    };
  }
  const rect = target.getBoundingClientRect();
  return {
    anchor: `element:${domPath(target)}`,
    x: ratio(event.clientX - rect.left, rect.width),
    y: ratio(event.clientY - rect.top, rect.height),
  };
}

export function resolvePointer(pointer: PointerPosition): { left: number; top: number } | null {
  const element = anchorElement(pointer.anchor);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const left = rect.left + pointer.x * rect.width;
  const top = rect.top + pointer.y * rect.height;
  // 锚点卷到画面外（自己这边看不到那一段）时不画
  if (top < 0 || left < 0 || top > window.innerHeight || left > window.innerWidth) return null;
  return { left, top };
}

function anchorElement(anchor: string): Element | null {
  if (anchor.startsWith("field:")) {
    const name = CSS.escape(anchor.slice("field:".length));
    return document.querySelector(`[data-collab-field="${name}"],[data-collab-frame="${name}"]`);
  }
  if (anchor.startsWith("element:")) return elementAtPath(anchor.slice("element:".length));
  return null;
}

function ratio(offset: number, size: number): number {
  if (size <= 0) return 0;
  return Math.min(1, Math.max(0, offset / size));
}

/** 从 body 往下的元素路径（标签名加同类序号），两边打开同一页面时指向同一个元素。 */
function domPath(element: Element): string {
  const parts: string[] = [];
  let node: Element | null = element;
  while (node && node !== document.body) {
    const parent: Element | null = node.parentElement;
    if (!parent) break;
    const tag = node.tagName;
    const index = Array.from(parent.children)
      .filter((child) => child.tagName === tag)
      .indexOf(node);
    parts.unshift(`${tag.toLowerCase()}:${index}`);
    node = parent;
  }
  return parts.join("/");
}

function elementAtPath(path: string): Element | null {
  if (path === "") return document.body;
  let node: Element | null = document.body;
  for (const part of path.split("/")) {
    const [tag, rawIndex] = part.split(":");
    const index = Number(rawIndex);
    if (!node || !tag || !Number.isInteger(index)) return null;
    const children: Element[] = Array.from(node.children).filter((child) => child.tagName.toLowerCase() === tag);
    node = children[index] ?? null;
  }
  return node;
}
