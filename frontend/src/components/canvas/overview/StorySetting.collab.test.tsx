import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { CollabClient, setCollabEnabled } from "@/collab/collab-client";
import { FakeCollabServer } from "@/collab/collab-test-server";
import { unitJson } from "@/collab/ydoc-json";
import { setToken } from "@/utils/auth";

import { StorySetting } from "./StorySetting";

const ROOM = { project: "demo", kind: "overview", key: "" };

function renderSetting() {
  return render(
    <StorySetting
      projectName="demo"
      overview={{ synopsis: "雨夜", genre: "", theme: "", world_setting: "" }}
      readOnly={false}
      canGenerate={false}
      generating={false}
      generateError={null}
      onGenerate={() => {}}
    />,
  );
}

describe("StorySetting in live collaboration", () => {
  let server: FakeCollabServer;
  let restore: () => void;

  beforeEach(() => {
    setToken("token");
    server = new FakeCollabServer({ "demo/overview/": { synopsis: "雨夜", genre: "", theme: "", world_setting: "" } });
    restore = server.install();
    setCollabEnabled(true, new CollabClient("ws://test/collab"));
  });

  afterEach(() => {
    setCollabEnabled(false);
    restore();
  });

  it("syncs typing to the room and shows other people's changes without a save button", async () => {
    const update = vi.spyOn(API, "updateOverview");
    renderSetting();
    await screen.findByText("实时同步中");
    const synopsis = screen.getByLabelText("梗概");

    fireEvent.change(synopsis, { target: { value: "雨夜的街口" } });
    await waitFor(() => expect(unitJson(server.docFor(ROOM)).synopsis).toBe("雨夜的街口"));

    act(() => server.externalChange(ROOM, { synopsis: "深夜，雨夜的街口", genre: "悬疑", theme: "", world_setting: "" }));
    await waitFor(() => expect(synopsis).toHaveValue("深夜，雨夜的街口"));
    expect(screen.getByLabelText("类型")).toHaveValue("悬疑");

    // 协作中由服务端合并写回，不走保存接口，也没有保存与放弃按钮
    expect(update).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
  });

  it("falls back to save-on-demand when the collaboration server refuses", async () => {
    server.acceptToken = null;
    renderSetting();
    const synopsis = screen.getByLabelText("梗概");

    fireEvent.change(synopsis, { target: { value: "离线也能改" } });

    expect(await screen.findByRole("button", { name: "保存" })).toBeInTheDocument();
  });
});
