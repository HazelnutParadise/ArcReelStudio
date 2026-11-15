---
id: text/drama_script_plan
category: text
title: 剧情演绎脚本规划
description: 把本集源文拆为剧情演绎的结构化分镜内容：分镜边界、出场资产、画面描述、逐字口播与原文锚。
i18n:
  zh-TW:
    title: "劇情演繹腳本規劃"
    description: "把本集原文拆成劇情演繹的結構化分鏡內容：分鏡邊界、出場資產、畫面描述、逐字口播與原文錨點。"
    slots:
      source_kind: "原文類型"
      target_language: "輸出語言，用專案的原文語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      style: "專案畫風"
      assets: "已登記資產，物件 {characters, scenes, props}，每項是 [{name, aliases, appearance}] 清單（角括號已中和；衍生寫成「本體/衍生」）"
      character_names: "可引用的角色名稱，衍生寫成「本體/衍生」"
      scene_names: "可引用的場景名稱"
      prop_names: "可引用的道具名稱"
      novel_text: "本集原文"
      episode: "集數"
      durations: "影片模型支援的秒數檔位"
      max_duration: "最長檔位的秒數"
      default_duration: "單個分鏡的預設秒數；未設定時為空"
      speech_rate: "口播語速（每秒閱讀單位數）"
      speech_unit: "閱讀單位量詞（字或詞）"
      episode_target_duration: "單集目標時長秒數；未設定時為空"
      episode_outline: "本集大綱（title、story_beats、hook、next_episode_teaser）；尚未規劃時為空"
      next_episode_outline: "下集大綱，格式同本集大綱；尚未規劃時為空"
      instructions: "附加指示；沒提供時為空"
  en:
    title: "Drama script planning"
    description: "Breaks the episode's source text into structured drama shots: shot boundaries, assets on screen, visual descriptions, verbatim lines and source anchors."
    slots:
      source_kind: "Source type"
      target_language: "Output language, the project's source language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      style: "Project art style"
      assets: "Registered assets, object {characters, scenes, props}, each a [{name, aliases, appearance}] list (angle brackets neutralized; variants written as “base/variant”)"
      character_names: "Character names that can be referenced; variants written as “base/variant”"
      scene_names: "Scene names that can be referenced"
      prop_names: "Prop names that can be referenced"
      novel_text: "This episode's source text"
      episode: "Episode number"
      durations: "Second tiers the video model supports"
      max_duration: "Seconds of the longest tier"
      default_duration: "Default seconds per shot; empty if not set"
      speech_rate: "Speaking rate (reading units per second)"
      speech_unit: "Reading unit word (characters or words)"
      episode_target_duration: "Target episode length in seconds; empty if not set"
      episode_outline: "This episode's outline (title, story_beats, hook, next_episode_teaser); empty if not planned"
      next_episode_outline: "Next episode's outline, same shape as this episode's; empty if not planned"
      instructions: "Additional instructions; empty if not given"
  ru:
    title: "Планирование сценария драмы"
    description: "Разбивает исходный текст серии на структурированные кадры драмы: границы кадров, материалы в кадре, описание изображения, дословные реплики и привязки к источнику."
    slots:
      source_kind: "Тип источника"
      target_language: "Язык вывода — язык источника проекта"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      style: "Художественный стиль проекта"
      assets: "Зарегистрированные материалы, объект {characters, scenes, props}, каждый — список [{name, aliases, appearance}] (угловые скобки нейтрализованы; варианты пишутся как «основной/вариант»)"
      character_names: "Имена персонажей, на которые можно ссылаться; варианты пишутся как «основной/вариант»"
      scene_names: "Названия сцен, на которые можно ссылаться"
      prop_names: "Названия реквизита, на который можно ссылаться"
      novel_text: "Исходный текст серии"
      episode: "Номер серии"
      durations: "Длительности в секундах, которые поддерживает видеомодель"
      max_duration: "Длительность самого длинного диапазона в секундах"
      default_duration: "Длительность кадра по умолчанию в секундах; пусто, если не задана"
      speech_rate: "Темп речи (единиц чтения в секунду)"
      speech_unit: "Единица чтения (иероглифы или слова)"
      episode_target_duration: "Целевая длительность серии в секундах; пусто, если не задана"
      episode_outline: "План этой серии (title, story_beats, hook, next_episode_teaser); пусто, если не спланирована"
      next_episode_outline: "План следующей серии, та же структура, что у текущей; пусто, если не спланирована"
      instructions: "Дополнительные указания; пусто, если не заданы"
  vi:
    title: "Lập kế hoạch kịch bản phim truyện"
    description: "Tách văn bản nguồn của tập thành các phân cảnh phim truyện có cấu trúc: ranh giới phân cảnh, tài sản xuất hiện, mô tả hình ảnh, lời thoại nguyên văn và mốc neo nguồn."
    slots:
      source_kind: "Loại nguồn"
      target_language: "Ngôn ngữ đầu ra, lấy ngôn ngữ nguồn của dự án"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      style: "Phong cách hình ảnh của dự án"
      assets: "Tài sản đã đăng ký, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, aliases, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa; biến thể viết là “gốc/biến thể”)"
      character_names: "Tên nhân vật có thể tham chiếu; biến thể viết là “gốc/biến thể”"
      scene_names: "Tên cảnh có thể tham chiếu"
      prop_names: "Tên đạo cụ có thể tham chiếu"
      novel_text: "Văn bản nguồn của tập"
      episode: "Số tập"
      durations: "Các mức giây mô hình video hỗ trợ"
      max_duration: "Số giây của mức dài nhất"
      default_duration: "Số giây mặc định của một phân cảnh; để trống nếu chưa đặt"
      speech_rate: "Tốc độ đọc (số đơn vị đọc mỗi giây)"
      speech_unit: "Đơn vị đọc (chữ hoặc từ)"
      episode_target_duration: "Thời lượng mục tiêu mỗi tập (giây); để trống nếu chưa đặt"
      episode_outline: "Dàn ý tập này (title, story_beats, hook, next_episode_teaser); để trống nếu chưa lập"
      next_episode_outline: "Dàn ý tập sau, cùng cấu trúc với dàn ý tập này; để trống nếu chưa lập"
      instructions: "Chỉ dẫn bổ sung; để trống nếu không có"
