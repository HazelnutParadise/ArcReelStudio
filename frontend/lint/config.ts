// 前端 lint 配置：vite.config.ts 的 lint 块（vp lint，即 Oxlint）。规则集按来源分组逐条列出：
// eslint:recommended、typescript-eslint recommended-type-checked、react recommended + jsx-runtime、
// react-hooks recommended、jsx-a11y recommended 与测试三件套，外加 @shadcn/lint 和 lint/arcreel-plugin.ts 的本仓守卫。
// Oxlint 没有内置实现、或内置实现与上游不一致的规则，经 JS 插件加载上游 ESLint 插件（见 jsPlugins）。
// 默认类别（correctness）关闭，只跑这里列出的规则；带选项的规则写明选项，部分规则的 Oxlint 默认值与上游不同。
// website/eslint.config.mjs 用 ESLint 维护同源的规则集，改动共有规则时两份配置各自同步。
import type { OxlintConfig } from "vite-plus/lint";

type Rules = NonNullable<OxlintConfig["rules"]>;

const TEST_FILES = ["src/**/*.test.{ts,tsx}"];
const UI_PRIMITIVES = ["src/components/ui/**"];

// 业务组件中确需按视口断点切换的文件（如外壳切换标准档与紧凑档、弹层宽度），逐个登记。
const VIEWPORT_BREAKPOINT_ALLOWLIST = [
  // 外壳按 xl 切换标准档与紧凑档：侧栏宽度、内容内边距与顶栏右侧留白
  "src/components/shared/page-shell/PageShell.tsx",
  "src/components/shared/page-shell/PageHeader.tsx",
  "src/components/shared/page-shell/PageSidebar.tsx",
];

// eslint:recommended，按 typescript-eslint 对 TS 文件的调整取舍（no-undef 等交给 tsc，no-var、prefer-const 等开启）。
// no-array-constructor、no-unused-expressions、no-unused-vars 在 Oxlint 里直接识别 TS 语法，取代 typescript-eslint 的同名扩展规则。
// no-octal 未移植：ES 模块即严格模式，八进制字面量已是语法错误。
const ESLINT_RECOMMENDED = {
  "no-array-constructor": "error",
  "no-unused-expressions": "error",
  "no-unused-vars": [
    "error",
    {
      varsIgnorePattern: "^_",
      argsIgnorePattern: "^_",
      caughtErrorsIgnorePattern: "^_",
      destructuredArrayIgnorePattern: "^_",
    },
  ],
  "for-direction": "error",
  "no-async-promise-executor": "error",
  "no-case-declarations": "error",
  "no-compare-neg-zero": "error",
  "no-cond-assign": ["error", "except-parens"],
  "no-constant-binary-expression": ["error", { checkRelationalComparisons: false }],
  "no-constant-condition": "error",
  "no-control-regex": "error",
  "no-debugger": "error",
  "no-delete-var": "error",
  "no-dupe-else-if": "error",
  "no-duplicate-case": "error",
  "no-empty": "error",
  "no-empty-character-class": "error",
  "no-empty-pattern": "error",
  "no-empty-static-block": "error",
  "no-ex-assign": "error",
  "no-extra-boolean-cast": "error",
  "no-fallthrough": "error",
  "no-global-assign": "error",
  "no-invalid-regexp": "error",
  "no-irregular-whitespace": [
    "error",
    { skipComments: false, skipJSXText: false, skipRegExps: false, skipStrings: true, skipTemplates: false },
  ],
  "no-loss-of-precision": "error",
  "no-misleading-character-class": "error",
  "no-nonoctal-decimal-escape": "error",
  "no-prototype-builtins": "error",
  "no-regex-spaces": "error",
  "no-self-assign": "error",
  "no-shadow-restricted-names": "error",
  "no-sparse-arrays": "error",
  "no-unassigned-vars": "error",
  "no-unexpected-multiline": "error",
  "no-unsafe-finally": "error",
  "no-unsafe-optional-chaining": "error",
  "no-unused-labels": "error",
  "no-unused-private-class-members": "error",
  "no-useless-assignment": "error",
  "no-useless-backreference": "error",
  "no-useless-catch": "error",
  "no-useless-escape": "error",
  "no-var": "error",
  "prefer-const": ["error", { destructuring: "any", ignoreReadBeforeAssign: false }],
  "prefer-rest-params": "error",
  "prefer-spread": "error",
  "preserve-caught-error": "error",
  "require-yield": "error",
  "use-isnan": "error",
  "valid-typeof": "error",
} satisfies Rules;

