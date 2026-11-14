import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";

import { useCollabRoom } from "@/collab/useCollabRoom";
import { useLiveFields } from "@/collab/useLiveFields";
import { jsonEqual, type UnitJson } from "@/collab/ydoc-json";

import type { CollabOptions, EditUnit, SaveAndGenerateOptions } from "./useEditUnit";

interface LiveEditUnitOptions<T> {
  collab: CollabOptions<T> | undefined;
  /** 已保存的内容：补齐房间文档里没有的部分。 */
  source: T;
  saved: T;
  /** 连上之前的编辑内容；与 `saved` 不同的字段在连上时带进房间。 */
  value: T;
  isEqual: (a: T, b: T) => boolean;
  /** 连上并带入修改后调用：本机的「未保存修改」已交给房间，回到已保存内容。 */
  onJoined: () => void;
}

/**
 * 编辑单元的多人即时协作部分：连上房间后，单元内容就是房间里的文档，输入即时同步、由服务端写回。
 * 连不上（或未开启协作）时返回 null，编辑单元照旧「改完再保存」。
 */
export function useLiveEditUnit<T>({
  collab,
  source,
  saved,
  value,
  isEqual,
  onJoined,
}: LiveEditUnitOptions<T>): { saving: boolean; unit: Omit<EditUnit<T>, "expectSource"> } | null {
  const { room, snapshot } = useCollabRoom(collab?.ref ?? null);
  const fromUnit = collab?.fromUnit;
  const toUnit = collab?.toUnit;
  const liveJson = snapshot.json;
  const isLive =
    room !== null &&
    liveJson !== null &&
    fromUnit !== undefined &&
    toUnit !== undefined &&
    (snapshot.phase === "synced" || snapshot.phase === "offline");
  const liveValue = useMemo(
    () => (fromUnit !== undefined && liveJson !== null && isLive ? fromUnit(liveJson, source) : null),
    [isLive, fromUnit, liveJson, source],
  );
  // 本机连续修改（重绘之前的第二次输入）以上一次修改后的内容为基准
  const latestLive = useRef<T | null>(null);
  useLayoutEffect(() => {
    if (!isLive || !room || !liveJson) return;
    room.markRendered(liveJson);
    latestLive.current = liveValue;
  }, [isLive, room, liveJson, liveValue]);

  // 连上之前已经改了的内容：只把改过的字段带进房间，不把别人此时的内容改回去
  const hasLocalEdits = !isEqual(value, saved);
  const carriedEdits = useMemo(
    () =>
      isLive && toUnit !== undefined && liveJson !== null && hasLocalEdits
        ? withLocalEdits(liveJson, toUnit(saved, liveJson), toUnit(value, liveJson))
        : null,
    [isLive, toUnit, liveJson, hasLocalEdits, saved, value],
  );
  const carried = useRef(false);
  useEffect(() => {
    if (!isLive || !room || carried.current) return;
    carried.current = true;
    if (carriedEdits) room.change(carriedEdits);
    onJoined();
  }, [isLive, room, carriedEdits, onJoined]);

  const setValue = useCallback(
    (next: T | ((prev: T) => T)) => {
      const prev = latestLive.current;
      if (!room || !toUnit || prev === null) return;
      const resolved = typeof next === "function" ? (next as (prev: T) => T)(prev) : next;
      latestLive.current = resolved;
      room.change(toUnit(resolved, room.getSnapshot().json ?? {}));
    },
    [room, toUnit],
  );
  const save = useCallback(async () => (room ? room.flush() : false), [room]);
  const saveAndGenerate = useCallback(
    async (generate: () => unknown, options?: SaveAndGenerateOptions) => {
      if (options?.confirm && !(await options.confirm())) return false;
      if (!(await save())) return false;
      await generate();
      return true;
    },
    [save],
  );
  const fields = useLiveFields(isLive ? room : null, liveJson);

  if (!isLive || liveValue === null) return null;
  const error = snapshot.saveState === "error" ? (snapshot.error?.message ?? null) : null;
  return {
    saving: snapshot.pending || snapshot.saveState === "saving",
    unit: {
      value: liveValue,
      savedValue: liveValue,
      setValue,
      dirty: false,
      // 写回在背景持续进行，不当作「保存中」：编辑区不会因此锁住输入框
      status: error !== null ? "error" : "idle",
      error,
      externallyUpdated: false,
      save,
      discard: noop,
      saveAndGenerate,
      live: {
        connection: snapshot.phase === "offline" ? "offline" : "synced",
        peers: snapshot.peers,
        fieldProps: fields.fieldProps,
        undo: fields.undo,
        redo: fields.redo,
        fieldElement: fields.elementFor,
      },
    },
  };
}

function noop(): void {}

/** 在房间当前内容上，只套用本机相对编辑起点改过的顶层字段；别人此时的内容不被改回去。 */
export function withLocalEdits(current: UnitJson, base: UnitJson, mine: UnitJson): UnitJson {
  const next: UnitJson = { ...current };
  for (const key of Object.keys(mine)) {
    if (!jsonEqual(mine[key], base[key])) next[key] = mine[key];
  }
  return next;
}
