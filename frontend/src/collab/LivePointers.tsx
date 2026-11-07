import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import type { CollabPeer, CollabRoom, PointerPosition } from "./collab-client";
import { useCollabRoom } from "./useCollabRoom";

/** 指针位置最多每秒送这么多次。 */
const SEND_INTERVAL_MS = 50;

/**
 * 同一页面上其他成员的鼠标指针（Figma 那样的彩色箭头加名字）。
 *
 * 位置不送屏幕坐标：两个人的窗口大小、卷动位置不同。送的是「锚点元素 + 在它内容区里的比例」：
 * 指在协作输入框上时以那个输入框为锚点；否则以所在的卷动区（或整个页面）为锚点，纵向按卷动内容的总高度算比例。
 * 对方那里找到同一个锚点才画，找不到（如对方没打开同一个面板）就不画。
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
    <div aria-hidden className="pointer-events-none fixed inset-0 z-[60] overflow-hidden">
      {peers.map((peer) => {
        const point = peer.pointer ? resolvePointer(peer.pointer) : null;
        if (!point) return null;
        return (
          <div
            key={peer.clientId}
            className="absolute top-0 left-0 transition-transform duration-75 ease-linear"
            style={{ transform: `translate(${point.left}px, ${point.top}px)` }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" className="drop-shadow-sm">
              <path
                d="M2 2 L2 15 L6 11 L9 17 L11.5 16 L8.5 10 L14 10 Z"
                fill={peer.color}
                stroke="white"
                strokeWidth="1.2"
              />
            </svg>
            <span
              className="absolute top-4 left-3.5 rounded-sm px-1.5 py-0.5 text-[11px] leading-none whitespace-nowrap text-white shadow-sm"
              style={{ backgroundColor: peer.color }}
            >
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
  const scroller = scrollContainerOf(target);
  if (!scroller) return null;
  const rect =
    scroller === document.documentElement
      ? new DOMRect(0, 0, window.innerWidth, window.innerHeight)
      : scroller.getBoundingClientRect();
  return {
    anchor: `scroll:${domPath(scroller)}`,
    x: ratio(event.clientX - rect.left, rect.width),
    y: ratio(event.clientY - rect.top + scroller.scrollTop, Math.max(scroller.scrollHeight, rect.height)),
  };
}

export function resolvePointer(pointer: PointerPosition): { left: number; top: number } | null {
  if (pointer.anchor.startsWith("field:")) {
    const name = CSS.escape(pointer.anchor.slice("field:".length));
    const field = document.querySelector(`[data-collab-field="${name}"],[data-collab-frame="${name}"]`);
    if (!field) return null;
    const rect = field.getBoundingClientRect();
    return { left: rect.left + pointer.x * rect.width, top: rect.top + pointer.y * rect.height };
  }
  if (pointer.anchor.startsWith("scroll:")) {
    const scroller = elementAtPath(pointer.anchor.slice("scroll:".length));
    if (!scroller) return null;
    const rect =
      scroller === document.documentElement
        ? new DOMRect(0, 0, window.innerWidth, window.innerHeight)
        : scroller.getBoundingClientRect();
    const contentHeight = Math.max(scroller.scrollHeight, rect.height);
    const top = rect.top + pointer.y * contentHeight - scroller.scrollTop;
    // 指在对方卷不到的地方（自己这边还看不到那一段）时不画
    if (top < rect.top - 4 || top > rect.bottom + 4) return null;
    return { left: rect.left + pointer.x * rect.width, top };
  }
  return null;
}

function ratio(offset: number, size: number): number {
  if (size <= 0) return 0;
  return Math.min(1, Math.max(0, offset / size));
}

function scrollContainerOf(element: Element): Element | null {
  let node: Element | null = element;
  while (node && node !== document.body && node !== document.documentElement) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return document.scrollingElement ?? document.documentElement;
}

/** 从 body 往下的元素路径（标签名加同类序号），两边打开同一页面时指向同一个元素。 */
function domPath(element: Element): string {
  if (element === document.documentElement || element === document.scrollingElement) return "";
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
  if (path === "") return document.scrollingElement ?? document.documentElement;
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
