---
id: text/ad_reference_video_script
category: text
title: 广告 / 短片 · 参考生视频单元
description: 按 brief 与资产候选一次产出广告片的参考生视频单元，每个单元含引用语法正文。
i18n:
  zh-TW:
    title: "廣告 / 短片 · 參考生影片單元"
    description: "依 brief 與資產候選一次產出廣告片的參考生影片單元，每個單元都附引用語法正文。"
    slots:
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme}；缺值時傳 null"
      style: "專案風格"
      style_description: "專案風格描述"
      aspect_ratio: "畫面比例"
      aspect_ratio_label: "比例的文字標籤"
      brief: "創作 brief；沒填時傳 null"
      assets: "已登記資產，物件 {characters, scenes, props}，每項是 [{name, aliases, appearance}] 清單（角括號已中和；衍生寫成「本體/衍生」）"
      products: "商品資訊區塊（名稱 / 品牌 / 描述 / 賣點），由程式碼依商品資料渲染；沒有商品時傳 null"
      product_names: "候選商品名稱清單"
      character_names: "候選角色名稱清單"
      scene_names: "候選場景名稱清單"
      prop_names: "候選道具名稱清單"
      target_duration: "整部影片的目標總時長（秒）"
      ad_duration_tier: "最接近目標總時長的審定檔位（15 / 30 / 60 / 90），距離相同時取較接近 30 秒的一邊，用來解析配比表變體"
      off_tier_target_duration: "目標總時長不在審定檔位內時的目標秒數，用來依比例調整說明；剛好是檔位時傳 null"
      min_unit_duration: "單個 unit 編排時長下限（秒）"
      max_unit_duration: "單個 unit 編排時長上限（秒）"
      episode: "集數，廣告片一律是單一影片"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Ad / short · Reference-to-video units"
    description: "Produces all reference-to-video units of an ad in one pass from the brief and candidate assets, each with its reference-syntax body."
    slots:
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme}; null when missing"
      style: "Project style"
      style_description: "Project style description"
      aspect_ratio: "Aspect ratio"
      aspect_ratio_label: "Text label of the aspect ratio"
      brief: "Creative brief; null when not filled in"
      assets: "Registered assets, object {characters, scenes, props}, each a [{name, aliases, appearance}] list (angle brackets neutralized; variants written as “base/variant”)"
      products: "Product details block (name / brand / description / selling points), rendered by code from the product data; null when there is no product"
      product_names: "Candidate product names"
      character_names: "Candidate character names"
      scene_names: "Candidate scene names"
      prop_names: "Candidate prop names"
      target_duration: "Target total length of the whole video (seconds)"
      ad_duration_tier: "The reviewed tier closest to the target length (15 / 30 / 60 / 90), taking the side nearer 30 seconds on a tie; used to resolve the allocation table variant"
      off_tier_target_duration: "Target seconds when the total length is not one of the reviewed tiers, used to scale the guidance proportionally; null when it matches a tier"
      min_unit_duration: "Minimum arranged length of a single unit (seconds)"
      max_unit_duration: "Maximum arranged length of a single unit (seconds)"
      episode: "Episode number; an ad is always a single video"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Реклама / короткое видео · Блоки видео по референсу"
    description: "За один проход создаёт все блоки видео по референсу для рекламного ролика по брифу и подходящим материалам, у каждого блока есть текст с синтаксисом ссылок."
    slots:
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme}; null при отсутствии"
      style: "Стиль проекта"
      style_description: "Описание стиля проекта"
      aspect_ratio: "Соотношение сторон"
      aspect_ratio_label: "Текстовая метка соотношения сторон"
      brief: "Творческий бриф; null, если не заполнен"
      assets: "Зарегистрированные материалы, объект {characters, scenes, props}, каждый — список [{name, aliases, appearance}] (угловые скобки нейтрализованы; варианты пишутся как «основной/вариант»)"
      products: "Блок сведений о товаре (название / бренд / описание / преимущества), формируется кодом из данных товара; null, если товара нет"
      product_names: "Список названий товаров-кандидатов"
      character_names: "Список имён персонажей-кандидатов"
      scene_names: "Список названий сцен-кандидатов"
      prop_names: "Список названий реквизита-кандидатов"
      target_duration: "Целевая общая длительность ролика (секунды)"
      ad_duration_tier: "Ближайший к целевой длительности утверждённый диапазон (15 / 30 / 60 / 90), при равенстве — тот, что ближе к 30 секундам; для выбора варианта таблицы пропорций"
      off_tier_target_duration: "Целевая длительность в секундах, если она не совпадает с утверждёнными диапазонами, для пропорциональной подгонки указаний; null, если совпадает"
      min_unit_duration: "Минимальная длительность одного блока (секунды)"
      max_unit_duration: "Максимальная длительность одного блока (секунды)"
      episode: "Номер серии; реклама всегда одно видео"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Quảng cáo / phim ngắn · Đơn vị video tham chiếu"
    description: "Tạo toàn bộ đơn vị video tham chiếu của quảng cáo trong một lần từ brief và các tài sản đề xuất, mỗi đơn vị kèm nội dung theo cú pháp tham chiếu."
    slots:
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme}; null khi thiếu"
      style: "Phong cách dự án"
      style_description: "Mô tả phong cách dự án"
      aspect_ratio: "Tỷ lệ khung hình"
      aspect_ratio_label: "Nhãn chữ của tỷ lệ"
      brief: "Brief sáng tác; null khi chưa điền"
      assets: "Tài sản đã đăng ký, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, aliases, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa; biến thể viết là “gốc/biến thể”)"
      products: "Khối thông tin sản phẩm (tên / thương hiệu / mô tả / điểm bán hàng), do mã kết xuất từ dữ liệu sản phẩm; null khi không có sản phẩm"
      product_names: "Danh sách tên sản phẩm đề xuất"
      character_names: "Danh sách tên nhân vật đề xuất"
      scene_names: "Danh sách tên cảnh đề xuất"
      prop_names: "Danh sách tên đạo cụ đề xuất"
      target_duration: "Tổng thời lượng mục tiêu của cả phim (giây)"
      ad_duration_tier: "Mức đã duyệt gần tổng thời lượng mục tiêu nhất (15 / 30 / 60 / 90), khi cách đều thì lấy bên gần 30 giây hơn; dùng để chọn biến thể bảng phân bổ"
      off_tier_target_duration: "Số giây mục tiêu khi tổng thời lượng không thuộc các mức đã duyệt, dùng để điều chỉnh hướng dẫn theo tỷ lệ; null khi trùng một mức"
      min_unit_duration: "Thời lượng sắp xếp tối thiểu của một đơn vị (giây)"
      max_unit_duration: "Thời lượng sắp xếp tối đa của một đơn vị (giây)"
      episode: "Số tập; quảng cáo luôn là một video"
      instructions: "Chỉ dẫn bổ sung; null khi thiếu"
