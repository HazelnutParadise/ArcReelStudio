/** 弹窗清单里的一个条目：是否待编写、视觉层是否已有内容。 */
export interface PromptAuthoringEntry {
  id: string;
  pending: boolean;
  hasContent: boolean;
}

/** 各条目形态的数组键、id 字段与视觉层字段；参考生视频单元的正文即视觉层。 */
const ENTRY_SHAPES: readonly { key: string; idField: string; fields: readonly string[] }[] = [
  { key: "video_units", idField: "unit_id", fields: ["text"] },
  { key: "segments", idField: "segment_id", fields: ["image_prompt", "video_prompt"] },
  { key: "scenes", idField: "scene_id", fields: ["image_prompt", "video_prompt"] },
  { key: "shots", idField: "shot_id", fields: ["image_prompt", "video_prompt"] },
];

function filled(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return Boolean(value);
}

/** 从正式脚本取出弹窗清单（剧本顺序）。 */
export function promptAuthoringEntries(script: unknown): PromptAuthoringEntry[] {
  if (!script || typeof script !== "object") return [];
  const record = script as Record<string, unknown>;
  const shape = ENTRY_SHAPES.find((candidate) => Array.isArray(record[candidate.key]));
  if (!shape) return [];
  const items = record[shape.key] as unknown[];
  return items.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Record<string, unknown>;
    const id = item[shape.idField];
    if (typeof id !== "string" || !id) return [];
    return [
      {
        id,
        pending: item.pending_authoring === true,
        hasContent: shape.fields.some((field) => filled(item[field])),
      },
    ];
  });
}

/**
 * 待编写条目还缺哪一侧提示词：服务端在两侧都写好后才清除待编写标记，只写了一侧时说出另一侧，
 * 免得写好一侧的人以为状态没跟上。两侧都空或不是图/视频两侧的形态时为 null，按整体待编写显示。
 */
export function pendingPromptSide(item: { image_prompt?: unknown; video_prompt?: unknown }): "image" | "video" | null {
  const image = filled(item.image_prompt);
  const video = filled(item.video_prompt);
  if (image && !video) return "video";
  if (video && !image) return "image";
  return null;
}
