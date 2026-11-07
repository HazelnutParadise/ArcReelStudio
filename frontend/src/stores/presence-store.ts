import { create } from "zustand";

import type { ProjectPresenceMember } from "@/types";

interface PresenceState {
  /** 名单所属的项目；离开项目后为 null。 */
  projectName: string | null;
  /** 项目在线成员（含自己），按用户名排序。 */
  members: ProjectPresenceMember[];
  setMembers: (projectName: string, members: ProjectPresenceMember[]) => void;
  clear: () => void;
}

/** 当前项目的在线成员名单：报到响应与项目事件流的 `presence` 事件都写到这里。 */
export const usePresenceStore = create<PresenceState>((set) => ({
  projectName: null,
  members: [],
  setMembers: (projectName, members) => set({ projectName, members }),
  clear: () => set({ projectName: null, members: [] }),
}));
