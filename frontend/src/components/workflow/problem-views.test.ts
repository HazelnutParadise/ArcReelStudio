import { describe, expect, it } from "vite-plus/test";
import type { TFunction } from "i18next";
import enWorkflow from "@/i18n/en/workflow";
import viWorkflow from "@/i18n/vi/workflow";
import ruWorkflow from "@/i18n/ru/workflow";
import zhTwWorkflow from "@/i18n/zh-TW/workflow";
import zhWorkflow from "@/i18n/zh/workflow";
import { admissionUnitViews, blockerViews, problemViews } from "./problem-views";

const CATALOGS = { en: enWorkflow, vi: viWorkflow, zh: zhWorkflow } as const;
const ALL_CATALOGS = { ...CATALOGS, ru: ruWorkflow, "zh-TW": zhTwWorkflow } as const;

function translatorFor(catalog: Record<string, string>) {
  return ((key: string, options?: { defaultValue?: string }) =>
    catalog[key] ?? options?.defaultValue ?? key) as unknown as TFunction<"workflow">;
}

/** 计划步骤里会出现的问题码：脚本结构的发声准入、项目数据升级，以及视频请求事实。 */
const PLAN_PROBLEM_CODES = [
  "mixed_speech",
  "needs_replan",
  "parse_failed",
  "empty_speaker",
  "project_migration_failed",
  "project_schema_unsupported",
  "video_capability_unavailable",
  "video_supported_durations_missing",
  "video_supported_durations_invalid",
  "video_supported_durations_incompatible",
  "reference_capability_unavailable",
  "reference_supported_durations_missing",
  "reference_supported_durations_invalid",
  "reference_supported_durations_incompatible",
];

describe("计划提示的本地化", () => {
  it.each(Object.keys(CATALOGS))("%s 下每个问题码都有自己的译文", (locale) => {
    const catalog: Record<string, string> = CATALOGS[locale as keyof typeof CATALOGS];
    const t = translatorFor(catalog);
    const views = problemViews(
      t,
      PLAN_PROBLEM_CODES.map((code) => ({ code, action: "fix_input", unit_id: "E1S01", params: {} })),
    );
    const fallback = catalog.problem_fallback_fix_input;
    expect(views.filter((view) => view.summary === fallback).map((view) => view.key)).toEqual([]);
  });

  it("不认识的问题码按交回的动作给通用原因，不露出问题码", () => {
    const t = translatorFor(zhWorkflow);
    const [known, unknown] = problemViews(t, [
      { code: "provider_rejected_xyz", action: "configure_provider", unit_id: "E1S03", params: {} },
      { code: "provider_rejected_xyz", action: "brand_new_action", params: {} },
    ]);
    expect(known.summary).toBe("当前的模型配置不支持这次生成。");
    expect(known.unitId).toBe("E1S03");
    expect(unknown.summary).toBe("这个单元暂时不能生成。");
  });

  it("计划里的准入缺口没有本地化文案时按问题码陈述，不展示服务端原文", () => {
    const t = translatorFor(zhWorkflow);
    const [view] = admissionUnitViews(
      t,
      [
        {
          unit_id: "E1S02",
          admitted: false,
          problems: [
            {
              code: "mixed_speech",
              detail: '发声准入未通过：{"reason": "character_and_narrator_mixed"}',
              action: "replan_unit",
            },
          ],
        },
      ],
      (value) => `${value}s`,
    );
    expect(view.unitId).toBe("E1S02");
    expect(view.summary).toBe("这个单元同时有角色台词和旁白，需要拆开。");
    expect(view.detail).toBeNull();
  });
});

/** 带插值的译文查表：下一步这层框架要把动作短语填进 `{{step}}`。 */
function interpolatingTranslatorFor(catalog: Record<string, string>) {
  return ((key: string, options?: Record<string, unknown> & { defaultValue?: string }) => {
    const template = catalog[key] ?? options?.defaultValue ?? key;
    return template.replace(/\{\{(\w+)\}\}/g, (_match, name: string) => String(options?.[name] ?? ""));
  }) as unknown as TFunction<"workflow">;
}

describe("版本过旧的项目", () => {
  const blocker = {
    code: "project_schema_unsupported",
    path: ".migration_failure.json",
    reason: "schema version 18 is older than v19",
  };

  it.each(Object.keys(ALL_CATALOGS))("%s 下 blocker 讲版本过旧，下一步指向上游升级而不是修复", (locale) => {
    const catalog: Record<string, string> = ALL_CATALOGS[locale as keyof typeof ALL_CATALOGS];
    const t = interpolatingTranslatorFor(catalog);
    const [view] = blockerViews(t, [blocker]);

    expect(view.summary).toBe(catalog.problem_project_schema_unsupported);
    expect(view.nextStep).toBe(catalog.next_step.replace("{{step}}", catalog.action_upgrade_project_upstream));
    expect(view.nextStep).not.toContain(catalog.action_repair_project_data);
    expect(view.detail).toBe(blocker.reason);
  });

  it("计划里的同码问题给出同一句原因与下一步", () => {
    const t = interpolatingTranslatorFor(zhWorkflow);
    const [planView] = problemViews(t, [
      { code: "project_schema_unsupported", action: "upgrade_project_upstream", params: { version: 18, minimum: 19 } },
    ]);
    const [blockerView] = blockerViews(t, [blocker]);

    expect(planView.summary).toBe(blockerView.summary);
    expect(planView.nextStep).toBe(blockerView.nextStep);
    expect(planView.summary).toContain("上游 ArcReel");
  });
});
