import { describe, expect, it } from "vitest";

import { toSupportedChinese } from "@/i18n";

describe("toSupportedChinese", () => {
  it.each(["zh-TW", "zh-tw", "zh-HK", "zh-MO", "zh-Hant", "zh-Hant-TW"])("把 %s 归到繁体中文", (lng) => {
    expect(toSupportedChinese(lng)).toBe("zh-TW");
  });

  it.each(["zh", "zh-CN", "zh-Hans", "zh-SG", "en-US", "vi"])("其余语言 %s 保持不变", (lng) => {
    expect(toSupportedChinese(lng)).toBe(lng);
  });
});