stage: script_plan
invoked_by:
  kind: agent_tool
  name: generate_script_plan
applies_to:
  content_mode:
  - drama
  generation_mode:
  - storyboard
  source_kind:
  - novel
  - screenplay
output_schema: lib.script.script_models:DramaNormalizedScript
slots:
  source_kind: 源文类型
  target_language: 输出语言，取项目源语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  style: 项目画风
  assets: 已登记资产，对象 {characters, scenes, props}，每项是 [{name, aliases, appearance}] 列表（尖括号已中和；衍生写作「本体/衍生」）
  character_names: 可引用的角色名，衍生写作「本体/衍生」
  scene_names: 可引用的场景名
  prop_names: 可引用的道具名
  novel_text: 本集源文
  episode: 集号
  durations: 视频模型支持的秒数档位
  max_duration: 最长档位秒数
  default_duration: 单个分镜的默认秒数；未设置为空
  speech_rate: 口播语速（每秒阅读单位数）
  speech_unit: 阅读单位量词（字或词）
  episode_target_duration: 单集目标时长秒数；未设置为空
  episode_outline: 本集大纲（title、story_beats、hook、next_episode_teaser）；未规划为空
  next_episode_outline: 下集大纲，形状同本集大纲；未规划为空
  instructions: 附加指令；未提供为空
protected: false
---
{{ variant("text/drama_script_plan/task", source_kind) }}

**输出语言**：自然语言字符串值必须使用 {{ target_language }}；JSON 键名 / 枚举值保持英文。{{ variant("text/drama_script_plan/language_rule", source_kind) }}
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

{{ partial("shared/pacing/drama") }}

## 项目信息

<overview>
{{ project_overview.synopsis or "" }}