// typescript-eslint recommended 中不需要类型信息的部分。
const TYPESCRIPT_RECOMMENDED = {
  "typescript/ban-ts-comment": "error",
  "typescript/no-duplicate-enum-values": "error",
  "typescript/no-empty-object-type": "error",
  "typescript/no-explicit-any": "error",
  "typescript/no-extra-non-null-assertion": "error",
  "typescript/no-misused-new": "error",
  "typescript/no-namespace": "error",
  "typescript/no-non-null-asserted-optional-chain": "error",
  "typescript/no-require-imports": "error",
  "typescript/no-this-alias": "error",
  "typescript/no-unnecessary-type-constraint": "error",
  "typescript/no-unsafe-declaration-merging": "error",
  "typescript/no-unsafe-function-type": "error",
  "typescript/no-wrapper-object-types": "error",
  "typescript/prefer-as-const": "error",
  "typescript/prefer-namespace-keyword": "error",
  "typescript/triple-slash-reference": "error",
} satisfies Rules;

// typescript-eslint recommended-type-checked 新增的类型感知规则（tsgolint 提供类型信息）。测试文件整组关闭。
const TYPESCRIPT_TYPE_CHECKED = {
  "typescript/await-thenable": "error",
  "typescript/no-array-delete": "error",
  "typescript/no-base-to-string": "error",
  "typescript/no-duplicate-type-constituents": "error",
  "typescript/no-floating-promises": "error",
  "typescript/no-for-in-array": "error",
  "typescript/no-implied-eval": "error",
  "typescript/no-misused-promises": "error",
  "typescript/no-redundant-type-constituents": "error",
  "typescript/no-unnecessary-type-assertion": "error",
  "typescript/no-unsafe-argument": "error",
  "typescript/no-unsafe-assignment": "error",
  "typescript/no-unsafe-call": "error",
  "typescript/no-unsafe-enum-comparison": "error",
  "typescript/no-unsafe-member-access": "error",
  "typescript/no-unsafe-return": "error",
  "typescript/no-unsafe-unary-minus": "error",
  "typescript/only-throw-error": "error",
  "typescript/prefer-promise-reject-errors": "error",
  "typescript/require-await": "error",
  "typescript/restrict-plus-operands": "error",
  "typescript/restrict-template-expressions": "error",
  "typescript/unbound-method": "error",
} satisfies Rules;

// eslint-plugin-react recommended + jsx-runtime。不含 prop-types（TypeScript 已检查 props）与
// jsx-uses-vars（no-unused-vars 已识别 JSX 引用）。Oxlint 没有 no-deprecated：React 19 已移除的顶层 API 过不了 tsc，
// 已废弃的类组件生命周期方法（componentWillMount 等）仍在 @types/react 里，由 no-unsafe 的 checkAliases 报出。
const REACT_RECOMMENDED = {
  "react/display-name": "error",
  "react/jsx-key": "error",
  "react/jsx-no-comment-textnodes": "error",
  "react/jsx-no-duplicate-props": "error",
  "react/jsx-no-target-blank": "error",
  "react/jsx-no-undef": "error",
  "react/no-children-prop": "error",
  "react/no-danger-with-children": "error",
  "react/no-direct-mutation-state": "error",
  "react/no-find-dom-node": "error",
  "react/no-is-mounted": "error",
  "react/no-render-return-value": "error",
  "react/no-string-refs": "error",
  "react/no-unescaped-entities": "error",
  "react/no-unknown-property": "error",
  "react/require-render-return": "error",
  "react/no-unsafe": ["error", { checkAliases: true }],
} satisfies Rules;

