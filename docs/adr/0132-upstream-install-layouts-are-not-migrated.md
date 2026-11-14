---
status: accepted
---

# 不迁移上游 ArcReel 的安装布局与旧配置，数据根与数据库只按当前形态读写

启动时原先有一组只为上游 ArcReel 旧安装准备的兼容步骤：把平铺的数据根整理进 `projects/` 等分层目录（连同会话键、全局资产、Vertex 凭据、费用记录与排队任务的改写），把旧默认库 `.arcreel.db`（连同 `-wal` / `-shm`）改名为 `arcreel.db`，把代码目录下的 `logs/` 并入数据根，把旧版 `.system_config.json` 导入数据库，把旧任务级文本键改写成档位键；文本任务判同时还忽略旧载荷里的 `projects_root`，费用统计把旧的 `clues/` 输出路径归到道具。本项目从未部署过，数据库只有一份基线迁移（`alembic/versions/0001baseline_baseline.py`），上游的数据库接不上来；项目又只从 schema 19 接起（ADR 0131）。这些步骤要处理的数据在任何一份本项目的安装里都不会出现，却让每次启动多跑一遍检查，也让数据根布局、日志与配置相关的改动都得顺带照顾旧形态。

## 规则

**数据根只认当前布局**：`lib/infra/data_root_layout.py` 的 `DataRootLayout` 给出的位置就是唯一的位置，启动时不检查、不搬动旧布局的条目，也不写布局迁移完成标记。默认 SQLite 只用 `arcreel.db`，日志只写数据根下的 `logs/`，系统配置只在数据库里。

**上游的数据只经项目归档进来**：上游 ArcReel 的项目在上游升级到 schema 19 或更高后导出归档，再在本项目导入（ADR 0131 的归档预检照常适用）；供应商配置与凭据在设置页重新填写。

**全新数据根照常起来**：空的数据根首次启动时写出签名密钥、建出默认管理员与初始密码文件、把日志写到数据根的 `logs/` 下（`tests/unit/server/test_app_startup_migration.py` 的 `test_fresh_empty_data_root_starts_cleanly`）。

## 后果

- 删去 `lib/infra/data_root_layout_migration.py`、目录交换中间目录的命名约定（`staged_swap.py`）、`lib/config/migration.py`、`SystemConfigManager` 及只为它们存在的路径属性与测试。
- 若有人把上游的数据根直接挂上来，平铺在顶层的项目不会显示，旧名数据库不会被使用；部署文档「从上游 ArcReel 迁入」一节说明改走归档导入。
- `.<项目名>.v6-*` 目录（ADR 0131 提到的旧版目录交换遗留）不再有代码认得；它们只可能出现在上游的数据根里。
- 收窄 `docs/adr/0088` 里「原地嵌套、升级不改部署配置」所隐含的旧布局迁移，以及 `docs/adr/0131` 里「数据根布局迁移仍认得后者」一句。
