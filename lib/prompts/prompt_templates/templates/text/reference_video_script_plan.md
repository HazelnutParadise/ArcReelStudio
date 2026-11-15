---
id: text/reference_video_script_plan
category: text
title: 参考生视频 · 单元拆分
description: 把源文拆分为参考生视频单元表，每个单元含时长、原文锚与引用语法正文。
i18n:
  zh-TW:
    title: "參考生影片 · 單元拆分"
    description: "把原文拆成參考生影片單元表，每個單元附時長、原文錨點與引用語法正文。"
    slots:
      source_kind: "原文類型；只有劇情演繹會用 screenplay"
      target_language: "輸出語言"
      project_overview: "專案概述，鍵齊全的物件 {synopsis, genre, theme, world_setting}；缺值時傳 null"
      assets: "已登記資產，物件 {characters, scenes, props}，每項是 [{name, aliases, appearance}] 清單（角括號已中和；衍生寫成「本體/衍生」）"
      character_names: "角色候選引用名稱清單（含 本體/衍生）"
      scene_names: "場景候選引用名稱清單"
      prop_names: "道具候選引用名稱清單"
      novel_text: "逐字原文"
      episode_outline: "本集大綱，鍵齊全的物件 {title, story_beats, hook, next_episode_teaser}；沒有有效內容時傳 null"
      next_episode_outline: "下集大綱，格式同上；沒有有效內容時傳 null"
      episode: "目前集數"
      durations: "排序並去重後的可用秒數檔位，已格式化為文字"
      duration_tiers: "「參考圖↔時長」兩組檔位，物件 {with_references, without_references, default_with_references_only, default_without_references_only}，檔位已格式化為文字，後兩項表示預設秒數只落在其中一組檔位內；兩組相同或型號未宣告時傳 null"
      default_duration: "預設秒數偏好；未設定時傳 null"
      speech_rate: "口播語速（閱讀單位 / 秒），已格式化為文字"
      speech_unit: "閱讀單位量詞（字 / 詞）"
      max_duration: "單次生成的時長上限（秒）"
      max_reference_images: "單個影片單元的參考圖上限；不限制時傳 null"
      episode_target_duration: "單集目標秒數；未設定時傳 null"
      instructions: "附加指示內容；缺值時傳 null"
  en:
    title: "Reference-to-video · Unit splitting"
    description: "Breaks the source text into a table of reference-to-video units, each with a duration, a source anchor and a reference-syntax body."
    slots:
      source_kind: "Source type; only drama uses screenplay"
      target_language: "Output language"
      project_overview: "Project overview, an object with all keys {synopsis, genre, theme, world_setting}; null when missing"
      assets: "Registered assets, object {characters, scenes, props}, each a [{name, aliases, appearance}] list (angle brackets neutralized; variants written as “base/variant”)"
      character_names: "Candidate character reference names (including base/variant)"
      scene_names: "Candidate scene reference names"
      prop_names: "Candidate prop reference names"
      novel_text: "Verbatim source text"
      episode_outline: "This episode's outline, an object with all keys {title, story_beats, hook, next_episode_teaser}; null when it has no usable content"
      next_episode_outline: "Next episode's outline, same shape as above; null when it has no usable content"
      episode: "Current episode number"
      durations: "Valid second tiers, sorted and deduplicated, formatted as text"
      duration_tiers: "Two sets of duration tiers for with/without reference images, object {with_references, without_references, default_with_references_only, default_without_references_only}, tiers formatted as text; the last two mean the default seconds fall in only one set; null when both sets are equal or the model declares none"
      default_duration: "Preferred default seconds; null if not set"
      speech_rate: "Speaking rate (reading units / second), formatted as text"
      speech_unit: "Reading unit word (characters / words)"
      max_duration: "Maximum length of a single generation (seconds)"
      max_reference_images: "Maximum reference images per video unit; null when unlimited"
      episode_target_duration: "Target episode length in seconds; null if not set"
      instructions: "Additional instructions; null when missing"
  ru:
    title: "Видео по референсу · Разбивка на блоки"
    description: "Делит исходный текст на таблицу блоков видео по референсу, у каждого есть длительность, привязка к источнику и текст с синтаксисом ссылок."
    slots:
      source_kind: "Тип источника; screenplay бывает только у драмы"
      target_language: "Язык вывода"
      project_overview: "Обзор проекта, объект со всеми ключами {synopsis, genre, theme, world_setting}; null при отсутствии"
      assets: "Зарегистрированные материалы, объект {characters, scenes, props}, каждый — список [{name, aliases, appearance}] (угловые скобки нейтрализованы; варианты пишутся как «основной/вариант»)"
      character_names: "Список имён персонажей-кандидатов для ссылок (включая основной/вариант)"
      scene_names: "Список названий сцен-кандидатов для ссылок"
      prop_names: "Список названий реквизита-кандидатов для ссылок"
      novel_text: "Дословный исходный текст"
      episode_outline: "План этой серии, объект со всеми ключами {title, story_beats, hook, next_episode_teaser}; null, если содержимого нет"
      next_episode_outline: "План следующей серии, та же структура; null, если содержимого нет"
      episode: "Номер текущей серии"
      durations: "Допустимые значения в секундах, отсортированные и без повторов, оформлены текстом"
      duration_tiers: "Два набора диапазонов длительности «с референсами / без», объект {with_references, without_references, default_with_references_only, default_without_references_only}, диапазоны оформлены текстом; последние два поля означают, что длительность по умолчанию попадает только в один набор; null, если наборы совпадают или модель их не объявляет"
      default_duration: "Предпочтительная длительность по умолчанию в секундах; null, если не задана"
      speech_rate: "Темп речи (единиц чтения / секунду), оформлен текстом"
      speech_unit: "Единица чтения (иероглифы / слова)"
      max_duration: "Максимальная длительность одной генерации (секунды)"
      max_reference_images: "Максимум референсов на один видеоблок; null, если без ограничений"
      episode_target_duration: "Целевая длительность серии в секундах; null, если не задана"
      instructions: "Дополнительные указания; null при отсутствии значения"
  vi:
    title: "Video tham chiếu · Chia đơn vị"
    description: "Tách văn bản nguồn thành bảng đơn vị video tham chiếu, mỗi đơn vị có thời lượng, mốc neo nguồn và nội dung theo cú pháp tham chiếu."
    slots:
      source_kind: "Loại nguồn; chỉ phim truyện mới dùng screenplay"
      target_language: "Ngôn ngữ đầu ra"
      project_overview: "Tổng quan dự án, đối tượng đủ khóa {synopsis, genre, theme, world_setting}; null khi thiếu"
      assets: "Tài sản đã đăng ký, đối tượng {characters, scenes, props}, mỗi mục là danh sách [{name, aliases, appearance}] (dấu ngoặc nhọn đã được vô hiệu hóa; biến thể viết là “gốc/biến thể”)"
      character_names: "Danh sách tên nhân vật đề xuất để tham chiếu (gồm gốc/biến thể)"
      scene_names: "Danh sách tên cảnh đề xuất để tham chiếu"
      prop_names: "Danh sách tên đạo cụ đề xuất để tham chiếu"
      novel_text: "Văn bản nguồn nguyên văn"
      episode_outline: "Dàn ý tập này, đối tượng đủ khóa {title, story_beats, hook, next_episode_teaser}; null khi không có nội dung hợp lệ"
      next_episode_outline: "Dàn ý tập sau, cùng cấu trúc như trên; null khi không có nội dung hợp lệ"
      episode: "Số tập hiện tại"
      durations: "Các mức giây hợp lệ, đã sắp xếp và bỏ trùng, đã định dạng thành văn bản"
      duration_tiers: "Hai bộ mức thời lượng có/không ảnh tham chiếu, đối tượng {with_references, without_references, default_with_references_only, default_without_references_only}, các mức đã định dạng thành văn bản; hai mục sau cho biết số giây mặc định chỉ nằm trong một bộ; null khi hai bộ giống nhau hoặc mô hình không khai báo"
      default_duration: "Số giây mặc định ưu tiên; null nếu chưa đặt"
      speech_rate: "Tốc độ đọc (đơn vị đọc / giây), đã định dạng thành văn bản"
      speech_unit: "Đơn vị đọc (chữ / từ)"
      max_duration: "Thời lượng tối đa của một lần tạo (giây)"
      max_reference_images: "Số ảnh tham chiếu tối đa cho một đơn vị video; null khi không giới hạn"
      episode_target_duration: "Số giây mục tiêu mỗi tập; null nếu chưa đặt"
      instructions: "Chỉ dẫn bổ sung; null khi thiếu"