// eslint-plugin-react-hooks recommended。本项目严于 recommended：exhaustive-deps、incompatible-library 一律视为 error。
// rules-of-hooks 与 exhaustive-deps 用 Oxlint 内置实现（规则名 react/，行内豁免仍写 react-hooks/exhaustive-deps）；
// React Compiler 诊断用官方插件经 JS 插件加载（别名 react-hooks-js，Oxlint 保留了 react-hooks 这个名字），
// 行内豁免写 react-hooks-js/set-state-in-effect 等。Oxlint 1.91 内置的 Compiler 诊断与官方实现不一致：
// effect 内局部变量在清理函数、异步回调里重新赋值会被 immutability 误报，部分 set-state-in-effect 又漏报。
const REACT_HOOKS_RECOMMENDED = {
  "react/rules-of-hooks": "error",
  "react/exhaustive-deps": "error",
  "react-hooks-js/config": "error",
  "react-hooks-js/error-boundaries": "error",
  "react-hooks-js/gating": "error",
  "react-hooks-js/globals": "error",
  "react-hooks-js/immutability": "error",
  "react-hooks-js/incompatible-library": "error",
  "react-hooks-js/preserve-manual-memoization": "error",
  "react-hooks-js/purity": "error",
  "react-hooks-js/refs": "error",
  "react-hooks-js/set-state-in-effect": "error",
  "react-hooks-js/set-state-in-render": "error",
  "react-hooks-js/static-components": "error",
  "react-hooks-js/unsupported-syntax": "warn",
  "react-hooks-js/use-memo": "error",
} satisfies Rules;

// eslint-plugin-jsx-a11y recommended（非 strict），选项照搬 recommended 预设。
const JSX_A11Y_RECOMMENDED = {
  "jsx-a11y/alt-text": "error",
  "jsx-a11y/anchor-has-content": "error",
  "jsx-a11y/anchor-is-valid": "error",
  "jsx-a11y/aria-activedescendant-has-tabindex": "error",
  "jsx-a11y/aria-props": "error",
  "jsx-a11y/aria-proptypes": "error",
  "jsx-a11y/aria-role": "error",
  "jsx-a11y/aria-unsupported-elements": "error",
  "jsx-a11y/autocomplete-valid": "error",
  "jsx-a11y/click-events-have-key-events": "error",
  "jsx-a11y/heading-has-content": "error",
  "jsx-a11y/html-has-lang": "error",
  "jsx-a11y/iframe-has-title": "error",
  "jsx-a11y/img-redundant-alt": "error",
  "jsx-a11y/interactive-supports-focus": [
    "error",
    { tabbable: ["button", "checkbox", "link", "searchbox", "spinbutton", "switch", "textbox"] },
  ],
  "jsx-a11y/label-has-associated-control": "error",
  "jsx-a11y/media-has-caption": "error",
  "jsx-a11y/mouse-events-have-key-events": "error",
  "jsx-a11y/no-access-key": "error",
  "jsx-a11y/no-autofocus": "error",
  "jsx-a11y/no-distracting-elements": "error",
  "jsx-a11y/no-interactive-element-to-noninteractive-role": [
    "error",
    { tr: ["none", "presentation"], canvas: ["img"] },
  ],
  "jsx-a11y/no-noninteractive-element-interactions": [
    "error",
    {
      handlers: ["onClick", "onError", "onLoad", "onMouseDown", "onMouseUp", "onKeyPress", "onKeyDown", "onKeyUp"],
      alert: ["onKeyUp", "onKeyDown", "onKeyPress"],
      body: ["onError", "onLoad"],
      dialog: ["onKeyUp", "onKeyDown", "onKeyPress"],
      iframe: ["onError", "onLoad"],
      img: ["onError", "onLoad"],
    },
  ],
  "jsx-a11y/no-noninteractive-element-to-interactive-role": [
    "error",
    {
      ul: ["listbox", "menu", "menubar", "radiogroup", "tablist", "tree", "treegrid"],
      ol: ["listbox", "menu", "menubar", "radiogroup", "tablist", "tree", "treegrid"],
      li: ["menuitem", "menuitemradio", "menuitemcheckbox", "option", "row", "tab", "treeitem"],
      table: ["grid"],
      td: ["gridcell"],
      fieldset: ["radiogroup", "presentation"],
    },
  ],
  "jsx-a11y/no-noninteractive-tabindex": ["error", { tags: [], roles: ["tabpanel"], allowExpressionValues: true }],
  "jsx-a11y/no-redundant-roles": "error",
  "jsx-a11y/no-static-element-interactions": [
    "error",
    {
      allowExpressionValues: true,
      handlers: ["onClick", "onMouseDown", "onMouseUp", "onKeyPress", "onKeyDown", "onKeyUp"],
    },
  ],
  "jsx-a11y/role-has-required-aria-props": "error",
  "jsx-a11y/role-supports-aria-props": "error",
  "jsx-a11y/scope": "error",
  "jsx-a11y/tabindex-no-positive": "error",
} satisfies Rules;

