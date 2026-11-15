---
id: text/ad_storyboard_prompt_authoring
category: text
title: 广告 / 短片 · 分镜提示词编写
description: 为广告分镜脚本里待编写的分镜补全画面与视频提示词（image_prompt / video_prompt）。
i18n:
  zh-TW:
    title: "廣告 / 短片 · 分鏡提示詞編寫"
    description: "為廣告分鏡腳本裡還沒寫的分鏡補上畫面與影片提示詞（image_prompt / video_prompt）。"
    slots:
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      style: "專案風格"
      style_description: "專案風格描述"
      aspect_ratio: "畫面比例"
      aspect_ratio_label: "比例的文字標籤"
      brief: "創作 brief；沒填時傳 null"
      character_names: "候選角色名稱清單（本體在前、衍生緊接在後），角括號已中和"
      scene_names: "候選場景名稱清單"
      prop_names: "候選道具名稱清單"
      products: "商品資訊區塊（名稱 / 品牌 / 描述 / 賣點），由程式碼依商品資料渲染；沒有商品時傳 null"
      shots_content: "整份分鏡的渲染文字（由程式碼投影：待編寫的分鏡帶標記，其餘分鏡附上已有的畫面與動作摘要）"
      episode: "集數，廣告片一律是單一影片"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Ad / short · Storyboard prompt writing"
    description: "Fills in the image and video prompts (image_prompt / video_prompt) for shots still to be written in an ad's storyboard script."
    slots:
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      style: "Project style"
      style_description: "Project style description"
      aspect_ratio: "Aspect ratio"
      aspect_ratio_label: "Text label of the aspect ratio"
      brief: "Creative brief; null when not filled in"
      character_names: "Candidate character names (each base followed by its variants), angle brackets neutralized"
      scene_names: "Candidate scene names"
      prop_names: "Candidate prop names"
      products: "Product details block (name / brand / description / selling points), rendered by code from the product data; null when there is no product"
      shots_content: "Rendered text of the whole storyboard (projected by code: shots to write are marked, the rest carry a summary of their existing visuals and action)"
      episode: "Episode number; an ad is always a single video"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Реклама / короткое видео · Написание промптов раскадровки"
    description: "Дописывает промпты изображения и видео (image_prompt / video_prompt) для ещё не написанных кадров в рекламной раскадровке."
    slots:
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      style: "Стиль проекта"
      style_description: "Описание стиля проекта"
      aspect_ratio: "Соотношение сторон"
      aspect_ratio_label: "Текстовая метка соотношения сторон"
      brief: "Творческий бриф; null, если не заполнен"
      character_names: "Список имён персонажей-кандидатов (сначала основной, сразу за ним варианты), угловые скобки нейтрализованы"
      scene_names: "Список названий сцен-кандидатов"
      prop_names: "Список названий реквизита-кандидатов"
      products: "Блок сведений о товаре (название / бренд / описание / преимущества), формируется кодом из данных товара; null, если товара нет"
      shots_content: "Отрисованный текст всей раскадровки (проекция кодом: кадры для написания помечены, остальные с кратким описанием изображения и действия)"
      episode: "Номер серии; реклама всегда одно видео"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Quảng cáo / phim ngắn · Viết prompt phân cảnh"
    description: "Bổ sung prompt hình ảnh và video (image_prompt / video_prompt) cho các phân cảnh chưa viết trong kịch bản phân cảnh quảng cáo."
    slots:
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      style: "Phong cách dự án"
      style_description: "Mô tả phong cách dự án"
      aspect_ratio: "Tỷ lệ khung hình"
      aspect_ratio_label: "Nhãn chữ của tỷ lệ"
      brief: "Brief sáng tác; null khi chưa điền"
      character_names: "Danh sách tên nhân vật đề xuất (bản gốc trước, biến thể ngay sau), dấu ngoặc nhọn đã được vô hiệu hóa"
      scene_names: "Danh sách tên cảnh đề xuất"
      prop_names: "Danh sách tên đạo cụ đề xuất"
      products: "Khối thông tin sản phẩm (tên / thương hiệu / mô tả / điểm bán hàng), do mã kết xuất từ dữ liệu sản phẩm; null khi không có sản phẩm"
      shots_content: "Văn bản đã kết xuất của toàn bộ phân cảnh (do mã chiếu ra: phân cảnh cần viết có đánh dấu, các phân cảnh khác kèm tóm tắt hình ảnh và hành động hiện có)"
      episode: "Số tập; quảng cáo luôn là một video"
      instructions: "Chỉ dẫn bổ sung; null khi thiếu"
