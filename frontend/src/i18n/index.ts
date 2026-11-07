import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import resourcesToBackend from 'i18next-resources-to-backend';
import { BRAND } from '@/branding';

// 按需加载 i18n namespace：
// Vite import.meta.glob 在编译期为每个 (lang, ns) 文件生成独立 chunk；运行时由
// i18next 异步 load。资源仍是 .ts（保留 satisfies Record schema 锁），不是 JSON。
const loaders = import.meta.glob<{ default: Record<string, string> }>(
  './{en,zh,zh-TW,vi,ru}/*.ts',
);

function pathFor(lang: string, ns: string): string {
  return `./${lang}/${ns}.ts`;
}

export const SUPPORTED_LANGUAGES = ['zh', 'zh-TW', 'en', 'vi', 'ru'] as const;
export type SupportedLanguage = typeof SUPPORTED_LANGUAGES[number];

export const LANGUAGE_DISPLAY_LABELS: Record<SupportedLanguage, string> = {
  zh: '简体中文',
  'zh-TW': '繁體中文',
  en: 'English',
  vi: 'Tiếng Việt',
  ru: 'Русский',
};

const TRADITIONAL_CHINESE = /^zh-(tw|hk|mo|hant)\b/i;

/** 把浏览器语言里的繁体中文变体（zh-HK、zh-Hant-TW 等）归到 zh-TW。 */
export function toSupportedChinese(lng: string): string {
  return TRADITIONAL_CHINESE.test(lng) ? 'zh-TW' : lng;
}

const I18N_NAMESPACES = [
  'common',
  'auth',
  'dashboard',
  'errors',
  'events',
  'templates',
  'assets',
  'onboarding',
  'workflow',
] as const;

// Replace every [[brand]] placeholder in a loaded namespace with the current
// brand name. Done inside the resourcesToBackend loader so it composes with
// on-demand chunk loading. We use [[...]] rather than i18next's
// native {{...}} so the value is not treated as a runtime variable (which
// would force every t() call site to pass { brand }).
function applyBrandPlaceholders(value: unknown): unknown {
  if (typeof value === 'string') {
    // Function replacer avoids `$`-sequences in BRAND.name (e.g. "Product$1")
    // being interpreted as String.prototype.replace patterns.
    return value.replace(/\[\[\s*brand\s*\]\]/g, () => BRAND.name);
  }
  if (Array.isArray(value)) {
    return value.map(applyBrandPlaceholders);
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = applyBrandPlaceholders(v);
    }
    return out;
  }
  return value;
}

// 返回 init Promise，调用方（main.tsx / test setup）await 后再 render，避免首屏闪 key。
export const i18nReady = i18n
  .use(
    resourcesToBackend(async (lang: string, ns: string) => {
      const loader = loaders[pathFor(lang, ns)];
      if (!loader) {
        // LanguageDetector 可能解析出 zh-CN / en-GB 等带区域的 BCP47 代码，
        // i18next 会先按完整代码请求一次再 fallback 到 zh/en。这是预期路径，
        // 不应该升级成异常。返回空对象让 i18next 走 fallback 链。
        console.warn(`i18n: no resource for ${pathFor(lang, ns)}, falling back`);
        return {};
      }
      const mod = await loader();
      return applyBrandPlaceholders(mod.default) as Record<string, string>;
    }),
  )
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // 繁体中文地区（台湾、香港、澳门）的浏览器语言统一用繁体界面，其余中文用简体。
    detection: { convertDetectedLanguage: toSupportedChinese },
    // zh-TW 缺的键先回落简体中文，再回落默认。
    fallbackLng: { 'zh-TW': ['zh'], default: ['zh'] },
    supportedLngs: SUPPORTED_LANGUAGES,
    debug: false,
    interpolation: { escapeValue: false },
    defaultNS: 'common',
    ns: I18N_NAMESPACES,
    partialBundledLanguages: true,
    react: { useSuspense: false },
  });

export default i18n;
