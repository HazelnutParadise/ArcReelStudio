---
id: text/drama_prompt_authoring
category: text
title: 剧情演绎 · 提示词编写
description: 为剧情演绎已定稿的分镜补全画面与视频提示词（image_prompt / video_prompt）。
i18n:
  zh-TW:
    title: "劇情演繹 · 提示詞編寫"
    description: "為劇情演繹已定稿的分鏡補上畫面與影片提示詞（image_prompt / video_prompt）。"
    slots:
      target_language: "輸出語言（自然語言字串值使用的語言）"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      style: "專案風格值"
      style_description: "專案風格描述"
      aspect_ratio: "畫面比例（例如 16:9）"
      aspect_ratio_label: "畫面比例的文字說明（直式構圖 / 橫式構圖 / 「<比例> 構圖」），由程式碼依比例產生"
      assets: "出場資產外觀，物件 {characters, scenes, props}，每項是 [{name, appearance}] 清單（角括號已中和）；呼叫端不提供資產區塊時傳 null"
      scenes_content: "script_plan 已定稿分鏡內容的渲染文字（由程式碼投影，含口播與原文錨點）"
      episode: "集數"
      instructions: "附加指示內容；沒有時傳 null"
  en:
    title: "Drama · Prompt writing"
    description: "Fills in the image and video prompts (image_prompt / video_prompt) for finalized drama shots."
    slots:
      target_language: "Output language (the language of natural-language string values)"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      style: "Project style value"
      style_description: "Project style description"
      aspect_ratio: "Aspect ratio (e.g. 16:9)"
      aspect_ratio_label: "Text description of the aspect ratio (portrait composition / landscape composition / \"<ratio> composition\"), produced by code from the ratio"
      assets: "Appearance of assets on screen, object {characters, scenes, props}, each a [{name, appearance}] list (angle brackets neutralized); null when the caller provides no asset block"
      scenes_content: "Rendered text of the finalized script_plan shots (projected by code, with spoken lines and source anchors)"
      episode: "Episode number"
      instructions: "Additional instructions; null when absent"
  ru:
    title: "Драма · Написание промптов"
    description: "Дописывает промпты изображения и видео (image_prompt / video_prompt) для утверждённых кадров драмы."
    slots:
      target_language: "Язык вывода (язык строковых значений на естественном языке)"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      style: "Значение стиля проекта"
      style_description: "Описание стиля проекта"
      aspect_ratio: "Соотношение сторон (например, 16:9)"
      aspect_ratio_label: "Текстовое описание соотношения сторон (вертикальная композиция / горизонтальная композиция / \"композиция <соотношение>\"), формируется кодом"
      assets: "Внешний вид материалов в кадре, объект {characters, scenes, props}, каждый — список [{name, appearance}] (угловые скобки нейтрализованы); null, если вызывающая сторона не передаёт блок материалов"
      scenes_content: "Отрисованный текст утверждённых кадров script_plan (проекция кодом, с репликами и привязками к источнику)"
      episode: "Номер серии"
      instructions: "Дополнительные указания; null, если их нет"
  vi:
    title: "Phim truyện · Viết prompt"
    description: "Bổ sung prompt hình ảnh và video (image_prompt / video_prompt) cho các phân cảnh phim truyện đã chốt."
    slots:
      target_language: "Ngôn ngữ đầu ra (ngôn ngữ của các giá trị chuỗi ngôn ngữ tự nhiên)"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      style: "Giá trị phong cách dự án"
      style_description: "Mô tả phong cách dự án"
      aspect_ratio: "Tỷ lệ khung hình (ví dụ 16:9)"
      aspect_ratio_label: "Mô tả bằng chữ của tỷ lệ khung hình (bố cục dọc / bố cục ngang / \"bố cục <tỷ lệ>\"), do mã tạo ra theo tỷ lệ"
      assets: "Ngoại hình tài sản xuất hiện, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa); null khi bên gọi không cung cấp khối tài sản"
      scenes_content: "Văn bản đã kết xuất của các phân cảnh script_plan đã chốt (do mã chiếu ra, gồm lời thoại và mốc neo nguồn)"
      episode: "Số tập"
      instructions: "Chỉ dẫn bổ sung; null khi không có"
stage: prompt_authoring
invoked_by:
  kind: agent_tool
  name: generate_episode_script
applies_to:
  content_mode:
  - drama
  generation_mode:
  - storyboard
output_schema: lib.script.script_models:DramaVisualScript
slots:
  target_language: 输出语言（自然语言字符串值所用语言）
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  style: 项目风格值
  style_description: 项目风格描述
  aspect_ratio: 画面比例（如 16:9）
  aspect_ratio_label: 画面比例的文字说明（竖屏构图 / 横屏构图 / "<比例> 构图"），由代码按比例产出
  assets: 出场资产外观，对象 {characters, scenes, props}，每项是 [{name, appearance}] 列表（尖括号已中和）；调用方不提供资产块时传 null
  scenes_content: script_plan 已定稿分镜内容的渲染文本（由代码投影，含口播与原文锚）
  episode: 集号
  instructions: 附加指令正文；无时传 null
protected: false
---
# 角色与任务

你是一位资深的短剧分镜摄影 / 动作设计师。下方分镜内容（分镜边界、出场资产、逐字口播、原文锚、视觉改编描述）均已定稿，你的唯一职责是为每个分镜补全视觉生产层：image_prompt（画面）与 video_prompt（动作 / 运镜 / 环境音）。**不要新增 / 删除 / 重排分镜、不要改动分镜内容。**

**输出语言**：所有字符串值必须使用 {{ target_language }}；JSON 键名 / 枚举值保持英文。
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

{{ partial("shared/pacing/drama") }}

# 上下文

{{ partial("shared/overview_block") }}

{{ partial("shared/text_style") }}

{% if assets %}
{{ partial("shared/lists/asset_appearance_blocks") }}

{{ partial("shared/asset_appearance_note") }}

{% endif %}
分镜内容中的「口播」与「原文锚」仅供理解戏剧节奏与语境，不要复制进视觉字段。

<shots>
{{ scenes_content }}
</shots>

<episode_constraints>
当前正在生成第 {{ episode }} 集。每个分镜产出一条视觉层，`scene_id` 必须逐字等于上方分镜内容里的 scene_id（含拆分 / 编辑后缀，如 `_1`），不增不减不改；不要输出口播 / 时长 / 资产等非视觉字段。
</episode_constraints>

# 字段写作指引

对每个分镜，按下列章节填写视觉字段。

{{ partial("shared/image_prompt_writing_guide") }}

## 视频提示词（video_prompt）——切换到「动作设计师」视角

- **video_prompt.action**：{{ partial("shared/action_writing_guide") }}
- **video_prompt.ambiance_audio**：{{ partial("shared/ambiance_audio_writing_guide") }}

# 创作目标

输出可直接驱动 AI 图像 / 视频生成的、视觉一致、节奏紧凑的视觉层。忠于已定稿的分镜内容与戏剧张力。
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