stage: script_plan
invoked_by:
  kind: agent_tool
  name: generate_script_plan
applies_to:
  content_mode: [drama, narration]
  generation_mode: [reference_video]
  source_kind: [novel, screenplay]
output_schema: lib.script.script_models:ReferenceScriptPlanFlatDraft
slots:
  source_kind: 源文类型；只有剧情演绎会取 screenplay
  target_language: 输出语言
  project_overview: 项目概述，键齐全的对象 {synopsis, genre, theme, world_setting}；缺值传 null
  assets: 已登记资产，对象 {characters, scenes, props}，每项是 [{name, aliases, appearance}] 列表（尖括号已中和；衍生写作「本体/衍生」）
  character_names: 角色候选引用名列表（含 本体/衍生）
  scene_names: 场景候选引用名列表
  prop_names: 道具候选引用名列表
  novel_text: 逐字源文
  episode_outline: 本集大纲，键齐全的对象 {title, story_beats, hook, next_episode_teaser}；无有效内容时传 null
  next_episode_outline: 下集大纲，形状同上；无有效内容时传 null
  episode: 当前集号
  durations: 排序去重后的合法秒数档位，已格式化为文本
  duration_tiers: 「参考图↔时长」两套档位，对象 {with_references, without_references, default_with_references_only, default_without_references_only}，档位已格式化为文本，后两项表示默认秒数只落在其中一套档位内；两套相同或型号未声明时传 null
  default_duration: 默认秒数偏好；未设置时传 null
  speech_rate: 口播语速（阅读单位 / 秒），已格式化为文本
  speech_unit: 阅读单位量词（字 / 词）
  max_duration: 单次生成的时长上限（秒）
  max_reference_images: 单个视频单元的参考图上限；不限时传 null
  episode_target_duration: 单集目标秒数；未设置时传 null
  instructions: 附加指令正文；缺值传 null