// @vitest/eslint-plugin recommended；`expectXxx(...)` 形态的本地断言辅助函数同样计作断言。
const VITEST_RECOMMENDED = {
  "vitest/expect-expect": ["error", { assertFunctionNames: ["expect", "expect*"] }],
  "vitest/no-commented-out-tests": "error",
  "vitest/no-conditional-expect": "error",
  "vitest/no-disabled-tests": "warn",
  "vitest/no-focused-tests": "error",
  "vitest/no-identical-title": "error",
  "vitest/no-import-node-test": "error",
  "vitest/no-interpolation-in-snapshots": "error",
  "vitest/no-mocks-import": "error",
  "vitest/no-standalone-expect": "error",
  "vitest/no-unneeded-async-expect-function": "error",
  "vitest/prefer-called-exactly-once-with": "error",
  "vitest/require-local-test-context-for-concurrent-snapshots": "error",
  "vitest/valid-describe-callback": "error",
  "vitest/valid-expect": "error",
  "vitest/valid-expect-in-promise": "error",
  "vitest/valid-title": ["error", { ignoreTypeOfDescribeName: false, allowArguments: false, disallowedWords: [] }],
} satisfies Rules;

// eslint-plugin-testing-library flat/react（JS 插件）。
// 预设里另有几条本仓刻意不开：no-node-access、prefer-screen-queries、no-container、render-result-naming-convention、
// no-unnecessary-act、no-manual-cleanup 是存量命中且无自动修的查询/容器风格规则，断言强度归 review；
// prefer-find-by、prefer-presence-queries、no-wait-for-multiple-assertions 的自动修在本仓产出语法错误或改写语义
// （改坏 waitFor 调用、把喂给 `.closest()` 的 getBy 换成可空的 queryBy、把断言搬出 waitFor 回调时丢了作用域）。
const TESTING_LIBRARY_REACT = {
  "testing-library/await-async-events": ["error", { eventModule: "userEvent" }],
  "testing-library/await-async-queries": "error",
  "testing-library/await-async-utils": "error",
  "testing-library/no-await-sync-events": ["error", { eventModules: ["fire-event"] }],
  "testing-library/no-await-sync-queries": "error",
  "testing-library/no-debugging-utils": "warn",
  "testing-library/no-dom-import": ["error", "react"],
  "testing-library/no-global-regexp-flag-in-query": "error",
  "testing-library/no-promise-in-fire-event": "error",
  "testing-library/no-render-in-lifecycle": "error",
  "testing-library/no-wait-for-side-effects": "error",
  "testing-library/no-wait-for-snapshot": "error",
  "testing-library/prefer-query-by-disappearance": "error",
} satisfies Rules;

// eslint-plugin-jest-dom recommended（JS 插件）。
// 不开 prefer-to-have-value：`toHaveAttribute("aria-valuenow", …)` 被判为表单取值断言，自动修会改写语义。
const JEST_DOM_RECOMMENDED = {
  "jest-dom/prefer-checked": "error",
  "jest-dom/prefer-empty": "error",
  "jest-dom/prefer-enabled-disabled": "error",
  "jest-dom/prefer-focus": "error",
  "jest-dom/prefer-in-document": "error",
  "jest-dom/prefer-required": "error",
  "jest-dom/prefer-to-have-attribute": "error",
  "jest-dom/prefer-to-have-class": "error",
  "jest-dom/prefer-to-have-style": "error",
  "jest-dom/prefer-to-have-text-content": "error",
} satisfies Rules;

// 测试文件放宽 any 与 unsafe-*：测试环境允许 mock 便利。
const TEST_LOOSE_TYPES = {
  "typescript/no-explicit-any": "off",
  "typescript/no-unsafe-assignment": "off",
  "typescript/no-unsafe-member-access": "off",
  "typescript/no-unsafe-argument": "off",
  "typescript/no-unsafe-call": "off",
  "typescript/no-unsafe-return": "off",
} satisfies Rules;

// 自身不带任何样式的行为原语：components/ui 里的实现只透传 props，不写 className（InfoTipTrigger 只补 focus-ring）。
// 它们渲染的元素外观由调用处给出，写在 render 元素或 className 上（见 info-tip.tsx 的说明）。
// @shadcn/lint 0.2.2 起把 render 元素上的 class 记到原语名下，按默认契约会误报「原语自带样式」，
// 故为这几个原语单列不限类别的契约。新增条目前先确认该原语在 components/ui 中确实不带样式。
const UNSTYLED_PRIMITIVES = ["Collapsible", "DialogTrigger", "InfoTipTrigger", "PopoverTrigger", "TooltipTrigger"];

