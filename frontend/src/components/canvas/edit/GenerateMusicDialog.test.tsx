import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

import { GenerateMusicButton } from "./GenerateMusicDialog";

beforeEach(() => {
  useAppStore.setState({ toast: null });
});

describe("GenerateMusicButton", () => {
  it("submits the prompt, length and options, then closes", async () => {
    const generate = vi
      .spyOn(API, "generateMusic")
      .mockResolvedValue({ success: true, task_id: "t-1", message: "音乐生成任务已提交" });
    render(<GenerateMusicButton projectName="demo" />);

    await userEvent.click(screen.getByRole("button", { name: "生成音乐" }));
    await userEvent.type(screen.getByLabelText("想要什么样的音乐"), "雨夜 lo-fi");
    await userEvent.clear(screen.getByLabelText("长度（秒）"));
    await userEvent.type(screen.getByLabelText("长度（秒）"), "90");
    await userEvent.type(screen.getByLabelText("名称（可不填）"), "雨夜");
    await userEvent.click(screen.getByRole("checkbox", { name: "只要器乐，不要人声" }));
    await userEvent.click(screen.getByRole("button", { name: "开始生成" }));

    await waitFor(() =>
      expect(generate).toHaveBeenCalledWith("demo", {
        prompt: "雨夜 lo-fi",
        duration_seconds: 90,
        instrumental: false,
        name: "雨夜",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("needs a prompt and a length in range before it can submit", async () => {
    render(<GenerateMusicButton projectName="demo" />);
    await userEvent.click(screen.getByRole("button", { name: "生成音乐" }));

    const submit = screen.getByRole("button", { name: "开始生成" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("想要什么样的音乐"), "drums");
    expect(submit).toBeEnabled();
    await userEvent.clear(screen.getByLabelText("长度（秒）"));
    await userEvent.type(screen.getByLabelText("长度（秒）"), "9999");
    expect(submit).toBeDisabled();
  });

  it("keeps the dialog open and reports a failure", async () => {
    vi.spyOn(API, "generateMusic").mockRejectedValue(new Error("还没有设定音乐模型"));
    render(<GenerateMusicButton projectName="demo" />);
    await userEvent.click(screen.getByRole("button", { name: "生成音乐" }));
    await userEvent.type(screen.getByLabelText("想要什么样的音乐"), "drums");
    await userEvent.click(screen.getByRole("button", { name: "开始生成" }));

    await waitFor(() => expect(useAppStore.getState().toast?.text).toContain("还没有设定音乐模型"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
