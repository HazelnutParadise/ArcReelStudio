import { useLayoutEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { LiveEditing } from "@/components/shared/edit-unit/useEditUnit";

import { caretCoordinates, type CaretPoint } from "./caret-coordinates";
import type { CollabPeer } from "./collab-client";

/**
 * 协作单元里一个输入框的外框：画出正在这个字段里的其他成员的光标与名字，并在框上加上对方的颜色。
 * 不在协作中（`live` 为 null）时原样渲染子元素，不多一层 DOM。
 */
export function CollabField({ live, path, children }: { live: LiveEditing | null; path: string; children: ReactNode }) {
  if (!live) return <>{children}</>;
  const here = live.peers.filter((peer) => peer.field === path);
  return (
    <div className="relative" data-collab-frame={path}>
      {children}
      {here.length > 0 && <PeerCarets live={live} path={path} peers={here} />}
    </div>
  );
}

function PeerCarets({ live, path, peers }: { live: LiveEditing; path: string; peers: CollabPeer[] }) {
  const { t } = useTranslation("dashboard");
  const [points, setPoints] = useState<Array<{ peer: CollabPeer; caret: CaretPoint | null }>>([]);
  const element = live.fieldElement(path);
  const value = element?.value;

  useLayoutEffect(() => {
    if (!element) {
      setPoints(peers.map((peer) => ({ peer, caret: null })));
      return;
    }
    const measure = () =>
      setPoints(
        peers.map((peer) => ({
          peer,
          caret: peer.selection ? caretCoordinates(element, peer.selection.head) : null,
        })),
      );
    measure();
    element.addEventListener("scroll", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => {
      element.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [element, peers, value]);

  const names = peers.map((peer) => peer.name).join("、");
  return (
    <>
      {/* 外框：对方在这个字段里时，框线用对方的颜色 */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-md ring-2"
        style={{ ["--tw-ring-color" as string]: peers[0].color }}
      />
      <span className="sr-only" role="status">
        {t("collab_peers_editing_field", { names })}
      </span>
      {points.map(({ peer, caret }) =>
        caret ? (
          <span
            key={peer.clientId}
            aria-hidden
            className="pointer-events-none absolute w-0.5"
            style={{ top: caret.top, left: caret.left, height: caret.height, backgroundColor: peer.color }}
          >
            <span
              className="absolute -top-4 left-0 rounded-sm px-1 text-[10px] leading-4 whitespace-nowrap text-white"
              style={{ backgroundColor: peer.color }}
            >
              {peer.name}
            </span>
          </span>
        ) : (
          <span
            key={peer.clientId}
            aria-hidden
            className="pointer-events-none absolute -top-2 right-2 rounded-sm px-1 text-[10px] leading-4 text-white"
            style={{ backgroundColor: peer.color }}
          >
            {peer.name}
          </span>
        ),
      )}
    </>
  );
}

/** 协作中的连线状态：即时同步中，或断线、修改留在本机。放在原本「未保存修改 / 已保存」的位置。 */
export function LiveStatus({ live }: { live: LiveEditing }) {
  const { t } = useTranslation("dashboard");
  const others = Array.from(new Map(live.peers.map((peer) => [peer.userId, peer])).values());
  return (
    <p role="status" className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
      <span
        aria-hidden
        className={
          live.connection === "synced"
            ? "size-1.5 shrink-0 rounded-full bg-good"
            : "size-1.5 shrink-0 rounded-full bg-warn"
        }
      />
      {live.connection === "synced" ? t("collab_status_live") : t("collab_status_offline")}
      {others.length > 0 && (
        <span className="flex items-center gap-1">
          {others.map((peer) => (
            <span
              key={peer.userId}
              title={peer.name}
              className="flex size-5 items-center justify-center rounded-full text-[10px] font-medium text-white"
              style={{ backgroundColor: peer.color }}
            >
              {peer.name.slice(0, 1).toUpperCase()}
            </span>
          ))}
        </span>
      )}
    </p>
  );
}

/** 协作中时绑到输入框上的属性（见 `LiveEditing.fieldProps`）；不在协作中时为空对象。 */
export function liveFieldProps(live: LiveEditing | null, path: string) {
  return live ? live.fieldProps(path) : {};
}