// @shadcn/lint 规则：components/ui 内的原语自身负责样式，关闭 restyle、任意值与静态 class 三条（见下方原语块）。
const SHADCN_RULES = {
  "shadcn/no-restyle": [
    "error",
    {
      allow: ["layout"],
      contracts: [{ pattern: `^(${UNSTYLED_PRIMITIVES.join("|")})$`, allow: ["*"] }],
    },
  ],
  "shadcn/no-raw-colors": "error",
  "shadcn/no-arbitrary-values": ["error", { allow: ["layout"] }],
  "shadcn/no-inline-styles": "error",
  "shadcn/require-static-classes": "error",
  "shadcn/no-unknown-classes": "error",
} satisfies Rules;

// API 直调与测试 mock 约束（arcreel 插件），源码与测试文件都受约束：
// - 入队类 API 方法只能经 src/actions/ 的入队动作层调用；新增入队方法时在 api.ts 加 @enqueue 并登记进
//   lint/arcreel-plugin.ts 的 ENQUEUE_METHODS（由 api.enqueue-methods.test.ts 校验一致）。
// - 模型能力只能经 src/hooks/useModelCapabilities 消费。
// - 不得整模块 mock `@/api`（含其 `@/api/*` 子模块）与 `react-i18next`，不得丢弃 refreshProject 的结算值。
// src/api.test.ts 豁免前两条：它测试的是 API 层本体的端点路径与请求体。
const API_GUARDS = {
  "arcreel/no-direct-enqueue": "error",
  "arcreel/no-direct-capabilities": "error",
  "arcreel/no-module-mock": "error",
  "arcreel/no-discarded-refresh": "error",
} satisfies Rules;

// 样式与布局守卫只约束源码，测试文件不受（它们在断言里引用类名而不渲染）。
// 原语目录、视口断点白名单与 ToastOverlay 在下方 overrides 里各关掉自己实现的那几条。
const LAYOUT_GUARDS = {
  "arcreel/no-viewport-height": "error",
  "arcreel/no-fixed-overlay": "error",
  "arcreel/no-scroll-height": "error",
  "arcreel/no-viewport-breakpoint": "error",
  "arcreel/no-raw-textarea": "error",
  "arcreel/no-toast-primitive": "error",
  "arcreel/no-motion-variant": "error",
  "arcreel/no-unpositioned-scroll": "error",
  "arcreel/no-scrollbar-style": "error",
  "arcreel/no-raw-z-index": "error",
  "arcreel/no-backdrop-blur": "error",
  "arcreel/no-raw-motion-token": "error",
} satisfies Rules;

// 测试文件关闭类型感知规则与全部 jsx-a11y 规则（测试用 a11y 反例做断言目标）。
const offAll = (rules: Rules): Rules => Object.fromEntries(Object.keys(rules).map((rule) => [rule, "off"]));

// components/ui/ 只放 shadcn 原语：不依赖 API、store、业务类型与业务组件。
// 不禁用 react-i18next：dialog、sheet、toast、message-scroller 用它取关闭按钮等文案。
const RESTRICT_UI_PRIMITIVE_IMPORTS = {
  // patterns 按顺序匹配，命中某条的 ! 排除项后不再看后面的条目，
  // 故 .. 段那条放在前面，否则 @/components/ui/../ 会被第二条的排除项放过。
  patterns: [
    // 原语目录没有子目录，路径里出现 .. 段就会离开 components/ui；统一走不含 .. 的 @/ 别名，下面的边界才查得到。
    {
      regex: String.raw`(^|/)\.\.(/|$)`,
      message: "components/ui/ 内跨目录导入用不含 .. 的 @/ 别名：带 .. 的路径绕过原语依赖边界的检查。",
    },
    {
      // * 不跨越 /，多级目录写 **。
      group: [
        "@/api",
        "@/api/**",
        "@/stores/**",
        "@/types",
        "@/types/**",
        "@/hooks/**",
        "@/actions/**",
        "@/components/**",
        "!@/components/ui",
        "!@/components/ui/**",
      ],
      message:
        "components/ui/ 只放 shadcn CLI 安装的原语：调用 API、读写 store 或依赖业务类型的组件放进使用它的业务目录，多处共用的放 components/shared/。knip 对 components/ui 的未使用导出整体豁免，业务组件混进来后，它真正未使用的导出也会被放过。",
    },
  ],
};

