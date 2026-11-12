import type { Series, SeriesSettingsPatch } from "@/types/series";

/** 世界观与剧情设定的字数上限；Agent 每次开始会话都会读取，过长会挤占上下文。 */
export const SERIES_SETTING_MAX = 6000;

export type SeriesDraft = Pick<Series, "name" | "description" | "world_setting" | "plot_setting">;

const DRAFT_FIELDS = ["name", "description", "world_setting", "plot_setting"] as const;

export function draftOf(series: Series): SeriesDraft {
  return {
    name: series.name,
    description: series.description,
    world_setting: series.world_setting,
    plot_setting: series.plot_setting,
  };
}

/** 草稿相对系列当前值有改动的字段；名称按去掉首尾空白后的值比较与提交。 */
export function changedFields(series: Series, draft: SeriesDraft): SeriesSettingsPatch {
  const patch: SeriesSettingsPatch = {};
  for (const key of DRAFT_FIELDS) {
    const value = key === "name" ? draft.name.trim() : draft[key];
    if (value !== series[key]) patch[key] = value;
  }
  return patch;
}

/** 把一个系列写回列表：同一个项目只属于一个系列，别的系列里同名项目随之移除。 */
export function replaceSeries(list: Series[], next: Series): Series[] {
  const moved = new Set(next.project_names);
  return list.map((item) =>
    item.id === next.id
      ? next
      : item.project_names.some((name) => moved.has(name))
        ? { ...item, project_names: item.project_names.filter((name) => !moved.has(name)) }
        : item,
  );
}
