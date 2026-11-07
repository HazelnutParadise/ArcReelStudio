import { API, type AssetCreateResult } from "@/api";
import type { AssetSheetType, Character, Product } from "@/types";
import type { GalleryAssetSource } from "./gallery-model";
import type { UnitJson } from "@/collab/ydoc-json";

/**
 * 详情编辑器里进入未保存修改的字段。四类资产共用一个形状，按类型只用到其中几项：
 * 角色有声音风格，商品有品牌与卖点。改名、上传、增删别名是立即执行的动作，不在这里。
 */
export interface AssetFields {
  description: string;
  voiceStyle: string;
  brand: string;
  /** 卖点，每行一条。 */
  sellingPoints: string;
}

/** 新建资产时多一个名称。 */
export interface NewAssetFields extends AssetFields {
  name: string;
}

export const EMPTY_ASSET_FIELDS: AssetFields = { description: "", voiceStyle: "", brand: "", sellingPoints: "" };

export function assetFieldsOf(type: AssetSheetType, asset: GalleryAssetSource): AssetFields {
  return {
    description: asset.description ?? "",
    voiceStyle: type === "character" ? ((asset as Character).voice_style ?? "") : "",
    brand: type === "product" ? ((asset as Product).brand ?? "") : "",
    sellingPoints: type === "product" ? ((asset as Product).selling_points ?? []).join("\n") : "",
  };
}

/** 卖点文本按行拆开，去掉空行与两端空白。 */
export function parseSellingPoints(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** 卖点只比较拆分后的条目：多一个空行不算修改。 */
export function assetFieldsEqual(a: AssetFields, b: AssetFields): boolean {
  return (
    a.description === b.description &&
    a.voiceStyle === b.voiceStyle &&
    a.brand === b.brand &&
    parseSellingPoints(a.sellingPoints).join("\n") === parseSellingPoints(b.sellingPoints).join("\n")
  );
}

/** 只带改过的字段，键名是资产接口的字段名。 */
export function assetFieldsPatch(
  type: AssetSheetType,
  value: AssetFields,
  saved: AssetFields,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  if (value.description !== saved.description) patch.description = value.description;
  if (type === "character" && value.voiceStyle !== saved.voiceStyle) patch.voice_style = value.voiceStyle;
  if (type === "product") {
    if (value.brand !== saved.brand) patch.brand = value.brand;
    const points = parseSellingPoints(value.sellingPoints);
    if (points.join("\n") !== parseSellingPoints(saved.sellingPoints).join("\n")) patch.selling_points = points;
  }
  return patch;
}

/** 保存后的规范形状：卖点去掉空行，与服务端回写的内容一致。 */
export function normalizeAssetFields(value: AssetFields): AssetFields {
  return { ...value, sellingPoints: parseSellingPoints(value.sellingPoints).join("\n") };
}

export function updateAssetFields(
  projectName: string,
  type: AssetSheetType,
  name: string,
  patch: Record<string, unknown>,
): Promise<unknown> {
  switch (type) {
    case "character":
      return API.updateCharacter(projectName, name, patch);
    case "scene":
      return API.updateProjectScene(projectName, name, patch);
    case "prop":
      return API.updateProjectProp(projectName, name, patch);
    case "product":
      return API.updateProjectProduct(projectName, name, patch);
  }
}

export function createAsset(
  projectName: string,
  type: AssetSheetType,
  fields: NewAssetFields,
): Promise<AssetCreateResult> {
  const name = fields.name.trim();
  switch (type) {
    case "character":
      return API.addCharacter(projectName, name, fields.description, fields.voiceStyle);
    case "scene":
      return API.addProjectScene(projectName, name, fields.description);
    case "prop":
      return API.addProjectProp(projectName, name, fields.description);
    case "product":
      return API.addProjectProduct(
        projectName,
        name,
        fields.description,
        fields.brand.trim() || undefined,
        parseSellingPoints(fields.sellingPoints),
      );
  }
}

/** 资产在协作房间里的内容（存储里的字段名）：卖点是每行一条的一段文字。 */
export function assetFieldsToUnit(type: AssetSheetType, value: AssetFields): UnitJson {
  const unit: UnitJson = { description: value.description };
  if (type === "character") unit.voice_style = value.voiceStyle;
  if (type === "product") {
    unit.brand = value.brand;
    unit.selling_points = value.sellingPoints;
  }
  return unit;
}

export function assetFieldsFromUnit(unit: UnitJson, fallback: AssetFields): AssetFields {
  const text = (value: unknown, otherwise: string) => (typeof value === "string" ? value : otherwise);
  return {
    description: text(unit.description, fallback.description),
    voiceStyle: text(unit.voice_style, fallback.voiceStyle),
    brand: text(unit.brand, fallback.brand),
    sellingPoints: text(unit.selling_points, fallback.sellingPoints),
  };
}
