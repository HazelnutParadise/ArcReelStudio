---
id: text/ad_reference_video_prompt_authoring
category: text
title: 广告 / 短片 · 参考生视频单元编写
description: 为广告参考生视频脚本里待编写的单元写出引用语法正文。
i18n:
  zh-TW:
    title: "廣告 / 短片 · 參考生影片單元編寫"
    description: "為廣告參考生影片腳本裡還沒寫的單元寫出引用語法正文。"
    slots:
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme}；缺值時傳 null"
      style: "專案風格"
      style_description: "專案風格描述"
      aspect_ratio: "畫面比例"
      aspect_ratio_label: "比例的文字標籤"
      brief: "創作 brief；沒填時傳 null"
      products: "商品資訊區塊（名稱 / 品牌 / 描述 / 賣點），由程式碼依商品資料渲染；沒有商品時傳 null"
      product_names: "候選商品名稱清單"
      character_names: "候選角色名稱清單"
      scene_names: "候選場景名稱清單"
      prop_names: "候選道具名稱清單"
      units_content: "整份影片單元的渲染文字（由程式碼投影：序號 + 待編寫標記 + 時長 + 正文）"
      pending_count: "待編寫的單元數"
      episode: "集數，廣告片一律是單一影片"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Ad / short · Reference-to-video unit writing"
    description: "Writes the reference-syntax body for units still to be written in an ad's reference-to-video script."
    slots:
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme}; null when missing"
      style: "Project style"
      style_description: "Project style description"
      aspect_ratio: "Aspect ratio"
      aspect_ratio_label: "Text label of the aspect ratio"
      brief: "Creative brief; null when not filled in"
      products: "Product details block (name / brand / description / selling points), rendered by code from the product data; null when there is no product"
      product_names: "Candidate product names"
      character_names: "Candidate character names"
      scene_names: "Candidate scene names"
      prop_names: "Candidate prop names"
      units_content: "Rendered text of all video units (projected by code: number + to-write mark + duration + body)"
      pending_count: "Number of units still to write"
      episode: "Episode number; an ad is always a single video"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Реклама / короткое видео · Написание блоков видео по референсу"
    description: "Пишет текст с синтаксисом ссылок для ещё не написанных блоков в сценарии рекламного видео по референсу."
    slots:
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme}; null при отсутствии"
      style: "Стиль проекта"
      style_description: "Описание стиля проекта"
      aspect_ratio: "Соотношение сторон"
      aspect_ratio_label: "Текстовая метка соотношения сторон"
      brief: "Творческий бриф; null, если не заполнен"
      products: "Блок сведений о товаре (название / бренд / описание / преимущества), формируется кодом из данных товара; null, если товара нет"
      product_names: "Список названий товаров-кандидатов"
      character_names: "Список имён персонажей-кандидатов"
      scene_names: "Список названий сцен-кандидатов"
      prop_names: "Список названий реквизита-кандидатов"
      units_content: "Отрисованный текст всех видеоблоков (проекция кодом: номер + отметка «написать» + длительность + текст)"
      pending_count: "Число блоков, которые ещё нужно написать"
      episode: "Номер серии; реклама всегда одно видео"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Quảng cáo / phim ngắn · Viết đơn vị video tham chiếu"
    description: "Viết nội dung theo cú pháp tham chiếu cho các đơn vị chưa viết trong kịch bản video tham chiếu của quảng cáo."
    slots:
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme}; null khi thiếu"
      style: "Phong cách dự án"
      style_description: "Mô tả phong cách dự án"
      aspect_ratio: "Tỷ lệ khung hình"
      aspect_ratio_label: "Nhãn chữ của tỷ lệ"
      brief: "Brief sáng tác; null khi chưa điền"
      products: "Khối thông tin sản phẩm (tên / thương hiệu / mô tả / điểm bán hàng), do mã kết xuất từ dữ liệu sản phẩm; null khi không có sản phẩm"
      product_names: "Danh sách tên sản phẩm đề xuất"
      character_names: "Danh sách tên nhân vật đề xuất"
      scene_names: "Danh sách tên cảnh đề xuất"
      prop_names: "Danh sách tên đạo cụ đề xuất"
      units_content: "Văn bản đã kết xuất của toàn bộ đơn vị video (do mã chiếu ra: số thứ tự + đánh dấu cần viết + thời lượng + nội dung)"
      pending_count: "Số đơn vị cần viết"
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
  - reference_video
output_schema: lib.script.script_models:ReferencePromptAuthoringFlatScript
slots:
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme}；缺值传 null
  style: 项目风格
  style_description: 项目风格描述
  aspect_ratio: 画面比例
  aspect_ratio_label: 比例的文字标签
  brief: 创作 brief；未填写时传 null
  products: 商品信息块（名称 / 品牌 / 描述 / 卖点），由代码按商品数据渲染；无商品时传 null
  product_names: 候选商品名列表
  character_names: 候选角色名列表
  scene_names: 候选场景名列表
  prop_names: 候选道具名列表
  units_content: 整份视频单元的渲染文本（由代码投影：序号 + 待编写标记 + 时长 + 正文）
  pending_count: 待编写单元数
  episode: 集号，广告片恒为单视频
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

你是一位资深短视频编导。下方是一支广告 / 短片已有的参考生视频单元，其中标注「【待编写】」的单元需要你写出正文；其余单元已定稿，只作前后文。

**输出语言**：所有正文使用 {{ target_language }}；JSON 键名保持英文。
**输出形状**：只输出 `{"title": "...", "units": [{"text": "..."}]}`，`units` 恰好 {{ pending_count }} 条，按待编写单元在片中的先后顺序一一对应。
单元时长、unit_id、references、generated_assets、needs_replan 均由系统沿用或派生，不得输出。`title` 不写回脚本，拟一个简短标题即可。

<overview>
{{ project_overview.synopsis or "" }}
题材：{{ project_overview.genre or "" }}
主题：{{ project_overview.theme or "" }}
</overview>

{{ partial("shared/text_style") }}

<brief>
{{ brief or "（未提供，按资产信息与常识自行设计）" }}
</brief>

<products>
{{ products or "（无商品，按通用短片创作）" }}
</products>

资产候选：
- products：[{{ product_names | join(", ") or "（无）" }}]
- characters：[{{ character_names | join(", ") or "（无）" }}]
- scenes：[{{ scene_names | join(", ") or "（无）" }}]
- props：[{{ prop_names | join(", ") or "（无）" }}]

<units>
{{ units_content }}
</units>

# 编写要求

- 待编写单元已有正文时，在它的基础上把画面描述写完整：其中的台词与画外音记号逐字保留，不增删、不改词。
- 待编写单元正文为空时，按 brief、商品信息与前后单元的内容补写，内容量与该单元时长匹配，与前后单元衔接自然。
- 每个单元内只能有一种发声归属：角色台词、无归属画外音或无发声三选一。

# 动作写作指引

{{ partial("shared/action_writing_guide") }}

# 统一引用语法

{{ partial("shared/writing_syntax") }}

商品、角色、场景、道具都使用同一个 `@[名称]` 语法。名称只可逐字取自候选表，不要发明资产。本片恒为第 {{ episode }} 集。
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
