/**
 * 生成入口的前置检查：缺供应商或默认模型时不提交、只弹一条带「前往设置」的提示；
 * 配置状态读不到时不拦截；任务提交后才因设置问题失败时，通知带同一个入口。
 */
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { navigate } from "wouter/use-browser-location";
import { API } from "@/api";
import { settingsSectionPath } from "@/app-routes";
import i18n from "@/i18n";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore, type ConfigIssue } from "@/stores/config-status-store";
import { useProjectsStore } from "@/stores/projects-store";
import type { ProjectData } from "@/types";
import {
  enqueueAssetSheetBatch,
  enqueueCharacter,
  enqueueStoryboard,
  enqueueStoryboardBatch,
  GenerationBlockedError,
} from "./generation";
import { blockGeneration, generationBlocker, settingsSectionForFailure } from "./generation-prerequisites";

vi.mock("wouter/use-browser-location", async (importOriginal) => ({
  ...(await importOriginal<typeof import("wouter/use-browser-location")>()),
  navigate: vi.fn(),
}));

function configStatus(state: {
  available?: string[];
  issues?: Partial<ConfigIssue>[];
  unsetDefaults?: string[];
  initialized?: boolean;
}): void {
  useConfigStatusStore.setState({
    initialized: state.initialized ?? true,
    availableMediaTypes: state.available ?? ["image", "video", "text", "audio"],
    issues: (state.issues ?? []) as ConfigIssue[],
    unsetDefaultModels: state.unsetDefaults ?? [],
  });
}

const DEFAULT_IMAGE_MISSING = { key: "no-default-image-model", section: "default-models", label: "x" } as const;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(navigate).mockClear();
  useConfigStatusStore.setState(useConfigStatusStore.getInitialState(), true);
  useProjectsStore.setState(useProjectsStore.getInitialState(), true);
  useAppStore.setState({ toast: null });
});

describe("generation entry points without a provider", () => {
  it("submit nothing and show one error with an action that opens the provider settings", async () => {
    configStatus({ available: ["video", "text"] });
    const api = vi.spyOn(API, "generateCharacter");

    const result = await enqueueCharacter("demo", "阿岚");

    expect(api).not.toHaveBeenCalled();
    expect(result.blocked).toBe(true);
    const toast = useAppStore.getState().toast;
    expect(toast?.tone).toBe("error");
    expect(toast?.text).toBe(
      i18n.t("dashboard:generation_blocked_no_provider", { media: i18n.t("dashboard:generation_media_image") }),
    );
    expect(toast?.action?.label).toBe(i18n.t("dashboard:open_settings_action"));
    toast?.action?.onClick();
    expect(navigate).toHaveBeenCalledWith(settingsSectionPath("providers"));
  });

  it("stop storyboard generation the same way instead of failing silently later", async () => {
    configStatus({ available: [] });
    const api = vi.spyOn(API, "generateStoryboard");

    await enqueueStoryboard("demo", "E1S01", "prompt", "episode_1.json");

    expect(api).not.toHaveBeenCalled();
    expect(useAppStore.getState().toast?.action).toBeDefined();
  });

  it("throw a handled error from batch entry points, whose result is the server's admission", async () => {
    configStatus({ available: ["text"] });
    const sheets = vi.spyOn(API, "submitAssetSheetBatch");
    const videos = vi.spyOn(API, "submitStoryboardBatch");

    await expect(enqueueAssetSheetBatch("demo", { kind: "all" } as never)).rejects.toBeInstanceOf(
      GenerationBlockedError,
    );
    await expect(enqueueStoryboardBatch("demo", 1, "videos")).rejects.toBeInstanceOf(GenerationBlockedError);
    expect(sheets).not.toHaveBeenCalled();
    expect(videos).not.toHaveBeenCalled();
  });
});

describe("generationBlocker", () => {
  it("points to the default model settings when the provider exists but no default model is set", () => {
    configStatus({ issues: [DEFAULT_IMAGE_MISSING] });
    expect(generationBlocker("image")).toEqual({ reason: "no_default_model", section: "default-models" });
  });

  it("lets the project's own model choice stand in for a missing global default", () => {
    configStatus({ issues: [DEFAULT_IMAGE_MISSING] });
    useProjectsStore.setState({ currentProjectData: { image_backend: "gemini/imagen-4" } as ProjectData });
    expect(generationBlocker("image")).toBeNull();
  });

  it("blocks music and sound effects without a default model, since they are never picked automatically", () => {
    configStatus({ unsetDefaults: ["music"] });
    expect(generationBlocker("music")).toEqual({ reason: "no_default_model", section: "default-models" });
    expect(generationBlocker("sfx")).toBeNull();
  });

  it("never blocks while the settings could not be read, leaving the decision to the server", () => {
    configStatus({ initialized: false, available: [] });
    expect(blockGeneration("image")).toBe(false);
    expect(useAppStore.getState().toast).toBeNull();
  });
});

describe("task failures caused by settings", () => {
  it("map to the settings section that fixes them", () => {
    expect(settingsSectionForFailure("default_model_not_set")).toBe("default-models");
    expect(settingsSectionForFailure("credential_not_found")).toBe("providers");
    expect(settingsSectionForFailure("provider_rejected")).toBeNull();
    expect(settingsSectionForFailure(undefined)).toBeNull();
  });

  it("carry an open-settings action on the toast and a settings link on the bell entry", () => {
    useAppStore.getState().pushNotification("失败", "error", { settings: "default-models" });

    const { toast, workspaceNotifications } = useAppStore.getState();
    expect(toast?.action?.label).toBe(i18n.t("dashboard:open_settings_action"));
    toast?.action?.onClick();
    expect(navigate).toHaveBeenCalledWith(settingsSectionPath("default-models"));
    expect(workspaceNotifications[0]?.settings).toBe("default-models");
  });
});
