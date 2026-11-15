---
id: text/narration_script_plan
category: text
title: 旁白解说 · 片段切分
description: 按朗读节奏把源文逐字切分为旁白解说分镜，并登记出场资产与时长。
i18n:
  zh-TW:
    title: "旁白解說 · 片段切分"
    description: "依朗讀節奏把原文逐字切成旁白解說分鏡，並登記出場資產與時長。"
    slots:
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      novel_text: "逐字原文"
      assets: "已登記資產，物件 {characters, scenes, props}，每項是 [{name, aliases, appearance}] 清單（角括號已中和；衍生寫成「本體/衍生」）"
      character_names: "角色候選引用名稱清單"
      scene_names: "場景候選引用名稱清單"
      prop_names: "道具候選引用名稱清單"
      episode: "目前集數"
      durations: "排序並去重後的可用秒數檔位"
      max_duration: "最長的可用秒數"
      default_duration: "預設秒數偏好；缺值或不在可用檔位內時傳 null"
      episode_target_duration: "單集目標秒數；缺值時傳 null"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Narration · Segment splitting"
    description: "Splits the source text word for word into narration shots by reading pace, recording the assets on screen and each duration."
    slots:
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      novel_text: "Verbatim source text"
      assets: "Registered assets, object {characters, scenes, props}, each a [{name, aliases, appearance}] list (angle brackets neutralized; variants written as “base/variant”)"
      character_names: "Candidate character reference names"
      scene_names: "Candidate scene reference names"
      prop_names: "Candidate prop reference names"
      episode: "Current episode number"
      durations: "Valid second tiers, sorted and deduplicated"
      max_duration: "Longest valid duration in seconds"
      default_duration: "Preferred default seconds; null when missing or not a valid tier"
      episode_target_duration: "Target episode length in seconds; null when missing"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Закадровый текст · Разбивка на фрагменты"
    description: "Дословно делит исходный текст на кадры с закадровым текстом по темпу чтения и отмечает материалы в кадре и длительность."
    slots:
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      novel_text: "Дословный исходный текст"
      assets: "Зарегистрированные материалы, объект {characters, scenes, props}, каждый — список [{name, aliases, appearance}] (угловые скобки нейтрализованы; варианты пишутся как «основной/вариант»)"
      character_names: "Список имён персонажей-кандидатов для ссылок"
      scene_names: "Список названий сцен-кандидатов для ссылок"
      prop_names: "Список названий реквизита-кандидатов для ссылок"
      episode: "Номер текущей серии"
      durations: "Допустимые значения в секундах, отсортированные и без повторов"
      max_duration: "Наибольшая допустимая длительность в секундах"
      default_duration: "Предпочтительная длительность по умолчанию в секундах; null, если не задана или недопустима"
      episode_target_duration: "Целевая длительность серии в секундах; null при отсутствии значения"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Thuyết minh · Chia đoạn"
    description: "Chia nguyên văn văn bản nguồn thành các phân cảnh thuyết minh theo nhịp đọc, ghi lại tài sản xuất hiện và thời lượng."
    slots:
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      novel_text: "Văn bản nguồn nguyên văn"
      assets: "Tài sản đã đăng ký, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, aliases, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa; biến thể viết là “gốc/biến thể”)"
      character_names: "Danh sách tên nhân vật đề xuất để tham chiếu"
      scene_names: "Danh sách tên cảnh đề xuất để tham chiếu"
      prop_names: "Danh sách tên đạo cụ đề xuất để tham chiếu"
      episode: "Số tập hiện tại"
      durations: "Các mức giây hợp lệ, đã sắp xếp và bỏ trùng"
      max_duration: "Số giây hợp lệ dài nhất"
      default_duration: "Số giây mặc định ưu tiên; null khi thiếu hoặc không thuộc mức hợp lệ"
      episode_target_duration: "Số giây mục tiêu mỗi tập; null khi thiếu"
      instructions: "Chỉ dẫn bổ sung; null khi thiếu"
