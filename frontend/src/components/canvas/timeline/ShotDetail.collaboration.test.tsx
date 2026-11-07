import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vite-plus/test";

import type { NarrationSegment } from "@/types";
import { makeNarrationSegment } from "@/test/factories";

import { ShotDetail } from "./ShotDetail";

type UpdatePrompt = NonNullable<Parameters<typeof ShotDetail>[0]["onUpdatePrompt"]>;

function detailElement(segment: NarrationSegment, onUpdatePrompt: UpdatePrompt) {
  return (
    <ShotDetail
      segment={segment}
      segmentId={segment.segment_id}
      contentMode="narration"
      aspectRatio="9:16"
      projectName="demo"
      scriptFile="episode_1.json"
      selectedIndex={0}
      totalCount={1}
      onPrev={() => {}}
      onNext={() => {}}
      durationOptions={[8]}
      onUpdatePrompt={onUpdatePrompt}
    />
  );
}

const narrationText = () => screen.getByRole("textbox", { name: "旁白正文" });
const EXTERNAL_UPDATE = "此内容已被其他成员或 Agent 更新";

describe("ShotDetail 多人同时编辑", () => {
  it("保存时带上编辑起点：这次要写的字段在开始编辑时的值", () => {
    const onUpdatePrompt = vi.fn<UpdatePrompt>().mockResolvedValue(true);
    render(detailElement(makeNarrationSegment({ novel_text: "雨下了一夜。" }), onUpdatePrompt));

    fireEvent.change(narrationText(), { target: { value: "雨停了。" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(onUpdatePrompt).toHaveBeenCalledWith("E1S01", { novel_text: "雨停了。" }, { novel_text: "雨下了一夜。" });
  });

  it("别人改了我没动的字段：直接采用对方的内容，保存时不把它改回去", () => {
    const onUpdatePrompt = vi.fn<UpdatePrompt>().mockResolvedValue(true);
    const segment = makeNarrationSegment({ novel_text: "雨下了一夜。", image_prompt: "雨夜街道" });
    const { rerender } = render(detailElement(segment, onUpdatePrompt));

    fireEvent.change(narrationText(), { target: { value: "雨停了。" } });
    rerender(detailElement({ ...segment, image_prompt: "别人改的街景" }, onUpdatePrompt));

    expect(screen.getByDisplayValue("别人改的街景")).toBeInTheDocument();
    expect(narrationText()).toHaveValue("雨停了。");
    expect(screen.queryByText(EXTERNAL_UPDATE)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(onUpdatePrompt).toHaveBeenCalledWith("E1S01", { novel_text: "雨停了。" }, { novel_text: "雨下了一夜。" });
  });

  it("别人改了我也在改的字段：保留我的修改并标出外部更新", () => {
    const onUpdatePrompt = vi.fn<UpdatePrompt>().mockResolvedValue(true);
    const segment = makeNarrationSegment({ novel_text: "雨下了一夜。" });
    const { rerender } = render(detailElement(segment, onUpdatePrompt));

    fireEvent.change(narrationText(), { target: { value: "雨停了。" } });
    rerender(detailElement({ ...segment, novel_text: "别人写的旁白。" }, onUpdatePrompt));

    expect(narrationText()).toHaveValue("雨停了。");
    expect(screen.getByText(EXTERNAL_UPDATE)).toBeInTheDocument();
  });
});
