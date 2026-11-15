import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vite-plus/test";

import { useProjectsStore } from "@/stores/projects-store";
import type { ProjectData } from "@/types";

import { ReferenceUnitAddDialog } from "./ReferenceUnitAddDialog";

function renderDialog(contentMode: string) {
  useProjectsStore.setState({ currentProjectData: { content_mode: contentMode } as unknown as ProjectData });
  render(
    <ReferenceUnitAddDialog
      open
      prompt=""
      submitting={false}
      onPromptChange={() => {}}
      onSubmit={() => {}}
      onClose={() => {}}
    />,
  );
  return screen.getByRole("textbox").getAttribute("placeholder") ?? "";
}

describe("ReferenceUnitAddDialog", () => {
  beforeEach(() => useProjectsStore.setState(useProjectsStore.getInitialState(), true));

  it("only mentions merchandise in ad projects and explains the line marks in plain words", () => {
    const drama = renderDialog("drama");
    expect(drama).not.toContain("商品");
    expect(drama).not.toMatch(/[{}]/);
    expect(drama).toContain("台词");
  });

  it("lists merchandise in ad projects", () => {
    expect(renderDialog("ad")).toContain("商品");
  });
});
