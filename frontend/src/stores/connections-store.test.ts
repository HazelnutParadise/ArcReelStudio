import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useConnectionsStore } from "@/stores/connections-store";

describe("useConnectionsStore", () => {
  beforeEach(() => {
    useConnectionsStore.setState({ connections: [], loaded: false });
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not reject when loading fails, and retries on the next fetch", async () => {
    const list = vi.spyOn(API, "listAllCredentials").mockRejectedValueOnce(new Error("offline"));
    await expect(useConnectionsStore.getState().fetch()).resolves.toBeUndefined();
    expect(useConnectionsStore.getState().loaded).toBe(false);

    list.mockResolvedValueOnce({ credentials: [] } as Awaited<ReturnType<typeof API.listAllCredentials>>);
    await useConnectionsStore.getState().fetch();
    expect(useConnectionsStore.getState().loaded).toBe(true);
    expect(list).toHaveBeenCalledTimes(2);
  });
});