stage: script_plan
invoked_by:
  kind: agent_tool
  name: generate_episode_script
applies_to:
  content_mode:
  - ad
  generation_mode:
  - reference_video
  ad_duration_tier:
  - '15'
  - '30'
  - '60'
  - '90'
output_schema: lib.script.script_models:AdReferenceFlatScript
slots:
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme}；缺值传 null
  style: 项目风格
  style_description: 项目风格描述
  aspect_ratio: 画面比例
  aspect_ratio_label: 比例的文字标签
  brief: 创作 brief；未填写时传 null
  assets: 已登记资产，对象 {characters, scenes, props}，每项是 [{name, aliases, appearance}] 列表（尖括号已中和；衍生写作「本体/衍生」）
  products: 商品信息块（名称 / 品牌 / 描述 / 卖点），由代码按商品数据渲染；无商品时传 null
  product_names: 候选商品名列表
  character_names: 候选角色名列表
  scene_names: 候选场景名列表
  prop_names: 候选道具名列表
  target_duration: 全片目标总时长（秒）
  ad_duration_tier: 距目标总时长最近的审定档位（15 / 30 / 60 / 90），等距时取更接近 30 秒的一侧，用于解析配比表变体
  off_tier_target_duration: 目标总时长不在审定档位内时的目标秒数，用于按比例适配说明；恰为档位时传 null
  min_unit_duration: 单个 unit 编排时长下限（秒）
  max_unit_duration: 单个 unit 编排时长上限（秒）
  episode: 集号，广告片恒为单视频
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

你是一位资深短视频编导。根据 brief 与资产候选，直接创作可供参考生视频的一组自包含 video unit。

**输出语言**：所有正文使用 {{ target_language }}；JSON 键名保持英文。
**输出形状**：只输出 `{"title": "...", "units": [{"duration_seconds": {{ min_unit_duration }}, "text": "..."}], "new_assets": []}`。
unit_id、references、generated_assets、needs_replan 均由系统派生，不得输出。不要输出 shots、section、shot_id、逐分镜时长、voiceover_text 或 speech_mode。

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

{{ partial("shared/lists/asset_registry_blocks") }}

资产候选：
- products：[{{ product_names | join(", ") or "（无）" }}]
- characters：[{{ character_names | join(", ") or "（无）" }}]
- scenes：[{{ scene_names | join(", ") or "（无）" }}]
- props：[{{ prop_names | join(", ") or "（无）" }}]

# 内容规划

目标总时长为 {{ target_duration }} 秒，所有 unit.duration_seconds 之和应贴近该值；每个 unit 是一次生成调用的完整编排时长，取 {{ min_unit_duration }}-{{ max_unit_duration }} 的整数，不按供应商档位量化。
下方框架只用于安排内容与节奏，不得把段落名写入 JSON 或正文：

{% if products %}
{{ partial("shared/ad_pacing/allocation") }}
{% else %}
按开场、发展、高潮、收束组织内容。
{% endif %}

本片恒为第 {{ episode }} 集。每个 unit 内只能有一种发声归属：角色台词、无归属画外音或无发声三选一；需要切换归属时拆成相邻 unit，不要在同一 unit 混写。

# 动作写作指引

{{ partial("shared/action_writing_guide") }}

# 统一引用语法

{{ partial("shared/writing_syntax") }}

商品、角色、场景、道具都使用同一个 `@[名称]` 语法。商品名逐字取自候选表；角色、场景、道具逐字取自候选表，或写 `new_assets` 里的称呼（台词记号的说话人同样如此）。

{{ partial("shared/ad_new_assets_rule") }}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
