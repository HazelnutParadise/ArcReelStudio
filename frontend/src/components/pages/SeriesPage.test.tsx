import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { makeSeries, makeSeriesAsset } from "@/test/series";
import type { ProjectSummary } from "@/types";
import type { AssetListPage } from "@/types/asset";
import { SeriesPage } from "./SeriesPage";

function project(name: string, title = name): ProjectSummary {
  return { name, title, style: "Anime", thumbnail: null, status: {}, last_activity_at: null };
}

function renderPage() {
  const location = memoryLocation({ path: "/app/series", record: true });
  return render(
    <Router hook={location.hook}>
      <SeriesPage />
    </Router>,
  );
}

const STARS = makeSeries({ id: 1, name: "星海纪事", project_names: ["p1"], asset_ids: ["a1"] });
const LOCAL = makeSeries({ id: 2, name: "山海经", project_names: ["p2"] });

function mockBackend(series = [STARS, LOCAL]) {
  vi.spyOn(API, "listSeries").mockResolvedValue({ series });
  vi.spyOn(API, "listProjects").mockResolvedValue({
    projects: [project("p1", "第一部"), project("p2", "第二部"), project("p3", "第三部")],
  });
  vi.spyOn(API, "getAsset").mockResolvedValue({ asset: makeSeriesAsset({ id: "a1", name: "王小明" }) });
}

async function openPage() {
  renderPage();
  await screen.findByRole("list", { name: "全部系列" });
  // 详情里的项目名取自项目列表；等它出现，说明两路请求都已落地
  await screen.findByText("第一部");
}

function toastText() {
  return useAppStore.getState().toast?.text;
}

