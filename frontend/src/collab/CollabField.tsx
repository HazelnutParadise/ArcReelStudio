import { useLayoutEffect, useState, type CSSProperties, type ReactNode } from "react";
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
  return (
    <div className="relative" data-collab-frame={path}>
      {children}
      <CollabCarets live={live} path={path} />
    </div>
  );
}

/** 只画其他人的光标与外框，交给已经有定位容器的输入框（如带着色镜像层的编辑器）自己摆放。 */
export function CollabCarets({ live, path }: { live: LiveEditing | null; path: string }) {
  const here = live ? live.peers.filter((peer) => peer.field === path) : [];
  if (!live || here.length === 0) return null;
  return <PeerCarets live={live} path={path} peers={here} />;
}

function PeerCarets({ live, path, peers }: { live: LiveEditing; path: string; peers: CollabPeer[] }) {
  const { t } = useTranslation("dashboard");
  const [measured, setMeasured] = useState<Array<{ peer: CollabPeer; caret: CaretPoint | null }>>([]);
  const element = live.fieldElement(path);
  const value = element?.value;

  useLayoutEffect(() => {
    if (!element) return;
    // 在输入框卷动、改变大小时重量光标位置；首次量在下一帧，跟着输入框完成排版
    const measure = () =>
      setMeasured(
        peers.map((peer) => ({
          peer,
          caret: peer.selection ? caretCoordinates(element, peer.selection.head) : null,
        })),
      );
    const frame = requestAnimationFrame(measure);
    element.addEventListener("scroll", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      element.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [element, peers, value]);
  // 量到之前（或找不到输入框时）先只标名字，不画光标
  const points = element ? measured : peers.map((peer) => ({ peer, caret: null }));

  const names = peers.map((peer) => peer.name).join("、");
  return (
    <>
      {/* 外框：对方在这个字段里时，框线用对方的颜色 */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-md ring-2 ring-(--peer-color)"
        style={{ "--peer-color": peers[0].color } as CSSProperties}
      />
      <span className="sr-only" role="status">
        {t("collab_peers_editing_field", { names })}
      </span>
      {points.map(({ peer, caret }) =>
        caret ? (
          <span
            key={peer.clientId}
            aria-hidden
            className="pointer-events-none absolute top-(--caret-top) left-(--caret-left) h-(--caret-height) w-0.5 bg-(--peer-color)"
            style={
              {
                "--peer-color": peer.color,
                "--caret-top": `${caret.top}px`,
                "--caret-left": `${caret.left}px`,
                "--caret-height": `${caret.height}px`,
              } as CSSProperties
            }
          >
            <span className="absolute -top-4 left-0 rounded-sm bg-(--peer-color) px-1 text-xs leading-4 whitespace-nowrap text-white">
              {peer.name}
            </span>
          </span>
        ) : (
          <span
            key={peer.clientId}
            aria-hidden
            className="pointer-events-none absolute -top-2 right-2 rounded-sm bg-(--peer-color) px-1 text-xs leading-4 text-white"
            style={{ "--peer-color": peer.color } as CSSProperties}
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
              className="flex size-5 items-center justify-center rounded-full bg-(--peer-color) text-xs font-medium text-white"
              style={{ "--peer-color": peer.color } as CSSProperties}
            >
              {peer.name.slice(0, 1).toUpperCase()}
            </span>
          ))}
        </span>
      )}
    </p>
  );
}
