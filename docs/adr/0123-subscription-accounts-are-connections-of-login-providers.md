---
status: accepted
---

# 订阅账号是登录型供应商的连线

Claude、ChatGPT、Grok 的订阅账号要能在网页登录、每家多个账号，并且像其他连线一样在各处指定（ADR 0122）。决定如下。

**订阅是内置供应商，账号是 `provider_credential`**：`PROVIDER_REGISTRY` 新增 `claude-subscription`、`chatgpt-subscription`、`grok-subscription`，`ProviderMeta.login_kind`（`code_paste` / `device_code`）标明连线只能经登录建立。连线中心、默认连线、旁键指定、删除前的引用检查、用量里的 `credential_id` 都直接沿用。另开一张「订阅账号表」会让每个遍历供应商的地方多一层分支。凭证表单的建立与修改对这三家拒收密钥，只能改名。

**目录清单写在代码里**：目录数据（出厂快照与每日官方同步）来自上游 `ArcReel/arcreel-catalog`，同步时整份取新；fork 新增的供应商写进快照会被清掉。三家的清单由 `lib/catalog/fork_providers.py` 叠在出厂快照与官方合成数据上，模型引用目录里的官方条目，倍率为 0。

**文字与图片生成经官方 CLI**：订阅只能经官方客户端使用，所以每次调用跑一轮官方 CLI：Claude 经 Agent SDK（`lib/subscriptions/claude_turn.py`，看图时只开放 `Read` 工具）、ChatGPT 经 `codex app-server`（`codex_turn.py`，结构化输出用 `outputSchema`，生图用 Codex 内置的生图）、Grok 经 `grok agent stdio` 的 ACP（`grok_turn.py`，结构化输出把 JSON Schema 附在提示里）。调用端点 `claude-subscription-chat`、`codex-chat`、`codex-image`、`grok-cli-chat` 只在订阅凭证下成立。

**凭证放哪**：Claude 的 `setup-token` 一年期令牌不刷新，存在 `api_key`。Codex 与 Grok 的凭证会被 CLI 刷新，放在连线专属的 HOME（`DataRootLayout.subscription_home`），用这条连线的进程都以它为 HOME，让 CLI 原地刷新；数据库不存这两家的凭证，避免多个进程各自复制、各自刷新、互相覆盖。删除连线时一并删除目录。

**登录**：`/providers/{id}/logins` 开始、贴码（Claude）、轮询（device code）、取消，只有管理员能做，可以同时进行多个。登录完成当下就存成连线，不靠页面轮询；同一账号（以账号说明比对）重新登录时更新原连线。

**Agent**：Claude 订阅那一方读 `claude-subscription` 的连线，`agent_subscription_credential_id` 旁键指定用哪一条，没指定用默认连线。订阅会话的用量记在 `claude-subscription` 名下与那条连线的 id，倍率 0。旧的 `claude_subscriptions` 表删除，不搬旧令牌（它没有账号信息）。

**CLI 来源**：Codex 与 Grok CLI 都用官方发布的 Linux 构建，版本与校验和固定，随镜像分发（见 NOTICE）。
