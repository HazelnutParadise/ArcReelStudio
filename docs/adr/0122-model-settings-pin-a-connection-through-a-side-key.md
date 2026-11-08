---
status: accepted
---

# 模型设置以同层旁键指定连线

同一个内置供应商可以存多条凭证（界面称「连线」），每个用到模型的地方要能各自指定用哪一条。决定如下。

**旁键而不是改值格式**：引用模型的字段（全局 `system_settings` 与项目 `project.json` 的 `GLOBAL_MODEL_SETTING_KEYS`、`PROJECT_MODEL_SETTING_KEYS`）值仍是 `provider/model`；旁边加同层的 `<字段>_credential_id` 存凭证 id，没有就用该供应商的默认连线（`provider_credential.is_active`）。改成 `provider@id/model` 要动二十多处自行切分 `provider/model` 的后端代码与前端六处，自定义模型 id 也可能含 `@` 或 `/`；结构化 JSON 则要改全部读写与项目迁移。旁键不动既有解析点，之后「额度用完换连线」可以把旁键扩成清单。

**连线跟着取到模型的那一层**：分层解析（项目桶 > 项目默认 > 全局桶 > 全局默认 > 自动推断）在哪一层取到模型，就读同一层的旁键，不跨层混用。换了供应商又没有重选连线时，写入端把旁键清掉。

**解析结果带连线**：`ProviderModel` 增加 `credential_id`，`pair_key` 不变（按模型分的 `model_settings` 等与连线无关）。`assemble_backend` 与 `provider_config_with_credential` 接受 `credential_id`，指定的连线不存在或不属于该供应商时抛 `CredentialNotFoundError`，不静默改用默认连线；backend 实例缓存的键包含连线。

**已提交的任务不换帐号**：视频提交检查点 schema v6 记录 `credential_id`，续跑用同一条连线轮询；更早的检查点读成默认连线。用量记录 `api_calls.credential_id` 记下实际用的连线（含默认连线），是历史快照，不设外键。

**删除被指定的连线要确认**：删除前列出指定它的全局设置与项目（`GET .../credentials/{id}/references`），未带 `force` 时回 409；确认后把那些旁键清掉，改用默认连线。

**不在范围内**：并发上限仍按供应商计，不按连线；自定义供应商的凭证在供应商本身，没有可选的连线；Agent 的凭证另有一套，随 Agent 引擎改造一并处理。
