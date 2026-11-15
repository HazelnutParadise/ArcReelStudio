/**
 * 生成入口的前置检查：缺少能生成该媒体的供应商，或没有可用的默认模型时，不提交任务，
 * 改弹一条带「前往设置」的提示。所有生成按钮都经 `actions/generation.ts` 入队，检查只在那里做一次；
 * 任务提交后才失败时，`useTaskFailureNotifications` 按失败码给通知附上同一个入口。
 *
 * 配置状态读不到（未初始化，例如成员无权读全局设置）时不拦截，由服务端准入兜底。
 */
import { navigate } from "wouter/use-browser-location";
import { settingsSectionPath, type SettingsSection } from "@/app-routes";
import i18n from "@/i18n";
import { useAppStore, type ToastAction } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { useProjectsStore } from "@/stores/projects-store";
import type { ProjectData } from "@/types";

export type GenerationMedia = "image" | "video" | "audio" | "text" | "music" | "sfx";

export interface GenerationBlocker {
  reason: "no_provider" | "no_default_model";
  section: Extract<SettingsSection, "providers" | "default-models">;
}

/** 项目自己选了模型时，全局默认模型留空也不妨碍生成。 */
function projectPicksModel(media: GenerationMedia, project: ProjectData | null): boolean {
  if (!project) return false;
  const picks: Record<GenerationMedia, Array<string | null | undefined>> = {
    image: [
      project.image_backend,
      project.default_image_backend,
      project.image_provider_t2i,
      project.image_provider_i2i,
    ],
    video: [project.video_backend, project.video_provider_i2v, project.video_provider_r2v],
    text: [project.default_text_backend, project.text_backend_simple, project.text_backend_complex],
    audio: [project.audio_backend],
    music: [project.music_backend],
    sfx: [project.sfx_backend],
  };
  return picks[media].some((value) => !!value);
}

/** 这类生成现在缺什么；不缺时为 null。 */
export function generationBlocker(media: GenerationMedia): GenerationBlocker | null {
  const status = useConfigStatusStore.getState();
  if (!status.initialized) return null;
  if (media === "music" || media === "sfx") {
    // 音乐与音效没有自动挑选：没设默认模型就不能生成
    const unset = status.unsetDefaultModels.includes(media);
    return unset && !projectPicksModel(media, useProjectsStore.getState().currentProjectData)
      ? { reason: "no_default_model", section: "default-models" }
      : null;
  }
  if (!status.hasMediaType(media)) return { reason: "no_provider", section: "providers" };
  const defaultMissing = status.issues.some((issue) => issue.key === `no-default-${media}-model`);
  if (defaultMissing && !projectPicksModel(media, useProjectsStore.getState().currentProjectData)) {
    return { reason: "no_default_model", section: "default-models" };
  }
  return null;
}

/** 提示上的「前往设置」，打开缺项所在的设置分区。 */
export function openSettingsAction(section: SettingsSection): ToastAction {
  return { label: i18n.t("dashboard:open_settings_action"), onClick: () => navigate(settingsSectionPath(section)) };
}

/** 缺前置条件时弹提示并返回 true，调用方据此不提交。 */
export function blockGeneration(media: GenerationMedia): boolean {
  const blocker = generationBlocker(media);
  if (!blocker) return false;
  const text = i18n.t(`dashboard:generation_blocked_${blocker.reason}`, {
    media: i18n.t(`dashboard:generation_media_${media}`),
  });
  useAppStore.getState().pushToast(text, "error", { action: openSettingsAction(blocker.section) });
  return true;
}

/** 任务失败码里属于「设置没配好」的那几种，对应要打开的设置分区。 */
const SETTINGS_FAILURE_SECTIONS: Record<string, SettingsSection> = {
  default_model_not_set: "default-models",
  model_not_selected: "default-models",
  model_not_in_provider_catalog: "default-models",
  model_discontinued: "default-models",
  provider_unsupported_media: "default-models",
  credential_not_found: "providers",
  vertex_connection_missing: "providers",
  vertex_credential_file_missing: "providers",
};

/** 失败码指向设置问题时返回要打开的分区，否则为 null。 */
export function settingsSectionForFailure(errorCode: string | null | undefined): SettingsSection | null {
  return (errorCode && SETTINGS_FAILURE_SECTIONS[errorCode]) || null;
}