protected: false
---
# 角色与任务

{{ variant("text/reference_video_script_plan/task", source_kind) }}
每个 video_unit 对应**一次视频生成调用**，正文是一段连续的画面描述，一次生成完整覆盖它。
本阶段定的是**结构与内容契约**：unit 边界、时长（时长即计费单位）、台词落位、核心资产指认——用户会逐 unit 审阅确认这份契约。
视觉编排（景别 / 构图 / 运镜扩写）由后续 prompt_authoring 以你的拆分为基底生成，本阶段不写。

**输出语言**：所有字符串值必须使用 {{ target_language }}；JSON 键名保持英文。
例外（逐字保留、不翻译）：`@[名称]` 中的资产名须逐字等于下方候选表中的登记名或 `new_assets` 里的称呼；`source_text` 须逐字复制源文。
**结构约束**：字段 / 枚举 / 必填项由 response_schema 强制；本提示只解释**如何写好每个字段的内容**。

# 上下文

{{ partial("shared/overview_block") }}

{{ partial("shared/lists/asset_registry_blocks") }}

{{ variant("text/reference_video_script_plan/source_heading", source_kind) }}

<{{ source_kind }}>
{{ novel_text }}
</{{ source_kind }}>

{% if episode_outline %}
<episode_outline>
{% if episode_outline.title %}
标题：{{ episode_outline.title }}
{% endif %}
{{ partial("shared/lists/episode_outline_lines", outline=episode_outline) }}
</episode_outline>

{% endif %}
{% if next_episode_outline %}
<next_episode_outline>
{% if next_episode_outline.title %}
标题：{{ next_episode_outline.title }}
{% endif %}
{{ partial("shared/lists/episode_outline_lines", outline=next_episode_outline) }}
</next_episode_outline>

{% endif %}
# 拆分规则

当前正在生成第 {{ episode }} 集。请覆盖全部源文情节，按叙事顺序逐 unit 产出。

- **unit 边界**：{{ variant("text/reference_video_script_plan/unit_rule", source_kind) }}
- **source_text**：该 unit 所依据的源文片段，**逐字复制**（可截断首尾，但中间不得删字、改写、翻译或概括）。
  它是追溯锚，用于把生成结果对回原文；不逐字复制会被机械校验拒绝。
