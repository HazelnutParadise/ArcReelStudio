import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import { API } from "@/api";
import { usePresenceStore } from "@/stores/presence-store";

import { PRESENCE_HEARTBEAT_MS, useProjectPresence, workspaceView } from "./useProjectPresence";

function Harness({ projectName }: { projectName: string | null }) {
  useProjectPresence(projectName);
  return null;
}

const MEMBERS = [{ user_id: "u-alice", username: "alice", views: ["episodes/2"] }];

describe("workspaceView", () => {
  it.each([
    ["/episodes/2", "episodes/2"],
    ["/episodes/2/", "episodes/2"],
    ["/episodes/2?view=edit", "episodes/2"],
    ["/", null],
    ["", null],
    ["/app/projects/demo/characters", "characters"],
    ["/app/projects/demo", null],
  ])("%s → %s", (location, expected) => {
    expect(workspaceView(location, "demo")).toBe(expected);
  });
});

describe("useProjectPresence", () => {
  let report: ReturnType<typeof vi.spyOn>;
  let leave: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.restoreAllMocks();
    usePresenceStore.getState().clear();
    report = vi.spyOn(API, "reportPresence").mockResolvedValue({ members: MEMBERS });
    leave = vi.spyOn(API, "leavePresence").mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("打开项目即报到所在位置，并把名单写进 store", async () => {
    const { hook } = memoryLocation({ path: "/episodes/2" });
    render(
      <Router hook={hook}>
        <Harness projectName="demo" />
      </Router>,
    );

    expect(report).toHaveBeenCalledWith("demo", expect.any(String), "episodes/2");
    await waitFor(() => {
      expect(usePresenceStore.getState().members).toEqual(MEMBERS);
    });
  });

  it("切换页面立即再报，之后按间隔定时报到", () => {
    vi.useFakeTimers();
    const location = memoryLocation({ path: "/episodes/2" });
    render(
      <Router hook={location.hook}>
        <Harness projectName="demo" />
      </Router>,
    );
    report.mockClear();

    act(() => {
      location.navigate("/characters");
    });
    expect(report).toHaveBeenLastCalledWith("demo", expect.any(String), "characters");

    report.mockClear();
    act(() => {
      vi.advanceTimersByTime(PRESENCE_HEARTBEAT_MS);
    });
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenLastCalledWith("demo", expect.any(String), "characters");
  });

  it("离开项目时退出在线名单并清空 store", async () => {
    const { hook } = memoryLocation({ path: "/" });
    const view = render(
      <Router hook={hook}>
        <Harness projectName="demo" />
      </Router>,
    );
    await waitFor(() => {
      expect(usePresenceStore.getState().members).toEqual(MEMBERS);
    });
    const tabId = report.mock.calls[0][1];

    view.unmount();

    expect(leave).toHaveBeenCalledWith("demo", tabId);
    expect(usePresenceStore.getState().members).toEqual([]);
  });

  it("没有项目（如演示项目）时不报到", () => {
    const { hook } = memoryLocation({ path: "/" });
    render(
      <Router hook={hook}>
        <Harness projectName={null} />
      </Router>,
    );

    expect(report).not.toHaveBeenCalled();
  });
});
