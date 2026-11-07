# 新增与升级依赖

1. **用包管理器写入。** 后端 `uv add <包>`（dev 依赖加 `--group dev`），前端与文档站在各自目录 `pnpm add <包>`。版本号与 lockfile 由包管理器写入，不在 `pyproject.toml` / `package.json` 中手写。
2. **归入 Dependabot 分组。** 在 `.github/dependabot.yml` 对应生态的 `groups` 里把新包加进语义最接近的分组。`all-other` 只收未归类的包，不能当作新包的分组；`uv run python scripts/audit_conventions.py --check` 会列出只命中 `all-other` 的直接依赖。
3. **跑依赖卫生检查。** `uv run deptry lib server alembic scripts tests`；改了子包时另在该子包目录（`packages/arcreel-market-core/`、`packages/arcreel-catalog-core/`）跑 `uv run deptry src tests`。直接 import 的第三方包必须声明（`DEP003`），声明了却没有 import 的包要删除或登记为运行时插件（`DEP002`）。

## 已知版本约束

- **前端 TypeScript 受 `typescript-eslint` 的 peer 范围限制。** 升级 TypeScript 前先核对锁定版本的 `typescript-eslint` peer 范围，必要时同步升级。
- **文档站 TypeScript 上限是 6.x。** 原因与解锁条件写在 `.github/dependabot.yml` 的 website 段注释里。
- **后端 HTTP 客户端统一用 `httpx2`。** 仓库代码直接 `import httpx2`，不 import `httpx`。`lib/__init__.py`、`server/__init__.py`、`tests/conftest.py` 与 `packages/arcreel-market-core/tests/conftest.py` 在任何 `import httpx` 之前调用 `httpx2.alias_httpx()`，让仍按 `httpx` 编写的依赖（方舟 SDK `volcengine-ark-runtime`、respx）拿到同一套 `httpx2` 的类：这些 SDK 因此接受 `httpx2` 客户端，路径覆盖的 transport 层只实现 `httpx2` 一份，respx（`tests/http_capture.py`）拦截的也是 `httpx2` 发出的请求。respx 的 pytest 插件在加载 conftest 之前就 import `httpx`，主仓与子包的 pytest 配置都用 `-p no:respx` 禁止它自动加载。新增会在导入期 import `httpx` 的 pytest 插件或进程入口时，要保证 `alias_httpx()` 先执行，否则它抛出 `RuntimeError`。
- **`openai` 受 `instructor` 的 `jiter` 上限限制。** `openai` 3.4.0 起要求 `jiter>=0.16`，`instructor` 1.17.0 要求 `jiter<0.15`，`uv lock --upgrade` 因此停在 `openai` 3.3.0。解锁条件：`instructor` 放宽 `jiter` 上限。
- **Gemini Developer API 客户端固定 `api_version="v1beta"`。** `google-genai` 3.x 缺省 `v1`，`v1` 不支持语音输出（Speech Config），Python 端点的默认路径与路径覆盖也按 `/v1beta` 书写（`lib/custom_provider/endpoints.py`）。新建 AI Studio 客户端时用 `lib/backends/gemini_shared.py` 的 `gemini_http_options` 或 `GEMINI_DEVELOPER_API_VERSION`，Vertex 客户端沿用 SDK 缺省。3.x 在 API Key 模式下拒绝提交 Veo 任务，`lib/backends/video_backends/gemini.py` 把它转成能力错误 `video_veo_api_key_mode_unsupported`，已提交任务的续跑不受影响。
- **`imageio-ffmpeg` 锁在 0.7.x。** 0.8 起随包 FFmpeg 9，它的 mov 解复用器把 `stts` 的解码间隔作为包时长。带 B 帧的可变帧率视频里，pts 最大的那一包的时长不是它的显示时长，`lib/infra/media_probe.py` 按「pts + 包时长」算出的流时长会超出容器声明的时长（`tests/integration/lib/infra/test_media_probe.py` 的 `test_silent_vfr_reports_presentation_packet_span`）。解锁条件：探测改用不依赖逐包时长的算法，并同步更新 `NOTICE` 的随包构建说明。
- **`pyproject.toml` 与 `frontend/package.json` 的 `version` 字段由 release-please 维护**，视为只读。
- **pnpm 设置写在 `frontend/`、`website/` 各自的 `pnpm-workspace.yaml`。** pnpm 12 不读 `package.json` 的 `pnpm` 字段，`overrides` 与 `allowBuilds` 都写在 `pnpm-workspace.yaml`。新依赖带构建脚本时，安装报 `ERR_PNPM_IGNORED_BUILDS`，在 `allowBuilds` 里写明该包允许执行（`true`）或不执行（`false`）。pnpm 默认不安装发布未满 1 天的版本（`minimumReleaseAge`），刚发布的版本要等满 1 天再升级。
- **shadcn 原语随依赖升级。** Dependabot 只升级 npm 包，不会重新生成 `frontend/src/components/ui/*.tsx`。`@base-ui/react` 与 `shadcn` 的 minor、patch 升级归入 `shadcn-stack` 分组；major 升级单独开 PR，在同一个 PR 中对已安装组件逐个运行 `pnpm exec shadcn add <组件> --diff`，手动合并上游改动，保留带注释说明的本地改动。遇到原语缺陷时，先用 `add --diff` 确认上游是否已经修复。

- **供应商图标只使用 `@lobehub/icons/es/*/components/{Color,Mono}` 的独立 SVG 入口。** `frontend/pnpm-workspace.yaml` 的定向 override 排除该包的 `@lobehub/ui` peer；这些入口只依赖 React，不使用其 UI 组件，避免自动引入另一套 UI 与动效依赖。若改用 Avatar、组合入口或其他依赖 `@lobehub/ui` 的组件，先复核此约束。