- **时长决策序**（自上而下，高优先级是硬边界，低优先级在其内做优化）：
  1. 硬约束：`duration_seconds` 是 unit 时长（一次生成调用一个时长），必须取支持档位（{{ durations }}）中的值。
     叙事需要的时长放不下时，把该 unit 按叙事顺序重拆为多个 unit，**不得违约时长**。
{% if duration_tiers %}
     本型号下该档位还随「有无参考图」分两套，按该 unit **画面描述里有没有 `@` 资产引用**取用（台词记号 `@[角色]{台词}` 的说话人不计入——它不生成参考图，只驱动音色声明）：带 `@` 引用取（{{ duration_tiers.with_references }}），不带取（{{ duration_tiers.without_references }}）。服务端按该 unit 此刻**可用的参考图**定档：引用的资产还没有生成参考图时，该 unit 按不带引用的那套档位执行。两者取其一：要么改取该 unit 引用状态对应档位内的值，要么调整引用——把次要资产融入描述文字、不用 `@` 引用，从而适用不带引用的那套档位。
{% endif %}
  2. 台词下界：先估算该 unit 全部台词与画外音念完约需的秒数（口播语速约 {{ speech_rate }} {{ speech_unit }}/秒），
     取**不低于**这个秒数的档位。这是单向下界——台词永不压进念不完的短档；无台词的 unit 没有此下界。
     台词量超过最长档（{{ max_duration }} 秒）时把该 unit 拆开，不要把台词硬塞进一个 unit。
  3. 默认偏好：{% if default_duration %}unit 默认取 {{ default_duration }} 秒{% if duration_tiers and duration_tiers.default_with_references_only %}（该默认值只落在带 `@` 引用的 unit 的档位内，另一种状态的 unit 按上面的硬约束取值）{% endif %}{% if duration_tiers and duration_tiers.default_without_references_only %}（该默认值只落在不带 `@` 引用的 unit 的档位内，另一种状态的 unit 按上面的硬约束取值）{% endif %}，叙事需要更长时可取更长档（偏好可被内容需要覆盖，硬约束不可）{% else %}按叙事需要从档位中取值，不强制默认值{% endif %}。
  4. 打包效率：在 1-3 之内组织正文内容，{% if episode_target_duration %}按本集目标时长打包——{{ partial("shared/episode_target_duration_rule") }}；单个 unit 在目标之内可长可短，不必贴近单次上限 {{ max_duration }} 秒，也{% else %}使 unit 时长贴近 {{ max_duration }} 秒；{% endif %}不要默认选最短 / 保守值。
{% if max_reference_images %}
- **references 上限**：一个 unit 的**画面描述里** `@` 引用的资产名（去重后）不超过 {{ max_reference_images }} 个（台词记号 `@[角色]{台词}` 的说话人不计入——它不生成参考图）；超出时把次要角色融入背景描述（不用 `@` 引用），不要压缩主体资产。
{% endif %}

# 正文书写语法

{{ partial("shared/writing_syntax") }}

# 本阶段的正文写作指引

- 画面描述聚焦当下瞬间的**可见动作**：谁做了什么、物件互动、环境动态；动词描述物理可观察动作
  （伸手 / 转身 / 推门 / 投向），避免「陷入 / 回忆 / 意识到 / 决定」等内心动词。
- 资产名逐字取自下列候选；候选里没有的写原文称呼，并列进 `new_assets`（见下文），台词记号的说话人同样如此：
  - character: {{ partial("shared/asset_name_candidates", names=character_names) }}
  - scene: {{ partial("shared/asset_name_candidates", names=scene_names) }}
  - prop: {{ partial("shared/asset_name_candidates", names=prop_names) }}
{{ variant("text/reference_video_script_plan/dialogue_rule", source_kind) }}
- 每个 unit 的正文都要 `@` 引用它发生地的场景资产；地点切换到新 unit 时换成新地点的场景，
  地点不变的连续 unit 逐条重复引用同一个场景（候选表里没有匹配的场景时才用文字写地点）。
- 本阶段不写景别 / 构图 / 运镜（prompt_authoring 补），把叙事内容与动作过程写清楚即可。

{{ partial("shared/new_assets_rule") }}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
