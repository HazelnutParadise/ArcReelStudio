---
id: text/ad_storyboard_script
category: text
title: 广告 / 短片 · 分镜脚本
description: 按 brief 与商品信息一次产出广告片的平铺分镜脚本。
i18n:
  zh-TW:
    title: "廣告 / 短片 · 分鏡腳本"
    description: "依 brief 與商品資訊一次產出廣告片的平鋪分鏡腳本。"
    slots:
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      style: "專案風格"
      style_description: "專案風格描述"
      aspect_ratio: "畫面比例"
      aspect_ratio_label: "比例的文字標籤"
      brief: "創作 brief；沒填時傳 null"
      assets: "已登記資產，物件 {characters, scenes, props}，每項是 [{name, aliases, appearance}] 清單（角括號已中和；衍生寫成「本體/衍生」）"
      character_names: "候選角色名稱清單（本體在前、衍生緊接在後），角括號已中和"
      scene_names: "候選場景名稱清單"
      prop_names: "候選道具名稱清單"
      products: "商品資訊區塊（名稱 / 品牌 / 描述 / 賣點），由程式碼依商品資料渲染；沒有商品時傳 null"
      product_names: "候選商品名稱清單；沒有商品時傳空清單"
      target_duration: "整部影片的目標總時長（秒）"
      ad_duration_tier: "最接近目標總時長的審定檔位（15 / 30 / 60 / 90），距離相同時取較接近 30 秒的一邊，用來解析配比表變體"
      off_tier_target_duration: "目標總時長不在審定檔位內時的目標秒數，用來依比例調整說明；剛好是檔位時傳 null"
      duration_constraint: "單一分鏡的時長限制句，由影片模型支援的時長集合算出"
      speech_rate: "口播語速數值（專案設定優先，否則依語言預設），已格式化為文字"
      unit_noun: "閱讀單位量詞（字 / 詞），隨輸出語言"
      episode: "集數，廣告片一律是單一影片"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Ad / short · Storyboard script"
    description: "Produces an ad's flat storyboard script in one pass from the brief and product details."
    slots:
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      style: "Project style"
      style_description: "Project style description"
      aspect_ratio: "Aspect ratio"
      aspect_ratio_label: "Text label of the aspect ratio"
      brief: "Creative brief; null when not filled in"
      assets: "Registered assets, object {characters, scenes, props}, each a [{name, aliases, appearance}] list (angle brackets neutralized; variants written as “base/variant”)"
      character_names: "Candidate character names (each base followed by its variants), angle brackets neutralized"
      scene_names: "Candidate scene names"
      prop_names: "Candidate prop names"
      products: "Product details block (name / brand / description / selling points), rendered by code from the product data; null when there is no product"
      product_names: "Candidate product names; an empty list when there are none"
      target_duration: "Target total length of the whole video (seconds)"
      ad_duration_tier: "The reviewed tier closest to the target length (15 / 30 / 60 / 90), taking the side nearer 30 seconds on a tie; used to resolve the allocation table variant"
      off_tier_target_duration: "Target seconds when the total length is not one of the reviewed tiers, used to scale the guidance proportionally; null when it matches a tier"
      duration_constraint: "The per-shot duration constraint sentence, derived from the durations the video model supports"
      speech_rate: "Speaking rate (the project's setting first, otherwise the language default), formatted as text"
      unit_noun: "Reading unit word (characters / words), following the output language"
      episode: "Episode number; an ad is always a single video"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Реклама / короткое видео · Сценарий раскадровки"
    description: "За один проход создаёт линейный сценарий раскадровки рекламного ролика по брифу и данным о товаре."
    slots:
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      style: "Стиль проекта"
      style_description: "Описание стиля проекта"
      aspect_ratio: "Соотношение сторон"
      aspect_ratio_label: "Текстовая метка соотношения сторон"
      brief: "Творческий бриф; null, если не заполнен"
      assets: "Зарегистрированные материалы, объект {characters, scenes, props}, каждый — список [{name, aliases, appearance}] (угловые скобки нейтрализованы; варианты пишутся как «основной/вариант»)"
      character_names: "Список имён персонажей-кандидатов (сначала основной, сразу за ним варианты), угловые скобки нейтрализованы"
      scene_names: "Список названий сцен-кандидатов"
      prop_names: "Список названий реквизита-кандидатов"
      products: "Блок сведений о товаре (название / бренд / описание / преимущества), формируется кодом из данных товара; null, если товара нет"
      product_names: "Список названий товаров-кандидатов; пустой список, если товаров нет"
      target_duration: "Целевая общая длительность ролика (секунды)"
      ad_duration_tier: "Ближайший к целевой длительности утверждённый диапазон (15 / 30 / 60 / 90), при равенстве — тот, что ближе к 30 секундам; для выбора варианта таблицы пропорций"
      off_tier_target_duration: "Целевая длительность в секундах, если она не совпадает с утверждёнными диапазонами, для пропорциональной подгонки указаний; null, если совпадает"
      duration_constraint: "Фраза об ограничении длительности кадра, выведенная из длительностей, которые поддерживает видеомодель"
      speech_rate: "Темп речи (сначала настройка проекта, иначе значение по умолчанию для языка), оформлен текстом"
      unit_noun: "Единица чтения (иероглифы / слова), по языку вывода"
      episode: "Номер серии; реклама всегда одно видео"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Quảng cáo / phim ngắn · Kịch bản phân cảnh"
    description: "Tạo kịch bản phân cảnh dạng phẳng cho quảng cáo trong một lần từ brief và thông tin sản phẩm."
    slots:
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      style: "Phong cách dự án"
      style_description: "Mô tả phong cách dự án"
      aspect_ratio: "Tỷ lệ khung hình"
      aspect_ratio_label: "Nhãn chữ của tỷ lệ"
      brief: "Brief sáng tác; null khi chưa điền"
      assets: "Tài sản đã đăng ký, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, aliases, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa; biến thể viết là “gốc/biến thể”)"
      character_names: "Danh sách tên nhân vật đề xuất (bản gốc trước, biến thể ngay sau), dấu ngoặc nhọn đã được vô hiệu hóa"
      scene_names: "Danh sách tên cảnh đề xuất"
      prop_names: "Danh sách tên đạo cụ đề xuất"
      products: "Khối thông tin sản phẩm (tên / thương hiệu / mô tả / điểm bán hàng), do mã kết xuất từ dữ liệu sản phẩm; null khi không có sản phẩm"
      product_names: "Danh sách tên sản phẩm đề xuất; danh sách rỗng khi không có sản phẩm"
      target_duration: "Tổng thời lượng mục tiêu của cả phim (giây)"
      ad_duration_tier: "Mức đã duyệt gần tổng thời lượng mục tiêu nhất (15 / 30 / 60 / 90), khi cách đều thì lấy bên gần 30 giây hơn; dùng để chọn biến thể bảng phân bổ"
      off_tier_target_duration: "Số giây mục tiêu khi tổng thời lượng không thuộc các mức đã duyệt, dùng để điều chỉnh hướng dẫn theo tỷ lệ; null khi trùng một mức"
      duration_constraint: "Câu ràng buộc thời lượng mỗi phân cảnh, suy ra từ các thời lượng mô hình video hỗ trợ"
      speech_rate: "Tốc độ đọc (ưu tiên thiết lập của dự án, nếu không thì theo mặc định của ngôn ngữ), đã định dạng thành văn bản"
      unit_noun: "Đơn vị đọc (chữ / từ), theo ngôn ngữ đầu ra"
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
  - storyboard
  ad_duration_tier:
  - '15'
  - '30'
  - '60'
  - '90'