stage: script_plan
invoked_by:
  kind: agent_tool
  name: generate_script_plan
applies_to:
  content_mode:
  - narration
  generation_mode:
  - storyboard
output_schema: lib.script.script_models:NarrationScriptPlanDraft
slots:
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  novel_text: 逐字源文
  assets: 已登记资产，对象 {characters, scenes, props}，每项是 [{name, aliases, appearance}] 列表（尖括号已中和；衍生写作「本体/衍生」）
  character_names: 角色候选引用名列表
  scene_names: 场景候选引用名列表
  prop_names: 道具候选引用名列表
  episode: 当前集号
  durations: 排序去重后的合法秒数档位
  max_duration: 最长合法秒数
  default_duration: 默认秒数偏好；缺值或不在合法档位时传 null
  episode_target_duration: 单集目标秒数；缺值传 null
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

你是一位专业的旁白内容架构师，本任务是把源文按朗读节奏拆分为适合短视频配音的分镜表（script_plan 脚本规划）。
旁白/解说脚本走两段式：本阶段只定内容层——逐字 `novel_text`、分镜边界、时长、场景切换标记与出场资产；
视觉层（image_prompt / video_prompt）由后续 prompt_authoring 按 `segment_id` 对齐生成，`novel_text` 由本阶段定稿后透传、不再重出。

**输出语言**：自然语言字符串值使用 {{ target_language }}；JSON 键名保持英文。
例外（逐字保留、不翻译、不改写）：`novel_text` 逐字等于源文原句（含标点）；资产引用字段
（`characters_in_segment` / `scenes` / `props`）逐字等于下方候选表中的登记名或 `new_assets` 里的称呼。
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

{{ partial("shared/pacing/narration") }}

# 上下文

{{ partial("shared/overview_block") }}

{{ partial("shared/lists/asset_registry_blocks") }}

## 小说原文

<novel>
{{ novel_text }}
</novel>

# 拆分规则

当前正在生成第 {{ episode }} 集。

- **novel_text**：逐字保留小说原文，不改编 / 不删减 / 不添加 / 不改标点（后期配音与透传的真相源）；
  对话片段含完整说话内容与引导语（如「他说道」）。在句号 / 问号 / 感叹号 / 省略号等标点或段落结束处拆分，
  保持语义完整，不拆断完整的语义单元。
- **segment_id**：`E{{ episode }}S{两位序号}` 格式（如 E{{ episode }}S01），按顺序递增，不得用其他集号前缀。
- **duration_seconds**：{% if default_duration %}单分镜默认取 {{ default_duration }} 秒（按朗读语速估算该秒数内能念完的字数）；长句 / 情绪铺陈 / 关键对话等可从档位中取更长值（至 {{ max_duration }} 秒）——偏好可被内容需要覆盖，硬约束不可{% else %}按朗读节奏从档位（{{ durations }}）中取值（最长 {{ max_duration }} 秒），不强制默认值{% endif %}{% if episode_target_duration %}。{{ partial("shared/episode_target_duration_rule") }}{% endif %}。取值必须落在支持档位（{{ durations }}）内。
- **segment_break**：在真正的场景切换点（时间跳跃 / 空间转换 / 情节转折）标 `true`，同一连续场景内标 `false`，不要滥用。
- **characters_in_segment / scenes / props**：列出该分镜 `novel_text` 中实际出现（被叙述或对话提及）的已登记资产，
  名称逐字取自下列候选，候选里没有的写原文称呼并列进 `new_assets`；泛指群演（老人甲 / 村民若干）不登记、不进 characters_in_segment。
  三个数组均必填，无对应资产时显式写空数组 `[]`。
  - character: {{ partial("shared/asset_name_candidates", names=character_names) }}
  - scene: {{ partial("shared/asset_name_candidates", names=scene_names) }}
  - prop: {{ partial("shared/asset_name_candidates", names=prop_names) }}

请覆盖全部源文，按叙事顺序逐分镜产出。

{{ partial("shared/new_assets_rule") }}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
