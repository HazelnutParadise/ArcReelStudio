import { create } from "zustand";

import { API } from "@/api";
import type { ProviderCredential } from "@/types";

/**
 * 全部内置供应商的连线（凭证）。各处的连线下拉共用一份；新增、删除、改名或换默认连线后调用 `refresh`。
 */
interface ConnectionsState {
  connections: ProviderCredential[];
  loaded: boolean;
  /** 还没载入时载入一次。 */
  fetch: () => Promise<void>;
  refresh: () => Promise<void>;
}

let inflight: Promise<void> | null = null;

export const useConnectionsStore = create<ConnectionsState>((set, get) => ({
  connections: [],
  loaded: false,
  fetch: async () => {
    if (get().loaded) return;
    await get().refresh();
  },
  refresh: async () => {
    inflight ??= API.listAllCredentials()
      .then((res) => set({ connections: res.credentials, loaded: true }))
      .finally(() => {
        inflight = null;
      });
    await inflight;
  },
}));

/** 某个供应商的连线，按建立时间排列。 */
export function connectionsOf(connections: readonly ProviderCredential[], provider: string): ProviderCredential[] {
  return connections.filter((connection) => connection.provider === provider);
}
