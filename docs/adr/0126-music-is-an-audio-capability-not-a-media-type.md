---
status: accepted
---

# 音乐是音频类型的一种能力，不是新的媒体类型

剪辑时要能用 AI 生成 BGM。媒体类型（`text` / `image` / `video` / `audio`）是封闭集合，往下扇出到目录、设定、解析、佇列容量、资料表栏位、计费与用量页面，新增一种要动四十多处并做资料库迁移。决定如下。

**音乐留在 `audio`，以能力区分**：`AudioFacts` 记 `text_to_speech` / `text_to_music` / `text_to_sfx` 与 `max_seconds`，三项都没写的条目是配音，上游既有的 TTS 条目不用改。`ModelCapability` 新增 `text_to_music`、`text_to_sfx`。设定键 `default_music_backend`（全域）与 `music_backend`（专案）的媒体类型都是 `audio`，`MODEL_SETTING_CAPABILITIES` 记下它们要求的能力：写入校验与 `/system/config` 的选单都按能力过滤，配音选单不出现音乐模型，反过来也一样。

**音乐不自动推断**：按媒体类型挑的预设模型分不出用途（音频的预设是配音），所以音乐键位不自动挑，没设定就请使用者去设定。

**后端与计价**：音乐后端（`lib/backends/music_backends/`）吃提示词与长度，与配音的「文字＋音色」分开；端点 `gemini-lyria`、`stability-audio`、`elevenlabs-music`。计量沿用 `requests`（按次）与 `output_seconds`（扩到音频，按秒）；记账仍是 `call_type="audio"`，由调用端按用量契约上报。

**佇列**：任务类型 `music`，共用音频 lane；入队时就解析好模型与连线并冻结在 payload，佇列投影与执行按任务类型分流，音乐任务不占配音供应商的名额。

**产物**：生成结果走与上传相同的 BGM 登记（统一到 −16 LUFS、按字节登记），`BgmTrack.source` 记 `ai` 与提示词、模型；上传的条目不写这些栏位。

**目录条目**：上游目录没有这些音乐模型，条目写在 `lib/catalog/fork_providers.py`，Lyria 追加到上游的 AI Studio 清单，不取代它。

**ElevenLabs 音乐**：它的条款禁止把音乐模型提供给第三方平台使用（Model Resale）。自己部署、自己的金钥给自己团队用不受影响；对外开放前要先取得授权，供应商说明里写了这一点。
