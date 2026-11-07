import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { CollabPeer, CollabRoom, PointerPosition } from "./collab-client";
import { pointerFromEvent, resolvePointer } from "./pointer-anchor";
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
