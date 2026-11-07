import { useCallback, useLayoutEffect, useMemo, useRef } from "react";
import type { FocusEvent, KeyboardEvent, SyntheticEvent } from "react";
import * as Y from "yjs";

import type { CollabRoom } from "./collab-client";
import { textAt } from "./useCollabRoom";
import type { UnitJson } from "./ydoc-json";

type FieldElement = HTMLInputElement | HTMLTextAreaElement;

/** 绑到协作单元里一个输入框上的属性。 */
export interface CollabFieldProps {
  "data-collab-field": string;
  ref: (el: FieldElement | null) => void;
  onFocus: (event: FocusEvent<FieldElement>) => void;
  onBlur: () => void;
  onSelect: (event: SyntheticEvent<FieldElement>) => void;
  onInput: (event: SyntheticEvent<FieldElement>) => void;
  onKeyDown: (event: KeyboardEvent<FieldElement>) => void;
}

interface FocusState {
  path: string;
  anchor: Y.RelativePosition | null;
  head: Y.RelativePosition | null;
}

/**
 * 协作单元里输入框的绑定：
 * - 把自己的光标与选区（以 Yjs 相对位置表示）广播给同一单元里的其他人；
 * - 远端改动让输入框重新赋值时，按相对位置把自己的光标放回原处，不被推到结尾；
 * - Ctrl/⌘+Z、Ctrl/⌘+Shift+Z、Ctrl+Y 撤销与重做自己的修改，不动别人的。
 */
export function useLiveFields(room: CollabRoom | null, json: UnitJson | null) {
  const elements = useRef(new Map<string, FieldElement>());
  const focus = useRef<FocusState | null>(null);
  // 同一个输入框每次渲染拿到同一份属性，换了房间才重建
  const cache = useRef({ room: null as CollabRoom | null, props: new Map<string, CollabFieldProps>() });

  const capture = useCallback(
    (path: string, el: FieldElement) => {
      if (!room) return;
      const text = textAt(room, path);
      const anchor = text ? Y.createRelativePositionFromTypeIndex(text, el.selectionStart ?? 0) : null;
      const head = text ? Y.createRelativePositionFromTypeIndex(text, el.selectionEnd ?? 0) : null;
      focus.current = { path, anchor, head };
      room.setPresence({ field: path, anchor, head });
    },
    [room],
  );

  const undo = useCallback(() => room?.undoManager.undo(), [room]);
  const redo = useCallback(() => room?.undoManager.redo(), [room]);

  // 远端改动重新赋值后，把聚焦输入框的光标放回相对位置所指的地方
  useLayoutEffect(() => {
    const state = focus.current;
    if (!room || !state || !json) return;
    const el = elements.current.get(state.path);
    if (!el || document.activeElement !== el || !state.anchor || !state.head) return;
    const anchor = Y.createAbsolutePositionFromRelativePosition(state.anchor, room.doc);
    const head = Y.createAbsolutePositionFromRelativePosition(state.head, room.doc);
    if (!anchor || !head) return;
    const start = Math.min(anchor.index, head.index);
    const end = Math.max(anchor.index, head.index);
    if (el.selectionStart !== start || el.selectionEnd !== end) {
      el.setSelectionRange(start, end, anchor.index > head.index ? "backward" : "forward");
    }
  }, [room, json]);

  const fieldProps = useCallback(
    (path: string): CollabFieldProps => {
      if (cache.current.room !== room) cache.current = { room, props: new Map() };
      const cached = cache.current.props.get(path);
      if (cached) return cached;
      const props: CollabFieldProps = {
        "data-collab-field": path,
        ref: (el) => {
          if (el) elements.current.set(path, el);
          else elements.current.delete(path);
        },
        onFocus: (event) => capture(path, event.currentTarget),
        onSelect: (event) => capture(path, event.currentTarget),
        // 打字（尤其输入法上字）不一定触发选取事件：输入后也广播一次光标，等本机修改进了文档再算位置
        onInput: (event) => {
          const el = event.currentTarget;
          queueMicrotask(() => capture(path, el));
        },
        onBlur: () => {
          if (focus.current?.path === path) focus.current = null;
          room?.setPresence(null);
        },
        onKeyDown: (event) => {
          const mod = event.metaKey || event.ctrlKey;
          if (!mod || event.altKey) return;
          const key = event.key.toLowerCase();
          if (key === "z") {
            event.preventDefault();
            if (event.shiftKey) redo();
            else undo();
          } else if (key === "y" && event.ctrlKey) {
            event.preventDefault();
            redo();
          }
        },
      };
      cache.current.props.set(path, props);
      return props;
    },
    [capture, room, undo, redo],
  );

  const elementFor = useCallback((path: string) => elements.current.get(path) ?? null, []);

  return useMemo(() => ({ fieldProps, undo, redo, elementFor }), [fieldProps, undo, redo, elementFor]);
}
