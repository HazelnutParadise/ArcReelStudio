import { describe, expect, it } from 'vite-plus/test';

type Messages = Record<string, unknown>;

const zh = import.meta.glob<Messages>('./zh/*.ts', { eager: true, import: 'default' });
const zhTW = import.meta.glob<Messages>('./zh-TW/*.ts', { eager: true, import: 'default' });
const vi = import.meta.glob<Messages>('./vi/*.ts', { eager: true, import: 'default' });
const en = import.meta.glob<Messages>('./en/*.ts', { eager: true, import: 'default' });
const ru = import.meta.glob<Messages>('./ru/*.ts', { eager: true, import: 'default' });

function entries(modules: Record<string, Messages>): [string, string][] {
  const out: [string, string][] = [];
  const walk = (prefix: string, value: unknown) => {
    if (typeof value === 'string') out.push([prefix, value]);
    else if (value && typeof value === 'object') {
      for (const [k, v] of Object.entries(value)) walk(`${prefix}.${k}`, v);
    }
  };
  for (const [path, messages] of Object.entries(modules)) walk(path, messages);
  return out;
}

// 简体与繁体中文包守同一套标点规则；后端中文包按同一口径检查：tests/unit/lib/i18n/test_locale_wording.py
const CHINESE_PACKS = [
  ['zh', zh],
  ['zh-TW', zhTW],
] as const;

/** 只在简体中文里出现的常用字；繁体包里出现即说明有文案没有转成繁体。 */
const SIMPLIFIED_ONLY =
  /[们这个设视频项时为于与说对进会发动务类页选码号应关开当无将让还从网络数据图显输删编辑览载传导级链帮请确认]/u;

describe('locale wording', () => {
  it.each(CHINESE_PACKS)('uses a full-width colon after Chinese text in the %s pack', (_, modules) => {
    const offenders = entries(modules).filter(([, text]) => /\p{Script=Han}\s?:/u.test(text));
    expect(offenders).toEqual([]);
  });

  it.each(CHINESE_PACKS)('uses「…」for ellipses and「」for quotes in the %s pack', (_, modules) => {
    // 只查成对的引号：列举非法字符时单独出现的 " 是字符本身
    const offenders = entries(modules).filter(([, text]) => /\.\.\.|……|"[^"]*"/.test(text));
    expect(offenders).toEqual([]);
  });

  it.each(CHINESE_PACKS)('writes value ranges with「～」in the %s pack', (_, modules) => {
    // 端点含占位符或百分号、或后接单位的才算范围；两端都是裸数字的（如时长档位简写 3-15）是用户照样输入的语法
    const range =
      /\{\{\w+\}\}\s?[-–]\s?(\d|\{\{)|\d\s?[-–]\s?\{\{|\d%\s?[-–]\s?\d|\d\s?[-–]\s?\d+(\.\d+)?(%|\s?[\p{Script=Han}A-Za-z])/u;
    const offenders = entries(modules).filter(([, text]) => range.test(text));
    expect(offenders).toEqual([]);
  });

  it('writes the zh-TW pack in Traditional Chinese', () => {
    const offenders = entries(zhTW).filter(([, text]) => SIMPLIFIED_ONLY.test(text));
    expect(offenders).toEqual([]);
  });

  it.each([
    ['en', en],
    ['vi', vi],
    ['ru', ru],
  ])('keeps Chinese text and full-width punctuation out of the %s pack', (_, modules) => {
    const offenders = entries(modules).filter(([, text]) => /[\p{Script=Han}\u3000-\u303f\uff01-\uff5e]/u.test(text));
    expect(offenders).toEqual([]);
  });

  it('calls a derivative「phái sinh」throughout the vi pack, never「biến thể」', () => {
    const offenders = entries(vi).filter(([, text]) => /biến thể/iu.test(text));
    expect(offenders).toEqual([]);
  });
});
