import type { JsonValue, UnitJson } from "@/collab/ydoc-json";
import type { ProjectData } from "@/types";

import {
  buildProjectPatch,
  deriveForm,
  type GlobalModelDefaults,
  type ProjectFacts,
  type ProjectSettingsForm,
} from "./project-settings-form";

/**
 * 项目设置的协作房间：文档内容是项目文件里的设置字段（与项目 PATCH 同名），服务端按 PATCH 的规则写回。
 * 参考图只能上传换掉，房间里只读；清空它即取消参考图。
 */
export interface ProjectSettingsCollabOptions {
  projectName: string;
  facts: ProjectFacts;
  globals: GlobalModelDefaults;
}

export function projectSettingsFromUnit(unit: UnitJson, { projectName, facts, globals }: ProjectSettingsCollabOptions) {
  const project = { ...unit, generation_mode: facts.generationRoute } as unknown as ProjectData;
  const form = deriveForm(project, projectName, globals, null);
  if (form.style.kind !== "image") return form;
  // 参考图文件名固定，换图不换路径：以风格描述（每次上传重新分析）区分版本，别人换了图这里也会重新加载
  const description = typeof unit.style_description === "string" ? unit.style_description : "";
  return { ...form, style: { ...form.style, preview: withVersion(form.style.preview, description) } };
}

export function projectSettingsToUnit(
  value: ProjectSettingsForm,
  current: UnitJson,
  options: ProjectSettingsCollabOptions,
): UnitJson {
  const saved = projectSettingsFromUnit(current, options);
  const patch = buildProjectPatch(value, saved, options.facts, options.globals) as Record<string, unknown>;
  const next: UnitJson = { ...current };
  for (const [key, raw] of Object.entries(patch)) {
    if (key === "clear_style_image") continue;
    next[key] = (raw ?? null) as JsonValue;
  }
  // 模版与参考图二选一：选了模版或取消风格时参考图一并清空（服务端同一条规则）
  if ("style_template_id" in patch || patch.clear_style_image) {
    next.style_image = "";
    next.style_description = "";
  }
  return next;
}

function withVersion(url: string, description: string): string {
  if (!description) return url;
  let hash = 0;
  for (let i = 0; i < description.length; i++) hash = (Math.imul(hash, 31) + description.charCodeAt(i)) | 0;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}d=${(hash >>> 0).toString(36)}`;
}
