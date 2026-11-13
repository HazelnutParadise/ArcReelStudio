import type { TFunction } from "i18next";
import { describe, expect, it } from "vite-plus/test";
import type { VideoCapabilityProblem } from "@/types";
import { tierProblemText } from "./unit-tier-problem";

/** 返回「键<插值参数>」的 t：用来看清文案落在哪个键、带了哪些参数。 */
const t = ((key: string, options?: Record<string, unknown>) =>
  options ? `${key}<${Object.values(options).join(",")}>` : key) as unknown as TFunction<"dashboard">;

function problem(code: string): VideoCapabilityProblem {
  return { code, params: {}, action: "configure_video_model" };
}

function reasonKey(code: string): string {
  const { hint } = tierProblemText(t, problem(code), "r2v");
  const match = /(reference_unit_tier_reason_[a-z_]+)</.exec(hint);
  expect(match, `${code} 的提示里没有成因文案：${hint}`).not.toBeNull();
  return match![1];
}

describe("tierProblemText", () => {
  it("项目的模型只选了供应商时，成因说明是没有选定模型，不是笼统的「未解析」", () => {
    expect(reasonKey("model_not_selected")).toBe("reference_unit_tier_reason_not_selected");
  });

  it("模型引用不在清单中仍说模型已删除或停用", () => {
    expect(reasonKey("model_not_in_provider_catalog")).toBe("reference_unit_tier_reason_removed");
  });

  it("没有专门成因的问题码退回笼统的未解析成因", () => {
    expect(reasonKey("some_future_code")).toBe("reference_unit_tier_reason_unresolved");
  });

  it("成因文案按所落的桶插值", () => {
    const { hint } = tierProblemText(t, problem("model_not_selected"), "r2v");
    expect(hint).toContain("reference_unit_tier_reason_not_selected<reference_bucket_r2v>");
  });
});
