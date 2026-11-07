import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router, useLocation } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import { API, type ProjectEventStreamOptions } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import { usePresenceStore } from "@/stores/presence-store";
import { useProjectsStore } from "@/stores/projects-store";
import { FakeSseStream } from "@/test/fakeSseStream";
import type { ProjectChange, ProjectChangeActor, ProjectChangeBatchPayload } from "@/types";

import { useProjectEventsSSE } from "./useProjectEventsSSE";

function HookHarness() {
  useProjectEventsSSE("demo");
  const [location] = useLocation();
  return <div data-testid="location">{location}</div>;
}

function mount(path: string) {
  let options: ProjectEventStreamOptions | undefined;
  FakeSseStream.reset();
  vi.spyOn(API, "openProjectEventStream").mockImplementation((next) => {
    options = next;
    return new FakeSseStream();
  });
  const { hook } = memoryLocation({ path });
  render(
    <Router hook={hook}>
      <HookHarness />
    </Router>,
  );
  return {
    emit(payload: Partial<ProjectChangeBatchPayload> & { changes: ProjectChange[] }) {
      act(() => {
        options?.onChanges?.({
          project_name: "demo",
          batch_id: "batch-1",
          fingerprint: "fp-1",
          generated_at: "2026-11-07T00:00:00Z",
          source: "webui",
          ...payload,
        });
      });
    },
    get options() {
      return options;
    },
  };
}

const PROP_UPDATED: ProjectChange = {
  entity_type: "prop",
  action: "updated",
  entity_id: "玉佩",
  label: "道具「玉佩」",
  focus: { pane: "props", anchor_type: "prop", anchor_id: "玉佩" },
  important: true,
};

const DRAFT_CREATED: ProjectChange = {
  entity_type: "draft",
  action: "created",
  entity_id: "episode_1_script_plan",
  label: "第 1 集的剧本",
  episode: 1,
  focus: { pane: "episode", episode: 1 },
  important: true,
};

const BOB: ProjectChangeActor = { user_id: "u-bob", username: "bob" };

describe("useProjectEventsSSE：其他成员的修改", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState(useAppStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    usePresenceStore.getState().clear();
    useAuthStore.setState({ userId: "u-alice", username: "alice" });
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: {
        title: "Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [{ episode: 1, title: "第一集", script_file: "scripts/episode_1.json" }],
        characters: {},
        scenes: {},
        props: { 玉佩: { description: "" } },
      },
      scripts: {},
    });
  });

  it("其他成员的修改提示是谁改的，但不自动跳转、不排队聚焦", async () => {
    const stream = mount("/characters");

    stream.emit({ actor: BOB, changes: [PROP_UPDATED] });

    await waitFor(() => {
      expect(useAppStore.getState().toast?.text).toBe("bob：道具「玉佩」已更新");
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/characters");
    expect(useAppStore.getState().scrollTarget).toBeNull();
    // 通知记录里留下是谁改的；「AI 刚更新了……」那类可点击跳转的工作区通知只给 Agent 的修改
    expect(useAppStore.getState().workspaceNotifications.map((n) => n.text)).toEqual(["bob：道具「玉佩」已更新"]);
  });

  it("其他成员新建的草稿不把我带到那一集", async () => {
    const stream = mount("/characters");

    stream.emit({ actor: BOB, changes: [DRAFT_CREATED] });

    await waitFor(() => {
      expect(useAppStore.getState().toast).not.toBeNull();
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/characters");
  });

  it("自己的修改不提示：按账号 id 认出是自己", async () => {
    const stream = mount("/props");

    stream.emit({ actor: { user_id: "u-alice", username: "Alice" }, changes: [PROP_UPDATED] });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalled();
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(useAppStore.getState().toast).toBeNull();
  });

  it("没有成员归属的 Web 端修改照旧不提示", async () => {
    const stream = mount("/props");

    stream.emit({ actor: null, changes: [PROP_UPDATED] });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalled();
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(useAppStore.getState().toast).toBeNull();
  });

  it("在线名单事件写入名单 store", () => {
    const stream = mount("/");
    const members = [{ user_id: "u-bob", username: "bob", views: ["episodes/1"] }];

    act(() => {
      stream.options?.onPresence?.({ project_name: "demo", members });
    });

    expect(usePresenceStore.getState()).toMatchObject({ projectName: "demo", members });
  });
});