describe("SeriesPage", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("lists the series with their counts and shows the first one", async () => {
    mockBackend();
    await openPage();

    const list = screen.getByRole("list", { name: "全部系列" });
    expect(within(list).getByText("1 个项目 · 1 个资产")).toBeInTheDocument();
    expect(within(list).getByText("1 个项目 · 0 个资产")).toBeInTheDocument();
    expect(screen.getByLabelText("名称")).toHaveValue("星海纪事");
  });

  it("creates a series and selects it", async () => {
    mockBackend();
    const create = vi.spyOn(API, "createSeries").mockResolvedValue(makeSeries({ id: 3, name: "新系列" }));
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "新建系列" }));
    const dialog = await screen.findByRole("dialog", { name: "新建系列" });
    await user.type(within(dialog).getByLabelText("名称"), "新系列");
    await user.type(within(dialog).getByLabelText("简介（可选）"), "一句话");
    await user.click(within(dialog).getByRole("button", { name: "创建" }));

    expect(create).toHaveBeenCalledWith("新系列", "一句话");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /新系列/ })).toHaveAttribute("aria-current", "true");
    expect(toastText()).toBe("已创建系列「新系列」");
  });

  it("shows the server's message when the name is already taken", async () => {
    mockBackend();
    vi.spyOn(API, "createSeries").mockRejectedValue(new Error("系列名称已存在"));
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "新建系列" }));
    const dialog = await screen.findByRole("dialog", { name: "新建系列" });
    await user.type(within(dialog).getByLabelText("名称"), "星海纪事");
    await user.click(within(dialog).getByRole("button", { name: "创建" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("系列名称已存在");
    expect(screen.getByRole("dialog", { name: "新建系列" })).toBeInTheDocument();
  });

  it("saves only the fields that changed", async () => {
    mockBackend();
    const update = vi
      .spyOn(API, "updateSeries")
      .mockResolvedValue({ ...STARS, world_setting: "漂浮的群岛", updated_at: "2026-11-01T00:00:00Z" });
    await openPage();
    const user = userEvent.setup();
    const save = screen.getByRole("button", { name: "保存" });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText("世界观"), "漂浮的群岛");
    await user.click(save);

    expect(update).toHaveBeenCalledWith(1, { world_setting: "漂浮的群岛" });
    await waitFor(() => expect(toastText()).toBe("系列设定已保存"));
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  });

  it("reports a failed save and keeps the draft", async () => {
    mockBackend();
    vi.spyOn(API, "updateSeries").mockRejectedValue(new Error("名称重复"));
    await openPage();
    const user = userEvent.setup();

    await user.clear(screen.getByLabelText("名称"));
    await user.type(screen.getByLabelText("名称"), "山海经");
    await user.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(toastText()).toBe("系列保存失败：名称重复"));
    expect(screen.getByLabelText("名称")).toHaveValue("山海经");
  });

  it("caps the world and plot settings at 6000 characters", async () => {
    mockBackend();
    await openPage();

    expect(screen.getByLabelText("世界观")).toHaveAttribute("maxlength", "6000");
    expect(screen.getByLabelText("剧情设定")).toHaveAttribute("maxlength", "6000");
    expect(screen.getByText(/Agent 会读取这里的世界观与剧情设定/)).toBeInTheDocument();
  });

  it("adds a project from another series and says that it moves", async () => {
    mockBackend();
    const add = vi.spyOn(API, "addSeriesProject").mockResolvedValue({ ...STARS, project_names: ["p1", "p2"] });
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("combobox", { name: "加入项目" }));
    await user.click(await screen.findByRole("option", { name: "第二部（将从「山海经」移来）" }));
    await user.click(screen.getByRole("button", { name: "加入" }));

    expect(add).toHaveBeenCalledWith(1, "p2");
    await waitFor(() => expect(toastText()).toBe("已把 第二部 加入系列"));
    expect(screen.getByRole("button", { name: "把 第二部 移出系列" })).toBeInTheDocument();
    // 项目已离开山海经，列表里它的计数同步变成 0
    expect(within(screen.getByRole("list", { name: "全部系列" })).getAllByText("0 个项目 · 0 个资产")).toHaveLength(1);
  });

  it("removes a project and offers undo", async () => {
    mockBackend();
    const remove = vi.spyOn(API, "removeSeriesProject").mockResolvedValue({ ...STARS, project_names: [] });
    const add = vi.spyOn(API, "addSeriesProject").mockResolvedValue(STARS);
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "把 第一部 移出系列" }));

    expect(remove).toHaveBeenCalledWith(1, "p1");
    await waitFor(() => expect(screen.getByText("这个系列还没有项目。")).toBeInTheDocument());
    useAppStore.getState().toast?.action?.onClick();
    await waitFor(() => expect(add).toHaveBeenCalledWith(1, "p1"));
    expect(await screen.findByText("第一部")).toBeInTheDocument();
  });

  it("adds assets through the library picker, choosing the type first", async () => {
    mockBackend();
    const page: AssetListPage = {
      items: [makeSeriesAsset({ id: "s1", type: "scene", name: "古庙" })],
      total: 1,
      counts: { character: 0, scene: 1, prop: 0 },
    };
    const list = vi.spyOn(API, "listAssets").mockResolvedValue(page);
    const add = vi.spyOn(API, "addSeriesAsset").mockResolvedValue({ ...STARS, asset_ids: ["a1", "s1"] });
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "从资产库添加" }));
    await user.click(await screen.findByRole("menuitem", { name: "场景" }));
    const picker = await screen.findByRole("dialog", { name: "从资产库选择场景" });
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ type: "scene" }), expect.anything());
    await user.click(await within(picker).findByRole("button", { name: /古庙/ }));
    await user.click(within(picker).getByRole("button", { name: "导入 1 个" }));

    expect(add).toHaveBeenCalledWith(1, "s1");
    await waitFor(() => expect(toastText()).toBe("已向系列添加 1 个资产"));
  });

  it("removes an asset from the series without touching the library", async () => {
    mockBackend();
    const remove = vi.spyOn(API, "removeSeriesAsset").mockResolvedValue({ ...STARS, asset_ids: [] });
    await openPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "把 王小明 移出系列" }));

    expect(remove).toHaveBeenCalledWith(1, "a1");
    await waitFor(() => expect(screen.getByText("这个系列还没有资产库资产。")).toBeInTheDocument());
  });

  it("applies the series assets to a project with the skip policy and summarises the result", async () => {
    mockBackend();
    const apply = vi.spyOn(API, "applyAssetsToProject").mockResolvedValue({
      succeeded: [{ id: "a1", name: "王小明" }],
      skipped: [{ id: "a2", name: "李小红" }],
      failed: [],
    });
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "把系列资产套用到 第一部" }));

    expect(apply).toHaveBeenCalledWith({ asset_ids: ["a1"], target_project: "p1", conflict_policy: "skip" });
    await waitFor(() => expect(toastText()).toBe("已套用到 第一部：复制 1 个，1 个因同名已存在而跳过。"));
  });

  it("disables applying when the series has no assets", async () => {
    mockBackend([makeSeries({ id: 2, name: "山海经", project_names: ["p2"] })]);
    renderPage();
    await screen.findByText("第二部");

    expect(screen.getByRole("button", { name: "把系列资产套用到 第二部" })).toBeDisabled();
    expect(screen.getByText("先添加共用资产，才能套用到项目。")).toBeInTheDocument();
  });

  it("deletes a series only after confirmation", async () => {
    mockBackend();
    const del = vi.spyOn(API, "deleteSeries").mockResolvedValue();
    await openPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "删除系列" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/项目和资产库里的资产都不会被删除/)).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "删除系列" }));

    expect(del).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.queryByRole("button", { name: /星海纪事/ })).not.toBeInTheDocument());
    expect(screen.getByLabelText("名称")).toHaveValue("山海经");
  });

  it("explains a failed load and retries", async () => {
    const list = vi.spyOn(API, "listSeries").mockRejectedValueOnce(new Error("network down"));
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("系列加载失败：network down");

    list.mockResolvedValue({ series: [] });
    await userEvent.setup().click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("还没有系列")).toBeInTheDocument();
  });
});
