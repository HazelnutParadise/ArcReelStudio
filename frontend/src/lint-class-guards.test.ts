/// <reference types="node" />
import { execFile } from "node:child_process";
import { copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { lintConfig } from "../lint/config";

// 用真实的 lint/config.ts 跑 vp lint（Oxlint）：夹具按各条 override 匹配的路径写进临时目录，
// 每个用例占一行，按行号取报告。夹具不在 TS 工程里，关掉类型感知规则，守卫本身不需要类型。
const FRONTEND = process.cwd();
const requireFromFrontend = createRequire(path.join(FRONTEND, "package.json"));
// 直接用 node 执行 vp 的入口脚本，不经 node_modules/.bin 的 shell 包装。
const VP = path.join(path.dirname(requireFromFrontend.resolve("vite-plus/package.json")), "bin", "vp");
const run = promisify(execFile);

async function vp(cwd: string, args: string[]): Promise<string> {
  try {
    const { stdout } = await run(process.execPath, [VP, ...args], { cwd, maxBuffer: 64 * 1024 * 1024 });
    return stdout;
  } catch (error) {
    // 有报告时以非零状态退出，输出照常在 stdout。
    const output = (error as { stdout?: string }).stdout;
    if (!output) throw error;
    return output;
  }
}

type Report = { rule: string; message: string };

async function lint(cwd: string, args: string[]): Promise<Map<string, Report[]>> {
  const stdout = await vp(cwd, ["lint", "-f", "json", ...args]);
  const { diagnostics } = JSON.parse(stdout) as {
    diagnostics: Array<{ code?: string; message: string; filename: string; labels?: Array<{ span: { line: number } }> }>;
  };
  const byLine = new Map<string, Report[]>();
  for (const d of diagnostics) {
    // code 形如 arcreel(no-raw-textarea)、eslint(no-restricted-imports)。
    const rule = (d.code ?? "").replace(/^(.+)\((.+)\)$/, "$1/$2");
    const key = `${d.filename}:${d.labels?.[0]?.span.line ?? 0}`;
    byLine.set(key, [...(byLine.get(key) ?? []), { rule, message: d.message }]);
  }
  return byLine;
}

// 夹具：每个文件以固定的两行开头，之后每个用例追加一行并记下行号。
const HEADER = [`import { cn } from "cn";`, `declare const API: Record<string, (...args: unknown[]) => unknown>;`];
const fixtures = new Map<string, string[]>();
let seq = 0;
const uid = () => `c${seq++}`;
const at = (filePath: string, code: string) => {
  const lines = fixtures.get(filePath) ?? [...HEADER];
  fixtures.set(filePath, lines);
  lines.push(code);
  return `${filePath}:${lines.length}`;
};

// 字符串字面量与模板片段两种写法各测一遍。
const literalFixture = (className: string) => `export const ${uid()} = ${JSON.stringify(className)};`;
const templateFixture = (className: string) => `export const ${uid()} = (extra: string) => \`${className} \${extra}\`;`;

let reports = new Map<string, Report[]>();
const reportsAt = (key: string) => reports.get(key) ?? [];
const guardReports = (key: string) =>
  reportsAt(key)
    .filter((r) => r.rule.startsWith("arcreel/"))
    .map((r) => r.message);

const GUARD_MESSAGE = {
  motion: "禁用 motion-safe: / motion-reduce: 前缀",
  scroll: "滚动容器（overflow-auto",
  scrollbar: "禁止在组件里写滚动条样式",
};

// 覆盖每条按文件放宽守卫的 override，以及测试文件与 API 层测试。
const SOURCE_FILES = [
  "src/lint-fixture/Fixture.tsx", // 任意源码
  "src/components/ui/fixture.tsx", // 原语目录
  "src/components/shared/page-shell/PageShell.tsx", // 视口断点白名单
  "src/actions/fixture.tsx", // 入队动作层
  "src/hooks/useModelCapabilities.ts", // 模型能力真相源
  "src/components/layout/ToastOverlay.tsx", // 提示队列的唯一转交点
];
const TEST_FIXTURES = [
  "src/lint-fixture/Fixture.test.tsx", // 任意测试
  "src/actions/fixture.test.tsx", // 入队动作层的测试仍受入队约束
  "src/api.test.ts", // API 层本体的测试
];

const LAYOUT_GUARDS = {
  viewportHeight: { code: () => literalFixture("min-h-0 h-screen"), message: "禁止视口高度" },
  fixedOverlay: { code: () => literalFixture("fixed inset-0 bg-scrim"), message: "禁止手写 fixed inset-0 浮层" },
  scrollHeight: {
    code: () => `export const ${uid()} = (el: HTMLElement) => el.scrollHeight;`,
    message: "禁止读写 scrollHeight",
  },
  breakpoint: { code: () => literalFixture("flex md:grid"), message: "业务组件禁用视口断点前缀" },
  rawZIndex: { code: () => literalFixture("relative z-10"), message: "调用处不写数值层级" },
  arbitraryZIndex: { code: () => literalFixture("hover:z-[60]"), message: "调用处不写数值层级" },
  backdropBlur: { code: () => literalFixture("bg-popover/80 backdrop-blur-sm"), message: "不使用背景模糊" },
  rawDuration: { code: () => literalFixture("transition-colors duration-150"), message: "时长与缓动只用 token" },
  rawEase: { code: () => literalFixture("transition-opacity ease-in-out"), message: "时长与缓动只用 token" },
  toastPrimitive: {
    code: () => {
      const id = uid();
      return `import { toast as ${id}t } from "@/components/ui/toast"; export const ${id} = ${id}t;`;
    },
    message: "全局提示统一用 useAppStore 的 pushToast",
  },
  toastPrimitiveRelative: {
    code: () => {
      const id = uid();
      return `import { toast as ${id}t } from "../ui/toast"; export const ${id} = ${id}t;`;
    },
    message: "全局提示统一用 useAppStore 的 pushToast",
  },
  toastPrimitiveReexport: {
    code: () => `export { toast as ${uid()} } from "@/components/ui/toast";`,
    message: "全局提示统一用 useAppStore 的 pushToast",
  },
  toastPrimitiveExportAll: {
    code: () => `export * from "@/components/ui/toast";`,
    message: "全局提示统一用 useAppStore 的 pushToast",
  },
};
type LayoutGuard = keyof typeof LAYOUT_GUARDS;
const ALL_LAYOUT_GUARDS = Object.keys(LAYOUT_GUARDS) as LayoutGuard[];
const except = (...skipped: LayoutGuard[]) => ALL_LAYOUT_GUARDS.filter((g) => !skipped.includes(g));

// 布局守卫对全部源码生效：原语放过 fixed inset-0、scrollHeight、视口断点、数值层级与原始动效 token（背景模糊不放过），
// 白名单放过视口断点，ToastOverlay 放过 toast 原语导入；测试文件不受布局守卫约束。
const LAYOUT_ENFORCED: Record<string, LayoutGuard[]> = {
  "src/lint-fixture/Fixture.tsx": ALL_LAYOUT_GUARDS,
  "src/components/ui/fixture.tsx": [
    "viewportHeight",
    "backdropBlur",
    "toastPrimitive",
    "toastPrimitiveRelative",
    "toastPrimitiveReexport",
    "toastPrimitiveExportAll",
  ],
  "src/components/shared/page-shell/PageShell.tsx": except("breakpoint"),
  "src/actions/fixture.tsx": ALL_LAYOUT_GUARDS,
  "src/hooks/useModelCapabilities.ts": ALL_LAYOUT_GUARDS,
  "src/components/layout/ToastOverlay.tsx": except(
    "toastPrimitive",
    "toastPrimitiveRelative",
    "toastPrimitiveReexport",
    "toastPrimitiveExportAll",
  ),
  "src/lint-fixture/Fixture.test.tsx": [],
  "src/actions/fixture.test.tsx": [],
  "src/api.test.ts": [],
};

const API_GUARDS = {
  enqueue: { code: () => `API.generateVideo("${uid()}");`, message: "入队类 API 方法只能经 src/actions/" },
  capabilities: { code: () => `API.getVideoCapabilities("${uid()}");`, message: "模型能力只能经 useModelCapabilities 消费" },
  moduleMock: { code: () => `vi.mock("@/api/${uid()}");`, message: "禁止整模块 mock" },
  // 丢弃结算值的三种写法：直接调用、await 后丢弃、void。
  discardedRefresh: {
    code: () => {
      const id = uid();
      return `declare const ${id}: { refreshProject(): Promise<void> }; ${id}.refreshProject();`;
    },
    message: "不要丢弃 refreshProject 的结算值",
  },
  discardedRefreshAwait: {
    code: () => {
      const id = uid();
      return `declare const ${id}: { refreshProject(): Promise<void> }; await ${id}.refreshProject();`;
    },
    message: "不要丢弃 refreshProject 的结算值",
  },
  discardedRefreshVoid: {
    code: () => {
      const id = uid();
      return `declare const ${id}: { refreshProject(): Promise<void> }; void ${id}.refreshProject();`;
    },
    message: "不要丢弃 refreshProject 的结算值",
  },
};
type ApiGuard = keyof typeof API_GUARDS;
const ALL_API_GUARDS = Object.keys(API_GUARDS) as ApiGuard[];
const exceptApi = (...skipped: ApiGuard[]) => ALL_API_GUARDS.filter((g) => !skipped.includes(g));

// API 直调与 mock 约束对源码和测试都生效：动作层放过入队、useModelCapabilities 放过能力查询，API 层本体的测试两条都放过。
const API_ENFORCED: Record<string, ApiGuard[]> = {
  "src/lint-fixture/Fixture.tsx": ALL_API_GUARDS,
  "src/components/ui/fixture.tsx": ALL_API_GUARDS,
  "src/components/shared/page-shell/PageShell.tsx": ALL_API_GUARDS,
  "src/actions/fixture.tsx": exceptApi("enqueue"),
  "src/hooks/useModelCapabilities.ts": exceptApi("capabilities"),
  "src/components/layout/ToastOverlay.tsx": ALL_API_GUARDS,
  "src/lint-fixture/Fixture.test.tsx": ALL_API_GUARDS,
  "src/actions/fixture.test.tsx": ALL_API_GUARDS,
  "src/api.test.ts": exceptApi("enqueue", "capabilities"),
};

const VIOLATIONS: Array<[keyof typeof GUARD_MESSAGE, string]> = [
  ["motion", "size-4 motion-safe:animate-spin"],
  ["motion", "motion-reduce:transition-none"],
  ["motion", "hover:motion-safe:scale-105"],
  ["scroll", "min-h-0 flex-1 overflow-y-auto"],
  ["scroll", "overflow-auto"],
  ["scroll", "flex overflow-x-scroll"],
  ["scroll", "@md/canvas:overflow-y-auto"],
  ["scrollbar", "relative overflow-x-auto scrollbar-none"],
  ["scrollbar", "relative overflow-y-auto no-scrollbar"],
  ["scrollbar", "relative overflow-y-auto [scrollbar-width:none]"],
  ["scrollbar", "relative overflow-y-auto [&::-webkit-scrollbar]:hidden"],
  ["scrollbar", "relative overflow-y-auto scrollbar-thin"],
];

const ALLOWED = [
  "size-4 animate-spin",
  "relative min-h-0 flex-1 overflow-y-auto",
  "absolute inset-x-0 overflow-auto",
  "sticky top-0 max-h-48 overflow-y-auto",
  "overflow-hidden",
  "overflow-x-hidden",
  "relative overflow-y-auto [scrollbar-gutter:stable]",
  "relative overflow-y-auto scrollbar-gutter-stable",
  "motion-path-fixture",
  "relative z-sticky",
  "transition-colors duration-fast ease-emphasized",
  "backdrop-blur-0",
];

const RAW_TEXTAREA = `export const Editor = () => <textarea aria-label="x" />;`;
const RAW_COLORS = () => `export const ${uid()} = cn("bg-red-500");`;

// 传 onError 的刷新调用不算丢弃结算值。
const REFRESH_WITH_ON_ERROR = () => {
  const id = uid();
  return `declare const ${id}: { refreshProject(o: object): Promise<void> }; ${id}.refreshProject({ onError: () => {} });`;
};

// 原语目录的导入边界单独成文件：行号对应下方 toEqual 的期望。
const UI_IMPORTS_FIXTURE = "src/components/ui/imports-fixture.tsx";
const UI_IMPORTS = [
  `import { API as A } from "@/api";`,
  `import { useAppStore } from "@/stores/app-store";`,
  `import { PageShell } from "@/components/shared/page-shell/PageShell";`,
  `import { Button } from "@/components/ui/button";`,
  `import { useTranslation } from "react-i18next";`,
  `import { Dialog } from "./dialog";`,
  `import { useConfigStore } from "../../stores/config-store";`,
  `import { DetailPane } from "../shared/master-detail/DetailPane";`,
  `import { useProjectsStore } from "./../../stores/projects-store";`,
  `import { useTasksStore } from "@/components/ui/../../stores/tasks-store";`,
  `import { selectDeep } from "@/stores/nested/deep-store";`,
  `export const all = [A, useAppStore, PageShell, Button, useTranslation, Dialog, useConfigStore, DetailPane, useProjectsStore, useTasksStore, selectDeep];`,
];

// 补过 relative 的滚动容器：按原路径复制进临时目录，与夹具一起检查。
const REAL_SCROLL_FILES = [
  "src/components/pages/settings/PromptTemplateDetailView.tsx",
  "src/components/pages/settings/endpoints/ComfyuiEndpointDetail.tsx",
  "src/components/pages/settings/promptTemplateShared.tsx",
  "src/components/ui/attachment.tsx",
  "src/components/ui/combobox.tsx",
  "src/components/ui/dropdown-menu.tsx",
  "src/components/ui/popover.tsx",
  "src/components/ui/textarea.tsx",
  "src/components/ui/toast.tsx",
];

// 临时目录里的配置照搬 lint/config.ts，只把 JS 插件解析成绝对路径并关掉类型感知。
function fixtureConfig() {
  const resolve = (specifier: string) =>
    specifier.startsWith(".") ? path.resolve(FRONTEND, specifier) : requireFromFrontend.resolve(specifier);
  return {
    lint: {
      ...lintConfig,
      jsPlugins: lintConfig.jsPlugins.map((entry) =>
        typeof entry === "string" ? resolve(entry) : { ...entry, specifier: resolve(entry.specifier) },
      ),
      options: { typeAware: false },
    },
  };
}

let workdir = "";

describe("类名守卫", () => {
  beforeAll(async () => {
    workdir = await mkdtemp(path.join(tmpdir(), "arcreel-lint-"));
    // vp 以所在目录的 package.json 认定工作区。
    await writeFile(path.join(workdir, "package.json"), `${JSON.stringify({ name: "lint-fixture", private: true })}\n`);
    await writeFile(path.join(workdir, "vite.config.mjs"), `export default ${JSON.stringify(fixtureConfig())};\n`);
    for (const [filePath, lines] of [...fixtures, [UI_IMPORTS_FIXTURE, UI_IMPORTS] as const]) {
      await mkdir(path.dirname(path.join(workdir, filePath)), { recursive: true });
      await writeFile(path.join(workdir, filePath), `${lines.join("\n")}\n`);
    }
    for (const filePath of REAL_SCROLL_FILES) {
      await mkdir(path.dirname(path.join(workdir, filePath)), { recursive: true });
      await copyFile(path.join(FRONTEND, filePath), path.join(workdir, filePath));
    }
    reports = await lint(workdir, ["-c", "vite.config.mjs", "src"]);
  }, 60_000);

  afterAll(async () => {
    if (workdir) await rm(workdir, { recursive: true, force: true });
  });

  describe.each(SOURCE_FILES)("%s", (filePath) => {
    const violations = VIOLATIONS.map(
      ([guard, className]) =>
        [guard, className, at(filePath, literalFixture(className)), at(filePath, templateFixture(className))] as const,
    );
    it.each(violations)("报出 %s 违规：%s", (guard, _className, literal, template) => {
      // 用 toContainEqual：任意值变体（[&::-webkit-scrollbar]:）还会被视口断点守卫报出。
      expect(guardReports(literal)).toContainEqual(expect.stringContaining(GUARD_MESSAGE[guard]));
      expect(guardReports(template)).toContainEqual(expect.stringContaining(GUARD_MESSAGE[guard]));
    });

    const allowed = ALLOWED.map(
      (className) => [className, at(filePath, literalFixture(className)), at(filePath, templateFixture(className))] as const,
    );
    it.each(allowed)("放过 %s", (_className, literal, template) => {
      expect(guardReports(literal)).toEqual([]);
      expect(guardReports(template)).toEqual([]);
    });

    const rawColors = at(filePath, RAW_COLORS());
    it("报出原始调色板", () => {
      expect(reportsAt(rawColors).map((r) => r.rule)).toContain("shadcn/no-raw-colors");
    });
  });

  describe.each([...SOURCE_FILES, ...TEST_FIXTURES])("%s 的布局与 API 守卫", (filePath) => {
    const layout = ALL_LAYOUT_GUARDS.map((guard) => [guard, at(filePath, LAYOUT_GUARDS[guard].code())] as const);
    it.each(layout)("%s 按所在 override 生效或放宽", (guard, key) => {
      const reported = guardReports(key).some((m) => m.includes(LAYOUT_GUARDS[guard].message));
      expect(reported).toBe(LAYOUT_ENFORCED[filePath].includes(guard));
    });

    const api = ALL_API_GUARDS.map((guard) => [guard, at(filePath, API_GUARDS[guard].code())] as const);
    it.each(api)("%s 按所在 override 生效或放宽", (guard, key) => {
      const reported = guardReports(key).some((m) => m.includes(API_GUARDS[guard].message));
      expect(reported).toBe(API_ENFORCED[filePath].includes(guard));
    });

    const refreshWithOnError = at(filePath, REFRESH_WITH_ON_ERROR());
    it("传 onError 的 refreshProject 调用放行", () => {
      expect(guardReports(refreshWithOnError)).toEqual([]);
    });
  });

  const textareaInSource = at("src/lint-fixture/Fixture.tsx", RAW_TEXTAREA);
  const textareaInPrimitive = at("src/components/ui/fixture.tsx", RAW_TEXTAREA);
  it("原生 textarea 只在原语目录放行", () => {
    expect(guardReports(textareaInSource)).toEqual([
      expect.stringContaining("多行输入用 components/ui/textarea 的 Textarea"),
    ]);
    expect(guardReports(textareaInPrimitive)).toEqual([]);
  });

  it("原语目录不得依赖业务模块", () => {
    const restricted = UI_IMPORTS.flatMap((_, index) =>
      reportsAt(`${UI_IMPORTS_FIXTURE}:${index + 1}`).some((r) => r.rule === "eslint/no-restricted-imports")
        ? [index + 1]
        : [],
    );
    expect(restricted).toEqual([1, 2, 3, 7, 8, 9, 10, 11]);
  });

  const testFileClasses = at(
    "src/lint-fixture/Fixture.test.tsx",
    `it("x", () => { expect(cn("bg-red-500 h-screen fixed inset-0 md:grid overflow-y-auto motion-safe:animate-spin")).toBeTruthy(); });`,
  );
  it("测试文件不受布局守卫、类名守卫与 @shadcn/lint 约束", () => {
    expect(
      reportsAt(testFileClasses).filter((r) => r.rule.startsWith("arcreel/") || r.rule.startsWith("shadcn/")),
    ).toEqual([]);
  });

  it("补过 relative 的滚动容器零报告", () => {
    const guards = [...reports].flatMap(([key, list]) =>
      REAL_SCROLL_FILES.some((filePath) => key.startsWith(`${filePath}:`))
        ? list.filter((r) => r.rule.startsWith("arcreel/")).map((r) => `${key} ${r.message}`)
        : [],
    );
    expect(guards).toEqual([]);
  });
});

// 上面的夹具绕开了 vite.config.ts：这里确认 vp lint 在 frontend/ 读到的正是 lintConfig，且开着类型感知。
// 类型感知没开时，Oxlint 直接跳过 no-floating-promises 等规则，不报错也不提示。
describe("vite.config.ts 的 lint 块", () => {
  it("接入 lintConfig 并开启类型感知", async () => {
    const printed = JSON.parse(await vp(FRONTEND, ["lint", "--print-config"])) as {
      options?: { typeAware?: boolean };
      jsPlugins?: unknown[];
      overrides?: unknown[];
    };
    expect(printed.options?.typeAware).toBe(true);
    const plugins = (list: readonly unknown[] = []) => list.map((entry) => JSON.stringify(entry)).sort();
    expect(plugins(printed.jsPlugins)).toEqual(plugins(lintConfig.jsPlugins));
    expect(printed.overrides).toHaveLength(lintConfig.overrides.length);
  }, 30_000);
});