stage: prompt_authoring
invoked_by:
  kind: agent_tool
  name: generate_episode_script
applies_to:
  content_mode:
  - ad
  generation_mode:
  - storyboard
output_schema: lib.script.script_models:AdVisualScript
slots:
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  style: 项目风格
  style_description: 项目风格描述
  aspect_ratio: 画面比例
  aspect_ratio_label: 比例的文字标签
  brief: 创作 brief；未填写时传 null
  character_names: 候选角色名列表（本体在前、衍生紧随其后），尖括号已中和
  scene_names: 候选场景名列表
  prop_names: 候选道具名列表
  products: 商品信息块（名称 / 品牌 / 描述 / 卖点），由代码按商品数据渲染；无商品时传 null
  shots_content: 整份分镜的渲染文本（由代码投影：待编写分镜带标记，其余分镜附已有画面与动作摘要）
  episode: 集号，广告片恒为单视频
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

你是一位资深的短视频分镜摄影 / 动作设计师。下方是一支已定稿的广告 / 短片分镜脚本，其中标注「【待编写】」的分镜还没有视觉层。你的唯一职责是为这些分镜补全视觉生产层：image_prompt（画面）与 video_prompt（动作 / 运镜 / 环境音 / 出镜台词）。**不要新增 / 删除 / 重排分镜、不要改动口播、时长、段落与出场资产。**

**输出语言**：所有字符串值必须使用 {{ target_language }}；JSON 键名 / 枚举值保持英文。
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

# 上下文

{{ partial("shared/overview_block") }}

{{ partial("shared/text_style") }}

<brief>
{{ brief or "（未提供，按商品信息与常识自行设计）" }}
</brief>

{% if products %}
<products>
{{ products }}
</products>

商品入画时外观须与商品信息一致：{{ partial("shared/product_fidelity") }}。

{% endif %}
{{ partial("shared/lists/asset_name_blocks") }}

未标注的分镜已有视觉层，只作前后文参照：待编写分镜的画面与动作要与前后分镜衔接自然、风格一致。

<shots>
{{ shots_content }}
</shots>

<episode_constraints>
本片为单视频（恒第 {{ episode }} 集）。只为标注「【待编写】」的分镜各产出一条视觉层，`shot_id` 必须逐字等于该分镜的 shot_id，不增不减不改；不要输出口播 / 时长 / 资产等非视觉字段。
</episode_constraints>

# 字段写作指引

{{ partial("shared/image_prompt_writing_guide") }}

## 视频提示词（video_prompt）——切换到「动作设计师」视角

- **video_prompt.action**：{{ partial("shared/action_writing_guide") }}
- **video_prompt.camera_motion**：按画面内容自行选择。
- **video_prompt.ambiance_audio**：{{ partial("shared/ambiance_audio_writing_guide") }}
- **video_prompt.dialogue**：仅当分镜内有出镜人物开口说话时填写（口播旁白已在脚本里，不要重复进 dialogue）；speaker 必须是该分镜的出场角色。

# 创作目标

输出可直接驱动 AI 图像 / 视频生成的、与前后分镜视觉一致的视觉层。忠于分镜口播与创作 brief，卖点表达不夸大、不虚构功效。
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