output_schema: lib.script.script_models:AdEpisodeScript
slots:
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  style: 项目风格
  style_description: 项目风格描述
  aspect_ratio: 画面比例
  aspect_ratio_label: 比例的文字标签
  brief: 创作 brief；未填写时传 null
  assets: 已登记资产，对象 {characters, scenes, props}，每项是 [{name, aliases, appearance}] 列表（尖括号已中和；衍生写作「本体/衍生」）
  character_names: 候选角色名列表（本体在前、衍生紧随其后），尖括号已中和
  scene_names: 候选场景名列表
  prop_names: 候选道具名列表
  products: 商品信息块（名称 / 品牌 / 描述 / 卖点），由代码按商品数据渲染；无商品时传 null
  product_names: 候选商品名列表；无商品时传空列表
  target_duration: 全片目标总时长（秒）
  ad_duration_tier: 距目标总时长最近的审定档位（15 / 30 / 60 / 90），等距时取更接近 30 秒的一侧，用于解析配比表变体
  off_tier_target_duration: 目标总时长不在审定档位内时的目标秒数，用于按比例适配说明；恰为档位时传 null
  duration_constraint: 单分镜时长约束句，由视频模型支持的时长集合算出
  speech_rate: 口播语速数值（项目覆盖优先，否则按语言默认），已格式化为文本
  unit_noun: 阅读单位量词（字 / 词），随输出语言
  episode: 集号，广告片恒为单视频
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

{% if products %}
你是一位资深的带货短视频编导，精通把商品卖点与创作诉求转写为可直接驱动 AI 图像 / 视频生成的结构化分镜脚本。
你的任务：基于下方商品信息与创作 brief，按带货八段框架与时长配比，产出一支约 {{ target_duration }} 秒的带货短视频分镜脚本（平铺 shots[]），符合 schema 的 JSON。
{% else %}
你是一位资深的短视频编导，精通把一段创作诉求转写为可直接驱动 AI 图像 / 视频生成的结构化分镜脚本。
你的任务：基于下方创作 brief，产出一支约 {{ target_duration }} 秒的通用短片分镜脚本（平铺 shots[]），符合 schema 的 JSON。
{% endif %}

