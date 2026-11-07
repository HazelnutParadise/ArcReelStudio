// 本仓的架构与样式守卫，由 vite.config.ts 的 lint.jsPlugins 加载（Oxlint JS 插件，规则名前缀 arcreel/）。
// 每条约束是一条独立规则，生效范围与豁免在 lint/config.ts 的 overrides 里按文件开关；
// 选择器写法与 ESLint 的 no-restricted-syntax 相同（esquery）。
import { definePlugin, defineRule, type Node } from "vite-plus/lint/plugins";

// 入队类 API 方法清单（按字母序）。新增入队方法时在 api.ts 的方法上加 JSDoc @enqueue，并在此加一行；
// api.enqueue-methods.test.ts 校验两边集合一致，漏登记会让该测试失败。
export const ENQUEUE_METHODS = [
  "authorPrompts",
  "continueEpisodeReplan",
  "editImage",
  "exportJianyingDraft",
  "generateAdScript",
  "generateCharacter",
  "generateCharacterDerivative",
  "generateCharacterVoiceSample",
  "generateEpisodeNarrationAudio",
  "generateGrid",
  "generateNarrationAudio",
  "generateProjectProduct",
  "generateProjectProp",
  "generateProjectScene",
  "generateReferenceVideoBatch",
  "generateReferenceVideoUnit",
  "generateStoryboard",
  "generateVideo",
  "planEpisodes",
  "planScript",
  "regenerateGrid",
  "renderFinalCut",
  "repairEpisodeDraft",
  "startEpisodeReplan",
  "submitAssetSheetBatch",
  "submitStoryboardBatch",
];

// 命中任一选择器即按 message 报告。
const selectorRule = (selectors: string[], message: string) =>
  defineRule({
    meta: { type: "problem", schema: [] },
    create(context) {
      const report = (node: Node) => context.report({ node, message });
      return Object.fromEntries(selectors.map((selector) => [selector, report]));
    },
  });

// 字符串字面量与模板片段里的 class 守卫；先匹配含该 token 的字符串，再由 message 说明替代写法。
const classGuard = (pattern: string, message: string) =>
  selectorRule([`Literal[value=${pattern}]`, `TemplateElement[value.raw=${pattern}]`], message);

// projects-store 的 refreshProject 以结算值报告失败而不 reject，丢弃返回值就没人提示刷新失败：
// 写入已生效，界面却停在旧数据上。写入后的刷新经 canvas/shared/refreshAfterWrite；
// 加载与同步路径传 onError，或消费结算值。
const REFRESH_PROJECT_CALL =
  "CallExpression[callee.property.name='refreshProject']:not(:has(Property[key.name='onError']))";

// 滚动容器须是定位元素，且定位类与 overflow 类写在同一个字符串里（守卫按单个字符串判断）。
const SCROLL_CLASS = String.raw`/(^|[\s:])overflow-(x-|y-)?(auto|scroll)(?![\w-])/`;
const POSITIONED_CLASS = String.raw`/(^|[\s:])(relative|absolute|fixed|sticky)(?![\w-])/`;

const FIXED_OVERLAY_MESSAGE = "禁止手写 fixed inset-0 浮层：改用 components/ui 的 Dialog、Sheet 等原语。";

