import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { useProjectsStore } from "@/stores/projects-store";
import { makeSeries } from "@/test/series";
import type { ProjectSummary } from "@/types";
import { ProjectsPage } from "./ProjectsPage";

vi.mock("@/components/pages/CreateProjectModal", () => ({
  CreateProjectModal: () => <div data-testid="create-project-modal" />,
}));

function project(name: string, title: string): ProjectSummary {
  return { name, title, style: "Anime", thumbnail: null, status: {}, last_activity_at: null };
}

const PROJECTS = [project("p1", "第一部"), project("p2", "第二部"), project("p3", "第三部")];

function renderLobby() {
  const location = memoryLocation({ path: "/app/projects", record: true });
  return render(
    <Router hook={location.hook}>
      <ProjectsPage />
    </Router>,
  );
}

async function cardTitles() {
  const list = await screen.findByRole("list", { name: "项目" });
  return within(list)
    .getAllByRole("heading", { level: 3 })
    .map((heading) => heading.textContent);
}

describe("ProjectsPage series", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    useConfigStatusStore.setState(useConfigStatusStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: PROJECTS });
  });

  it("marks cards of series projects with the series name", async () => {
    vi.spyOn(API, "listSeries").mockResolvedValue({
      series: [makeSeries({ id: 1, name: "星海纪事", project_names: ["p1"] })],
    });
    renderLobby();

    const list = await screen.findByRole("list", { name: "项目" });
    expect(await within(list).findByText("星海纪事")).toBeInTheDocument();
    expect(within(list).getAllByText("星海纪事")).toHaveLength(1);
  });

  // 四次打开下拉再选择，在负载高的机器上超过默认的 5 秒
  it("filters by series, and by projects that are in no series", { timeout: 20_000 }, async () => {
    vi.spyOn(API, "listSeries").mockResolvedValue({
      series: [
        makeSeries({ id: 1, name: "星海纪事", project_names: ["p1"] }),
        makeSeries({ id: 2, name: "山海经", project_names: ["p2"] }),
      ],
    });
    renderLobby();
    const user = userEvent.setup();
    expect(await cardTitles()).toHaveLength(3);

    await user.click(await screen.findByRole("combobox", { name: "按系列筛选" }));
    await user.click(await screen.findByRole("option", { name: "山海经" }));
    expect(await cardTitles()).toEqual(["第二部"]);

    await user.click(screen.getByRole("combobox", { name: "按系列筛选" }));
    await user.click(await screen.findByRole("option", { name: "不属于任何系列" }));
    expect(await cardTitles()).toEqual(["第三部"]);

    await user.click(screen.getByRole("combobox", { name: "按系列筛选" }));
    await user.click(await screen.findByRole("option", { name: "全部系列" }));
    expect(await cardTitles()).toHaveLength(3);
  });

  it("works as before, without badge or filter, when the series list fails to load", async () => {
    const listSeries = vi.spyOn(API, "listSeries").mockRejectedValue(new Error("boom"));
    renderLobby();

    expect(await cardTitles()).toEqual(["第一部", "第二部", "第三部"]);
    expect(listSeries).toHaveBeenCalled();
    expect(screen.queryByRole("combobox", { name: "按系列筛选" })).not.toBeInTheDocument();
    expect(useAppStore.getState().toast).toBeNull();
  });
});
