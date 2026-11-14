---
status: accepted
---

# 项目迁移链从 schema 19 接起，更早的项目拒绝并请用户先在上游升级

> 「后果」中「数据根布局迁移仍认得后者」一句已由 `docs/adr/0132` 取代：数据根布局迁移已删除，`.<项目名>.v6-*` 目录不再有代码认得。

项目迁移链原先从 v0 一路接到当前版本：二十步迁移器，加上只为其中几步服务的产物补录、旧媒体来源补写、目录交换与按数据库记录抬高集号高水位，以及规划器里只在迁移途中才走的各版本口径分支（不记风格描述、记资产名、带转场的呈现依据、旧配音抬升视频时长档位）。本项目从未发布过需要原地升级的实例；用户手里的旧项目都来自上游 ArcReel，上游在 2026-10-26 到达 v19、2026-11-11 到达 v20。为一份不会再出现的数据保留这些代码，每次改规划器都要顺带照顾十几种迁移期口径，维护成本远高于它的价值。

## 规则

**链的起点是 v19**：`lib/project/project_schema.py` 的 `MINIMUM_PROJECT_SCHEMA_VERSION = 19`。迁移链只有 v19→v20 一步，链首规整（ADR 0098）只留 v19、v20 数据仍可能带着的形态：剧本顶层集号缺失或不符、资产名归一后重名、资产图与参考文件指向别的资产名下的文件、条目 id 缺失或重复与跨集同号。

**更早的项目被拒，迁移不改写它的文件**：`schema_version` 早于 19 的项目，包括缺这个字段读作 v0 的项目，由 `migrate_project_dir` 在读出版本后、链首规整与任何备份之前以 `schema_unsupported_error`（`ProjectMigrationError`，`file="project.json"`，码 `project_schema_unsupported`，参数 `version`、`minimum`）拒绝；源文件编码迁移同样跳过它，不写 `.arcreel/` 标记。启动期与整项目恢复只在项目目录里写一份失败裁决 `.migration_failure.json`（带 `failed_at`、`code` 与 `params`），错误原文另记进数据根的迁移错误日志，然后继续处理其他项目。这类项目按 `project_schema_unsupported` 阻断，不按 `project_migration_failed`：制作状态的下一步是 `upgrade_project_upstream`，界面与 Agent 都只提示先在上游 ArcReel 升级、导出再导入，不给修复与重试；裁决里没有 `code` 的存量记录照旧读作 `project_migration_failed`。回收站里单个对象的恢复走原有的降级恢复。归档导入在解包之后、修复与编码迁移之前预检，以 `arch_project_schema_unsupported`（参数 `version`、`minimum`）返回 400，提示先在上游 ArcReel 打开项目，升级到 v19 或更高后重新导出。

**新建项目第一次写盘就带当前版本**：`ProjectManager.create_project` 写出的最小 `project.json` 带 `schema_version`，补完元数据之前进程退出也不会留下一个被读作 v0、继而被拒的项目。

**规划口径折成常量**：只服务 v19 之前项目的口径分支删去，依据只按当前口径投影。删分支前后对当前 schema 项目规划一次，依据摘要逐条不变（`tests/integration/lib/artifacts/test_planner_basis_digest_guard.py`）。缺口规则（ADR 0098）借用 v17、v18 表达「缺口即不登记」与「缺口记为缺席」两种口径，仍然保留。

**已发版的报告码保留**：迁移报告里已删规整项的调整码（如 `duplicate_episode_entry_removed`、`script_binding_canonicalized`）仍在 `MigrationAdjustmentCode` 里，存量报告照常读出与显示。

## 后果

- 上游 v19、v20 的项目照常导入与原地升级；更早的项目要先在上游升级一次。
- 迁移链、规划器与归档导入少了大量只在迁移途中才走的分支，改规划器时不再需要核对各版本口径。
- 旧版迁移链在 `project.json`、`versions/versions.json`、`.arcreel_artifacts.json`、绑定的剧本与当前文件名的脚本规划草稿、剪辑时间线（`edit_timelines/episode_*/*.json`）旁留下的 `*.bak.v<N>-*` 备份仍按原有保留期回收。不再自动清理的有：草稿改名前旧文件名的备份、v0→v1 留下的 `clues.bak.v0-*` 目录、旧版目录交换留下的 `.<项目名>.v6-*` 目录；数据根布局迁移仍认得后者。
- 取代 `docs/adr/0075`；收窄 `docs/adr/0022`、`docs/adr/0098`、`docs/adr/0106` 里讲具体迁移步的部分。
