import type { Asset } from "@/types/asset";
import type { Series } from "@/types/series";

/** 系列的测试工厂：默认是一个空系列，用例只覆盖自己关心的字段。 */
export function makeSeries(overrides: Partial<Series> = {}): Series {
  return {
    id: 1,
    name: "星海纪事",
    description: "",
    world_setting: "",
    plot_setting: "",
    project_names: [],
    asset_ids: [],
    updated_at: null,
    ...overrides,
  };
}

export function makeSeriesAsset(overrides: Partial<Asset> = {}): Asset {
  return {
    id: "a1",
    type: "character",
    name: "王小明",
    description: "",
    voice_style: "",
    image_path: null,
    audio_path: null,
    source_project: null,
    updated_at: null,
    derivatives: [],
    ...overrides,
  };
}