export const lintConfig = {
  plugins: ["typescript", "react", "jsx-a11y"],
  // 路径相对 vite.config.ts 所在的 frontend/ 解析。
  jsPlugins: [
    { name: "react-hooks-js", specifier: "eslint-plugin-react-hooks" },
    "@shadcn/lint",
    "eslint-plugin-testing-library",
    "eslint-plugin-jest-dom",
    "./lint/arcreel-plugin.ts",
    { name: "vite-plus", specifier: "vite-plus/oxlint-plugin" },
  ],
  categories: { correctness: "off" },
  options: {
    typeAware: true,
    reportUnusedDisableDirectives: "warn",
  },
  ignorePatterns: [
    "dist/**",
    // Playwright 输出的报告与失败产物不属于项目源码。
    "playwright-report/**",
    "test-results/**",
    "coverage/**",
    "node_modules/**",
    "**/*.config.*",
  ],
  rules: {
    // 测试 API 从 vite-plus/test 导入，配置从 vite-plus 导入，不直接依赖 Vite+ 打包的 vitest、vite。
    "vite-plus/prefer-vite-plus-imports": "error",
    ...ESLINT_RECOMMENDED,
    ...TYPESCRIPT_RECOMMENDED,
    ...TYPESCRIPT_TYPE_CHECKED,
    ...REACT_RECOMMENDED,
    ...REACT_HOOKS_RECOMMENDED,
    ...JSX_A11Y_RECOMMENDED,
  },
  overrides: [
    {
      files: ["src/**/*.{ts,tsx}"],
      excludeFiles: TEST_FILES,
      env: { browser: true },
      rules: { ...SHADCN_RULES, ...API_GUARDS, ...LAYOUT_GUARDS },
    },
    {
      files: TEST_FILES,
      env: { browser: true },
      plugins: ["vitest"],
      rules: {
        ...offAll(TYPESCRIPT_TYPE_CHECKED),
        ...offAll(JSX_A11Y_RECOMMENDED),
        ...API_GUARDS,
        ...VITEST_RECOMMENDED,
        ...TESTING_LIBRARY_REACT,
        ...JEST_DOM_RECOMMENDED,
      },
    },
    {
      files: [...TEST_FILES, "src/test/**/*.{ts,tsx}"],
      rules: TEST_LOOSE_TYPES,
    },
    {
      files: ["src/api.test.ts"],
      rules: { "arcreel/no-direct-enqueue": "off", "arcreel/no-direct-capabilities": "off" },
    },
    {
      files: ["src/actions/**/*.{ts,tsx}"],
      excludeFiles: TEST_FILES,
      rules: { "arcreel/no-direct-enqueue": "off" },
    },
    {
      files: ["src/hooks/useModelCapabilities.ts"],
      rules: { "arcreel/no-direct-capabilities": "off" },
    },
    {
      files: ["src/components/layout/ToastOverlay.tsx"],
      rules: { "arcreel/no-toast-primitive": "off" },
    },
    {
      files: VIEWPORT_BREAKPOINT_ALLOWLIST,
      rules: { "arcreel/no-viewport-breakpoint": "off" },
    },
    // 原语自身负责样式与浮层定位：关闭 restyle、任意值与静态 class 三条，放过 fixed inset-0、scrollHeight、视口断点、
    // 原生 textarea、数值层级与原始动效 token（背景模糊不放过）；另禁止依赖业务模块。
    {
      files: UI_PRIMITIVES,
      excludeFiles: TEST_FILES,
      rules: {
        "shadcn/no-restyle": "off",
        "shadcn/no-arbitrary-values": "off",
        "shadcn/require-static-classes": "off",
        "arcreel/no-fixed-overlay": "off",
        "arcreel/no-scroll-height": "off",
        "arcreel/no-viewport-breakpoint": "off",
        "arcreel/no-raw-textarea": "off",
        "arcreel/no-raw-z-index": "off",
        "arcreel/no-raw-motion-token": "off",
        "no-restricted-imports": ["error", RESTRICT_UI_PRIMITIVE_IMPORTS],
      },
    },
    // 页面级套件与录制脚本：类型信息取自 e2e/tsconfig.json。
    {
      files: ["e2e/**/*.ts"],
      env: { browser: true, node: true },
    },
    {
      files: ["e2e/regions/**/*.ts"],
      rules: { "arcreel/no-animation-wait": "error" },
    },
  ],
} satisfies OxlintConfig;
