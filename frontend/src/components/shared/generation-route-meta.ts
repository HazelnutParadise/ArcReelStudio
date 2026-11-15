import type { GenerationRoute } from "@/utils/generation-mode";

/**
 * 生成模式的文案。向导二卡与设置页只读展示共用同一份，避免两处各自维护「生成模式 → 名称 / 描述」的对应关系而漂移。
 * 不放 I2V、R2V 这类模型输入类型的缩写：创作者看不懂，名称与描述已经说清楚了。
 */
export const ROUTE_META: Record<GenerationRoute, { nameKey: string; descKey: string }> = {
  storyboard: { nameKey: "route_storyboard", descKey: "route_storyboard_desc" },
  reference_video: { nameKey: "route_reference_video", descKey: "route_reference_video_desc" },
};