**输出语言**：所有字符串值必须使用 {{ target_language }}；JSON 键名 / 枚举值保持英文。
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

# 上下文

{{ partial("shared/overview_block") }}

{{ partial("shared/text_style") }}

<brief>
{{ brief or "（未提供，按商品信息与常识自行设计）" }}
</brief>

{{ partial("shared/lists/asset_registry_blocks") }}

{% if products %}
<products>
{{ products }}
</products>

# 带货八段框架与时长配比

带货短视频按八个段落组织：hook → pain_point → product_reveal → selling_point → demo → trust → price_promo → cta。
下方配比表经审定，是各段时长与分镜数的执行标准：

{{ partial("shared/ad_pacing/allocation") }}
{% else %}
# 时长与节奏

- 全片目标总时长 {{ target_duration }} 秒，各分镜 duration_seconds 之和应贴近该值。
- 单个分镜{{ duration_constraint }}；全片平均 3-5 秒/分镜，按内容节奏自行切分。
{% endif %}

<episode_constraints>
本片为单视频（恒第 {{ episode }} 集）。所有 shot_id 必须严格使用 `E{{ episode }}S{两位序号}` 格式（如 E{{ episode }}S01、E{{ episode }}S02），按播放顺序连续编号，不得使用其他集号前缀。
</episode_constraints>

# 字段写作指引

{% if products %}
对每个分镜，按下列章节填写字段。

## 基础字段

- **section**：该分镜所属的带货框架段落标签，使用上方八值（如 hook、pain_point）；同段多个分镜重复同一标签。
- **voiceover_text**：每个分镜的口播文案，必须完整可照稿配音、与画面同步；无口播的纯画面分镜填空字符串。全片口播连起来应是一篇完整流畅的带货话术，口播长度按约 {{ speech_rate }} {{ unit_noun }}/秒折算。
- **duration_seconds**：单个分镜{{ duration_constraint }}；各段合计遵循配比表，全片总和贴近 {{ target_duration }} 秒。
- **products_in_shot**：该分镜画面中实际出现的商品名称列表（商品入画即列出，含局部/手持/包装）；氛围分镜填空数组。
  - 候选 products：[{{ product_names | join(", ") }}]
  - 商品名只取自候选。
- **characters_in_shot** / **scenes** / **props**：仅列出此分镜画面中实际出现的资产。
  - 候选 characters：[{{ character_names | join(", ") or "（无）" }}]
  - 候选 scenes：[{{ scene_names | join(", ") or "（无）" }}]
  - 候选 props：[{{ prop_names | join(", ") or "（无）" }}]
  - 候选里没有的资产写自拟称呼，并列进 `new_assets`（见下文）。
{% else %}
## 基础字段

- **section**：本片无带货框架，按内容自拟简短英文段落标签（如 opening/development/climax/ending），用于标记分镜在叙事中的位置。
- **voiceover_text**：每个分镜的口播文案，必须完整可照稿配音；无口播的纯画面分镜填空字符串。口播长度按约 {{ speech_rate }} {{ unit_noun }}/秒折算。
- **characters_in_shot** / **scenes** / **props**：仅列出此分镜画面中实际出现的资产。
  - 候选 characters：[{{ character_names | join(", ") or "（无）" }}]
  - 候选 scenes：[{{ scene_names | join(", ") or "（无）" }}]
  - 候选 props：[{{ prop_names | join(", ") or "（无）" }}]
  - 候选里没有的资产写自拟称呼，并列进 `new_assets`（见下文）。
- **products_in_shot**：本项目无商品，所有分镜一律填空数组。
{% endif %}

{{ partial("shared/image_prompt_writing_guide") }}

## 视频提示词（video_prompt）——切换到「动作设计师」视角

- **video_prompt.action**：{{ partial("shared/action_writing_guide") }}
- **video_prompt.camera_motion**：按画面内容自行选择。
- **video_prompt.ambiance_audio**：{{ partial("shared/ambiance_audio_writing_guide") }}
- **video_prompt.dialogue**：仅当分镜内有出镜人物开口说话时填写（口播旁白写在 voiceover_text，不要重复进 dialogue）；speaker 必须出现在 characters_in_shot。

{{ partial("shared/ad_new_assets_rule") }}

# 创作目标

{% if products %}
输出可直接驱动 AI 生成的、商品忠实、节奏紧凑的带货分镜脚本。卖点表达贴合 <products> 的 selling_points，不夸大、不虚构功效。
{% else %}
输出可直接驱动 AI 生成的、视觉一致、节奏紧凑的短片脚本。忠于创作 brief、保留情绪张力。
{% endif %}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
