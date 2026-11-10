import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

import { GenerateSfxButton } from "./GenerateSfxDialog";

beforeEach(() => {
  useAppStore.setState({ toast: null });
});

describe("GenerateSfxButton", () => {
  it("submits the prompt, length and name, then closes", async () => {
    const generate = vi
      .spyOn(API, "generateSfx")
      .mockResolvedValue({ success: true, task_id: "t-1", message: "音效生成任务已提交" });
    render(<GenerateSfxButton projectName="demo" />);

    await userEvent.click(screen.getByRole("button", { name: "生成音效" }));
    await userEvent.type(screen.getByLabelText("想要什么样的声音"), "玻璃碎裂");
    await userEvent.clear(screen.getByLabelText("长度（秒）"));
    await userEvent.type(screen.getByLabelText("长度（秒）"), "2");
    await userEvent.type(screen.getByLabelText("名称（可不填）"), "碎玻璃");
    await userEvent.click(screen.getByRole("button", { name: "开始生成" }));

    await waitFor(() =>
      expect(generate).toHaveBeenCalledWith("demo", { prompt: "玻璃碎裂", duration_seconds: 2, name: "碎玻璃" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("refuses a length over 30 seconds", async () => {
    render(<GenerateSfxButton projectName="demo" />);
    await userEvent.click(screen.getByRole("button", { name: "生成音效" }));
    await userEvent.type(screen.getByLabelText("想要什么样的声音"), "door");

    const submit = screen.getByRole("button", { name: "开始生成" });
    expect(submit).toBeEnabled();
    await userEvent.clear(screen.getByLabelText("长度（秒）"));
    await userEvent.type(screen.getByLabelText("长度（秒）"), "31");
    expect(submit).toBeDisabled();
  });

  it("keeps the dialog open and reports a failure", async () => {
    vi.spyOn(API, "generateSfx").mockRejectedValue(new Error("还没有设定音效模型"));
    render(<GenerateSfxButton projectName="demo" />);
    await userEvent.click(screen.getByRole("button", { name: "生成音效" }));
    await userEvent.type(screen.getByLabelText("想要什么样的声音"), "door");
    await userEvent.click(screen.getByRole("button", { name: "开始生成" }));

    await waitFor(() => expect(useAppStore.getState().toast?.text).toContain("还没有设定音效模型"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
