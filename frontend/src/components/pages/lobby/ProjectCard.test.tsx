import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vite-plus/test";
import type { ProjectSummary } from "@/types";
import { ProjectCard } from "./ProjectCard";

function project(thumbnail: string | null): ProjectSummary {
  return {
    name: "demo",
    title: "演示项目",
    style: "Anime",
    thumbnail,
    last_activity_at: null,
    status: {},
  };
}

function posterSrc(thumbnail: string): string | null {
  const { container } = render(<ProjectCard project={project(thumbnail)} readOnly />);
  return container.querySelector("img")?.getAttribute("src") ?? null;
}

describe("ProjectCard poster", () => {
  it("requests a 640px thumbnail for covers served from the project files route", () => {
    expect(posterSrc("/api/v1/files/demo/storyboards/E1S01.png?v=123")).toBe(
      "/api/v1/files/demo/storyboards/E1S01.png?v=123&w=640",
    );
    expect(posterSrc("/api/v1/files/demo/storyboards/E1S01.png")).toBe(
      "/api/v1/files/demo/storyboards/E1S01.png?w=640",
    );
  });

  it("leaves covers from other sources untouched", () => {
    const inline = "data:image/svg+xml;utf8,<svg/>";
    expect(posterSrc(inline)).toBe(inline);
  });
});

function blockedProject(repairCode: "project_migration_failed" | "project_schema_unsupported"): ProjectSummary {
  return {
    ...project(null),
    status: {
      needs_repair: true,
      repair_reason: "原因",
      repair_code: repairCode,
      assets: {},
      episodes_summary: { total: 0, scripted: 0, in_production: 0, completed: 0 },
      source_remaining: false,
    },
  };
}

describe("ProjectCard blocked badge", () => {
  it("says the version is too old for a project blocked by its schema version", () => {
    render(<ProjectCard project={blockedProject("project_schema_unsupported")} readOnly />);
    expect(screen.getByText("版本过旧")).toBeInTheDocument();
    expect(screen.queryByText("待修复")).not.toBeInTheDocument();
  });

  it("keeps the repair badge for a project whose migration failed", () => {
    render(<ProjectCard project={blockedProject("project_migration_failed")} readOnly />);
    expect(screen.getByText("待修复")).toBeInTheDocument();
    expect(screen.queryByText("版本过旧")).not.toBeInTheDocument();
  });
});
