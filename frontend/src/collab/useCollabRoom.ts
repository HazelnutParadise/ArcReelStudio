import { useEffect, useState, useSyncExternalStore } from "react";
import * as Y from "yjs";

import { collabClient, type CollabRef, type CollabRoom, type RoomSnapshot } from "./collab-client";

const IDLE_SNAPSHOT: RoomSnapshot = {
  phase: "unavailable",
  saveState: "saved",
  error: null,
  json: null,
  pending: false,
  peers: [],
};

const noopSubscribe = () => () => {};

/** 加入一个编辑单元的协作房间；`ref` 为 null 或协作不可用时返回 null 房间与不可用状态。 */
export function useCollabRoom(ref: CollabRef | null): { room: CollabRoom | null; snapshot: RoomSnapshot } {
  const project = ref?.project;
  const kind = ref?.kind;
  const key = ref?.key;
  const [room, setRoom] = useState<CollabRoom | null>(null);

  useEffect(() => {
    const client = collabClient();
    if (!client || project === undefined || kind === undefined || key === undefined) {
      setRoom(null);
      return;
    }
    const acquired = client.acquire({ project, kind, key });
    setRoom(acquired);
    return () => {
      client.release(acquired);
      setRoom((current) => (current === acquired ? null : current));
    };
  }, [project, kind, key]);

  const snapshot = useSyncExternalStore(
    room?.subscribe ?? noopSubscribe,
    room?.getSnapshot ?? (() => IDLE_SNAPSHOT),
    () => IDLE_SNAPSHOT,
  );
  return { room, snapshot };
}

/** 文档里路径 `path`（以 `.` 分隔，清单下标为数字）上的共享文字；不是文字时返回 null。 */
export function textAt(room: CollabRoom, path: string): Y.Text | null {
  let node: unknown = room.doc.getMap("unit");
  for (const part of path.split(".")) {
    if (node instanceof Y.Map) node = node.get(part);
    else if (node instanceof Y.Array) node = node.get(Number(part));
    else return null;
  }
  return node instanceof Y.Text ? node : null;
}
