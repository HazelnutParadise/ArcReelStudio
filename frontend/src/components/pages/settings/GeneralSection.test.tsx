import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API } from "@/api";
import i18n from "@/i18n";
import { useAppStore } from "@/stores/app-store";
import { useOnboardingStore } from "@/stores/onboarding-store";

import { GeneralSection } from "./GeneralSection";

type SystemConfig = Awaited<ReturnType<typeof API.getSystemConfig>>;

function systemConfig(gpuEncodingEnabled: boolean, gpuEncoder: string | null): SystemConfig {
  return {
    settings: { gpu_encoding_enabled: gpuEncodingEnabled },
    options: { video_backends: [], image_backends: [], text_backends: [], gpu_encoder: gpuEncoder },
  } as unknown as SystemConfig;
}

describe("GeneralSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useOnboardingStore.setState(useOnboardingStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(systemConfig(true, null));
  });

  afterEach(async () => {
    await i18n.changeLanguage("zh");
  });

  it("选中界面语言后立即切换整页文案", async () => {
    const user = userEvent.setup();
    render(<GeneralSection />);

    const language = screen.getByRole("combobox", { name: "界面语言" });
    expect(language).toHaveTextContent("中文");

    await user.click(language);
    await user.click(await screen.findByRole("option", { name: "English" }));

    expect(await screen.findByRole("combobox", { name: "Interface language" })).toHaveTextContent("English");
    expect(i18n.language).toBe("en");
  });

  it("选繁体中文后整页改用繁体", async () => {
    const user = userEvent.setup();
    render(<GeneralSection />);

    await user.click(screen.getByRole("combobox", { name: "界面语言" }));
    await user.click(await screen.findByRole("option", { name: "繁體中文" }));

    expect(await screen.findByRole("combobox", { name: "介面語言" })).toHaveTextContent("繁體中文");
    expect(i18n.language).toBe("zh-TW");
  });

  it("选浅色后立即切换，重新打开设置仍是浅色", async () => {
    document.documentElement.classList.add("dark");
    const user = userEvent.setup();
    const { unmount } = render(<GeneralSection />);

    const theme = screen.getByRole("combobox", { name: "主题" });
    expect(theme).toHaveTextContent("跟随系统");

    await user.click(theme);
    await user.click(await screen.findByRole("option", { name: "浅色" }));

    expect(document.documentElement).not.toHaveClass("dark");
    unmount();
    render(<GeneralSection />);
    expect(screen.getByRole("combobox", { name: "主题" })).toHaveTextContent("浅色");
  });

  it("重看引导会重新开始新手引导", async () => {
    const user = userEvent.setup();
    render(<GeneralSection />);

    await user.click(screen.getByRole("button", { name: "重看引导" }));

    expect(useOnboardingStore.getState().active).toBe(true);
  });

  it("检测到 GPU 时可以关闭 GPU 编码，切换后立即保存", async () => {
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(systemConfig(true, "h264_nvenc"));
    const update = vi.spyOn(API, "updateSystemConfig").mockResolvedValue(systemConfig(false, "h264_nvenc"));
    const user = userEvent.setup();
    render(<GeneralSection />);

    const toggle = await screen.findByRole("switch", { name: "GPU 编码" });
    expect(toggle).toBeChecked();
    expect(screen.getByText(/已检测到 NVIDIA GPU/)).toBeInTheDocument();

    await user.click(toggle);

    expect(update).toHaveBeenCalledWith({ gpu_encoding_enabled: false });
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it("没有可用的 GPU 时开关不可操作，并说明成片使用 CPU 编码", async () => {
    render(<GeneralSection />);

    const toggle = await screen.findByRole("switch", { name: "GPU 编码" });
    expect(toggle).toHaveAttribute("aria-disabled", "true");
    expect(toggle).not.toBeChecked();
    expect(screen.getByText("未检测到可用的 NVIDIA GPU，成片使用 CPU 编码。")).toBeInTheDocument();
  });

  it("保存失败时开关回到原值并提示", async () => {
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(systemConfig(true, "h264_nvenc"));
    vi.spyOn(API, "updateSystemConfig").mockRejectedValue(new Error("网络错误"));
    const user = userEvent.setup();
    render(<GeneralSection />);

    const toggle = await screen.findByRole("switch", { name: "GPU 编码" });
    await user.click(toggle);

    await waitFor(() => expect(toggle).toBeChecked());
    expect(useAppStore.getState().toast?.text).toContain("无法保存 GPU 编码设置");
  });
});
