import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import type { RemoteEdit } from "@/collab/collab-client";
import { useAppStore } from "@/stores/app-store";

import { useImpactfulSettingNotice } from "./useImpactfulSettingNotice";

const edit = (at: number): RemoteEdit => ({ userId: "u-bob", name: "bob", color: "#2563eb", at });

describe("useImpactfulSettingNotice", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState(useAppStore.getInitialState(), true);
  });

  it("tells me who changed the aspect ratio", () => {
    const { rerender } = renderHook(({ edits }) => useImpactfulSettingNotice(edits, false), {
      initialProps: { edits: {} as Record<string, RemoteEdit> },
    });
    rerender({ edits: { aspect_ratio: edit(1) } });
    expect(useAppStore.getState().toast?.text).toBe("bob 改了画面比例，你这里已经同步");
  });

  it("names every impactful field one change touched", () => {
    const pushToast = vi.spyOn(useAppStore.getState(), "pushToast");
    const { rerender } = renderHook(({ edits }) => useImpactfulSettingNotice(edits, false), {
      initialProps: { edits: {} as Record<string, RemoteEdit> },
    });
    const both = edit(1);
    rerender({ edits: { aspect_ratio: both, episode_target_duration: both } });

    expect(pushToast.mock.calls.map(([text]) => text)).toEqual([
      "bob 改了画面比例，你这里已经同步",
      "bob 改了单集目标时长，你这里已经同步",
    ]);
  });

  it("stays quiet about changes made before I opened the page and about other fields", () => {
    const before = edit(1);
    const { rerender } = renderHook(({ edits }) => useImpactfulSettingNotice(edits, false), {
      initialProps: { edits: { aspect_ratio: before } as Record<string, RemoteEdit> },
    });
    rerender({ edits: { aspect_ratio: before, synopsis: edit(2) } });
    expect(useAppStore.getState().toast).toBeNull();
  });
});