题材类型：{{ project_overview.genre or "" }}
核心主题：{{ project_overview.theme or "" }}
世界观设定：{{ project_overview.world_setting or "" }}
</overview>

<style>
{{ style }}
</style>

{{ partial("shared/lists/asset_registry_blocks") }}

## 源文

<{{ source_kind }}>
{{ novel_text }}
</{{ source_kind }}>

{% if episode_outline %}
<episode_outline>
本集大纲（分集规划设计，剧本内容应覆盖全部故事节点）：
{% if episode_outline.title %}
本集标题：{{ episode_outline.title }}
{% endif %}
{{ partial("shared/lists/episode_outline_lines", outline=episode_outline) }}
</episode_outline>

{% if episode_outline.hook or episode_outline.next_episode_teaser %}
末场（最后一个或几个分镜）的画面与对白须实际呈现集尾钩子的戏剧内容，让悬念定格在画面上；有下集预告语时，用结尾画面或对白自然引出，不要生硬插入「下集预告」字样的旁白。

{% endif %}
{% endif %}
{% if next_episode_outline %}
<next_episode_outline>
下集大纲（仅用于设计本集结尾的衔接，不要把下集情节提前写进本集）：
{% if next_episode_outline.title %}
下集标题：{{ next_episode_outline.title }}
{% endif %}
{{ partial("shared/lists/episode_outline_lines", outline=next_episode_outline) }}
</next_episode_outline>

{% endif %}
# 字段写作指引

把源文拆为有序分镜，逐条产出结构化分镜内容。当前正在生成第 {{ episode }} 集。

## 基础字段

- **scene_id**：`E{{ episode }}S{两位序号}` 格式（如 E{{ episode }}S01），按分镜顺序递增，不得用其他集号前缀。
- **duration_seconds**：
  - 档位：{% if default_duration %}从支持的秒数档位（{{ durations }}）中按画面内容选择：默认 {{ default_duration }} 秒，打斗 / 大场面 / 情绪铺陈等画面可取更长档至 {{ max_duration }} 秒，不要默认选最短档{% else %}从支持的秒数档位（{{ durations }}）中按画面内容复杂度匹配合适时长（最长 {{ max_duration }} 秒），不强制默认值{% endif %}。
  - 口播下界：先估算该场 utterances（台词 + 画外音）念完约需的秒数（口播语速约 {{ speech_rate }} {{ speech_unit }}/秒），在上述档位里取**不低于**这个秒数的最接近档位。这是单向下界，画面 / 情绪留白可在此之上取更长档位；utterances 为空的分镜没有此下界；若口播估算已超过最长 {{ max_duration }} 秒，取最长档即可，不删减台词。
{% if episode_target_duration %}
  - 单集目标：{{ partial("shared/episode_target_duration_rule") }}。
{% endif %}
- **segment_break**：{{ variant("text/drama_script_plan/break_rule", source_kind) }}
- **characters_in_scene** / **scenes** / **props**：从下列候选中列出此分镜实际出现的资产。
  - 候选 characters：[{{ character_names | join(", ") or "（暂无）" }}]
  - 候选 scenes：[{{ scene_names | join(", ") or "（暂无）" }}]
  - 候选 props：[{{ prop_names | join(", ") or "（暂无）" }}]
  - 候选里没有的资产写原文称呼，并列进 `new_assets`（见下文）；泛指群演（如「老人甲」「村民若干」）不进 characters_in_scene。
- **scene_description**：{{ variant("text/drama_script_plan/scene_rule", source_kind) }}

## 逐字内容（内容真相源，定稿后原样保留、不再改写）

- **source_text**：逐字摘录本分镜对应的原文片段，尽量与原文一致、宁缺毋造（无把握可留空）。
- **utterances**：{{ variant("text/drama_script_plan/utterances_rule", source_kind) }}

每个分镜应为一个独立的视觉画面、可在指定时长内完成；避免在一个分镜内安排多个动作或画面切换。

{{ partial("shared/new_assets_rule") }}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