export default definePlugin({
  meta: { name: "arcreel" },
  rules: {
    // 入队类 API 方法只能经 src/actions/ 的入队动作层调用：乐观占用打标、去重提示与返回值归一化由动作层统一封装。
    "no-direct-enqueue": selectorRule(
      [`CallExpression[callee.object.name='API'][callee.property.name=/^(${ENQUEUE_METHODS.join("|")})$/]`],
      "入队类 API 方法只能经 src/actions/ 的入队动作层调用（统一封装乐观占用打标与去重提示）。",
    ),
    // 各能力维度的真相源、失效时机与「未知不谎报不支持」的降级规则都收在 useModelCapabilities。
    "no-direct-capabilities": selectorRule(
      ["CallExpression[callee.object.name='API'][callee.property.name='getVideoCapabilities']"],
      "模型能力只能经 useModelCapabilities 消费（单一真相源 + 统一失效时机）。",
    ),
    "no-module-mock": selectorRule(
      [
        "CallExpression[callee.object.name='vi'][callee.property.name='mock'][arguments.0.value=/^(@\\/api(\\/.+)?|react-i18next)$/]",
      ],
      "禁止整模块 mock：API 打桩用 vi.spyOn(API, method)；i18n 用全局 setup 已加载的真实中文资源（整体 mock 后翻译缺失无法被发现）。",
    ),
    "no-discarded-refresh": selectorRule(
      [
        `ExpressionStatement > ${REFRESH_PROJECT_CALL}`,
        `ExpressionStatement > AwaitExpression > ${REFRESH_PROJECT_CALL}`,
        `UnaryExpression[operator='void'] > ${REFRESH_PROJECT_CALL}`,
      ],
      "不要丢弃 refreshProject 的结算值：写入后的刷新改用 canvas/shared/refreshAfterWrite，加载与同步路径传 onError 或按结算值处理。",
    ),

    // 样式与布局守卫。
    "no-viewport-height": classGuard(
      String.raw`/(^|[\s:])(min-|max-)?h-screen(?![\w-])|100vh/`,
      "禁止视口高度（h-screen、min-h-screen、max-h-screen、100vh）：高度由外壳的滚动契约分配，组件用 flex / grid 与 min-h-0 取得剩余空间。",
    ),
    "no-fixed-overlay": selectorRule(
      [
        String.raw`Literal[value=/(^|\s)fixed(\s|$)/][value=/(^|\s)inset-0(\s|$)/]`,
        String.raw`TemplateElement[value.raw=/(^|\s)fixed(\s|$)/][value.raw=/(^|\s)inset-0(\s|$)/]`,
      ],
      FIXED_OVERLAY_MESSAGE,
    ),
    "no-scroll-height": selectorRule(
      ["MemberExpression[property.name='scrollHeight']"],
      "禁止读写 scrollHeight 手动测高：自动撑高用统一的输入框原语，滚动区高度交给布局分配。",
    ),
    // 容器查询变体以 @ 开头（@md:），不在此列。
    "no-viewport-breakpoint": classGuard(
      String.raw`/(^|[\s:])(max-|min-)?(sm|md|lg|xl|2xl|\[[^\]]+\]):/`,
      "业务组件禁用视口断点前缀（sm: / md: / lg: / xl: / 2xl:）：外壳内一律用容器查询（@container 与 @md: 等），确需按视口切换的文件登记进 lint/config.ts 的 VIEWPORT_BREAKPOINT_ALLOWLIST。",
    ),
    "no-raw-textarea": selectorRule(
      ["JSXOpeningElement[name.name='textarea']"],
      "多行输入用 components/ui/textarea 的 Textarea：随内容撑高、超过上限后框内滚动、variant 与 mono 都由原语提供。必须使用原生 textarea 的场景（如与着色镜像层同步滚动的编辑器），行内 eslint-disable-next-line arcreel/no-raw-textarea 并写明理由。",
    ),
    // 匹配导入与转导出，以及别名与相对写法（@/components/ui/toast、../ui/toast）。
    "no-toast-primitive": selectorRule(
      [
        String.raw`:matches(ImportDeclaration, ExportNamedDeclaration, ExportAllDeclaration)[source.value=/(^|\/)ui\/toast$/]`,
      ],
      "全局提示统一用 useAppStore 的 pushToast：ToastOverlay 负责把 store 中的提示按到达顺序转交 Base UI 队列，直接调用 toast.add 会绕过它，也绕过提示、工作区通知与持久告警的分流（见 src/stores/app-store.ts 中 pushToast 的说明）。",
    ),
    // 减少动态效果由 index.css 的全局规则统一处理。
    "no-motion-variant": classGuard(
      String.raw`/(^|[\s:])motion-(safe|reduce):/`,
      "禁用 motion-safe: / motion-reduce: 前缀：减少动态效果由 index.css 的全局规则统一处理，组件直接写动效类。",
    ),
    "no-unpositioned-scroll": selectorRule(
      [
        `Literal[value=${SCROLL_CLASS}]:not([value=${POSITIONED_CLASS}])`,
        `TemplateElement[value.raw=${SCROLL_CLASS}]:not([value.raw=${POSITIONED_CLASS}])`,
      ],
      "滚动容器（overflow-auto、overflow-*-auto、overflow-*-scroll）须是定位元素：在同一个字符串里写 relative（已是 absolute、fixed、sticky 的除外），否则绝对定位的子元素会撑出文档滚动。",
    ),
    // 滚动条样式只在 index.css 定义；scrollbar-gutter 预留槽位，不改样式，不在此列。
    "no-scrollbar-style": classGuard(
      String.raw`/(^|[\s:\[])(no-scrollbar|scrollbar-(?!gutter)[\w-]+)|::-webkit-scrollbar/`,
      "禁止在组件里写滚动条样式（scrollbar-none、no-scrollbar、[scrollbar-width:*]、::-webkit-scrollbar 等）：滚动条始终可见，样式只在 index.css 定义。",
    ),
    // 层级由原语自带的 z-overlay、z-toast、z-onboarding 负责。
    "no-raw-z-index": classGuard(
      String.raw`/(^|[\s:])-?z-(\d+|\[)/`,
      "调用处不写数值层级（z-10、z-[…]）：弹层、提示、引导分别由原语自带的 z-overlay、z-toast、z-onboarding 负责；#app-root 是独立层叠上下文（isolation: isolate），挂在 body 上的 Portal 总在应用之上。应用内吸顶的工具栏用 z-sticky。",
    ),
    // backdrop-blur-0 用于取消模糊，放过。
    "no-backdrop-blur": classGuard(
      String.raw`/(^|[\s:])backdrop-blur(?![\w-]*-0\b)/`,
      "不使用背景模糊（backdrop-blur-*）：弹层遮罩用 bg-scrim，表面用 bg-popover 加 shadow-overlay。半透明表面的文字对比度会随背后画面变化，背景模糊在大面积重绘时开销也大。",
    ),
    "no-raw-motion-token": classGuard(
      String.raw`/(^|[\s:])(duration-\d+|ease-(linear|in|out|in-out))(?![\w-])/`,
      "时长与缓动只用 token：duration-fast（150ms）、duration-base（200ms）、ease-emphasized。动效不超过 300ms；弹层进出场用原语自带的 animate-in、animate-out，持续运行的状态指示用 animate-breath。",
    ),

    // 页面级场景不手写动画等待：Promise.all 等 finished 遇到被取消的过渡会拒绝，等全局动画会被循环动画卡住。
    // 公共入口已在探测前等待入场，场景中途需要等弹层时用 support/region-helpers 的 waitForEntrance。
    "no-animation-wait": selectorRule(
      ["MemberExpression[property.name='getAnimations']"],
      "页面级场景不手写动画等待：用 e2e/support/region-helpers.ts 的 waitForEntrance，或交给 defineRegionScenarios 探测前的统一等待。",
    ),
  },
});
