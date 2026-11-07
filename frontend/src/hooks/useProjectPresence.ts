import { useEffect, useRef } from "react";
import { useLocation } from "wouter";

import { API } from "@/api";
import { ROUTE_APP_PROJECTS } from "@/app-routes";
import { usePresenceStore } from "@/stores/presence-store";

/** 报到间隔；服务端 45 秒没收到报到就视为离开。 */
export const PRESENCE_HEARTBEAT_MS = 20_000;

/** 本标签页的标识：每次载入页面重新生成，同一标签页里切换项目时沿用。 */
const TAB_ID =
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `tab-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;

/**
 * 工作区内的位置：去掉项目前缀与首尾斜杠，如 `episodes/3`；在项目首页时为 null。
 * 嵌套路由里 `useLocation` 拿到的是项目内的相对路径，完整路径同样能处理。
 */
export function workspaceView(location: string, projectName: string): string | null {
  let path = location.split("?")[0].replace(/^\/+|\/+$/g, "");
  const prefix = `${ROUTE_APP_PROJECTS.replace(/^\/+/, "")}/${encodeURIComponent(projectName)}`;
  if (path === prefix) return null;
  if (path.startsWith(`${prefix}/`)) path = path.slice(prefix.length + 1);
  return path ? path.slice(0, 200) : null;
}

/**
 * 打开项目期间定时报到在线与正在看的位置，切换页面时立即再报；离开项目或关闭标签页时离开。
 * 名单写入 `usePresenceStore`，之后的变化由项目事件流的 `presence` 事件推送。
 */
export function useProjectPresence(projectName: string | null) {
  const [location] = useLocation();
  const view = projectName ? workspaceView(location, projectName) : null;
  const viewRef = useRef(view);
  const reportRef = useRef<(() => void) | null>(null);

  // 先于下面两个 effect 同步：报到读到的总是本次渲染的位置
  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  useEffect(() => {
    if (!projectName) return;
    let active = true;
    const report = () => {
      if (!active) return;
      API.reportPresence(projectName, TAB_ID, viewRef.current)
        .then(({ members }) => {
          if (active) usePresenceStore.getState().setMembers(projectName, members);
        })
        // 报到失败不打扰用户：下一次报到或事件流会补上名单
        .catch(() => {});
    };
    const leave = () => {
      API.leavePresence(projectName, TAB_ID).catch(() => {});
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") report();
    };
    reportRef.current = report;
    report();
    const timer = window.setInterval(report, PRESENCE_HEARTBEAT_MS);
    window.addEventListener("pagehide", leave);
    window.addEventListener("pageshow", report);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      reportRef.current = null;
      window.clearInterval(timer);
      window.removeEventListener("pagehide", leave);
      window.removeEventListener("pageshow", report);
      document.removeEventListener("visibilitychange", onVisible);
      leave();
      usePresenceStore.getState().clear();
    };
  }, [projectName]);

  // 切换页面立即报到；首次挂载由上面的报到负责
  const firstView = useRef(true);
  useEffect(() => {
    if (firstView.current) {
      firstView.current = false;
      return;
    }
    reportRef.current?.();
  }, [view]);
}
