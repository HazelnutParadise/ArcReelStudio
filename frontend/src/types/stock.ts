/** 免版权素材库（docs/adr/0128）：只列不用署名就能商用的素材。 */

/** 素材用途：BGM、音效、图片。 */
export type StockKind = "music" | "sfx" | "image";

/** 允许出现的授权：CC0、公有领域，以及 Pixabay / Pexels 自己的授权。 */
export type StockLicense = "cc0" | "pdm" | "pixabay" | "pexels";

/** 一条搜索结果。`preview_url` 是缩略图（图片）或试听档（音频）。 */
export interface StockItem {
  source: string;
  id: string;
  kind: StockKind;
  title: string;
  creator: string | null;
  license: StockLicense;
  license_url: string;
  page_url: string;
  preview_url: string | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
}

/** 一个来源这次搜索的结果状态：正常、还没设置密钥、密钥被拒、请求失败。 */
export type StockSourceStatus = "ok" | "key_missing" | "key_rejected" | "failed";

export interface StockSearchResult {
  items: StockItem[];
  sources: { source: string; status: StockSourceStatus }[];
}

/** 一个素材来源，以及当前成员能不能用它。 */
export interface StockSource {
  id: string;
  display_name: string;
  kinds: StockKind[];
  /** 密钥归谁：不需要、整个工作区共用（管理员设置）、每位成员用自己的。 */
  key_scope: "none" | "workspace" | "member";
  key_url: string | null;
  available: boolean;
  key_masked: string | null;
  can_set_key: boolean;
}
