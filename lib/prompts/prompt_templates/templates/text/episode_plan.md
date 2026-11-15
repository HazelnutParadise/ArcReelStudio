---
id: text/episode_plan
category: text
title: 分集规划
description: 把源文切分为若干集，每集给出标题、集尾钩子与结尾锚点，剧情演绎另给故事节点与下集预告语。
i18n:
  zh-TW:
    title: "分集規劃"
    description: "把原文切成若干集，每集給出標題、集尾鉤子與結尾錨點；劇情演繹另外給出故事節點與下集預告。"
    slots:
      content_mode: "創作類型軸值（drama / narration），用來解析具名變體片段"
      source_kind: "原文類型軸值（novel / screenplay），用來解析具名變體片段"
      synopsis: "故事大綱；沒有時傳 null"
      genre: "題材；沒有時傳 null"
      unit_noun: "閱讀單位量詞（字 / 詞），隨原文語言"
      target_volume: "每集目標分量，鍵齊全的物件 {units, seconds, units_per_second}；seconds 與 units_per_second 只在依單集目標時長換算時才有值，語速已格式化為文字；未設定時傳 null"
      max_episodes: "這一批最多規劃的集數，由文字模型的輸出上限推算"
      context_entries: "已規劃的最後幾集，鍵齊全的物件清單 {episode, title, hook}，沒有標題時 title 為 null；沒有時傳空清單"
      instructions: "附加指示內容；沒有時傳 null"
      progress: "整體進度，鍵齊全的物件 {planned_count, remaining_units, window_units}；只在有附加指示時傳入，否則傳 null"
      window_is_final: "這個視窗是否已含全文結尾（規劃一段未切分的原文時，是否已含這段原文的結尾）"
      followed_by_episode: "這個視窗結尾之後緊接著已規劃的集（規劃一段未切分的原文且這個視窗已含其結尾時為 true）"
      failure: "上一輪輸出沒通過檢核的原因清單；第一輪傳 null"
      window: "這一批原文視窗的內容"
  en:
    title: "Episode planning"
    description: "Splits the source text into episodes, each with a title, an end-of-episode hook and an ending anchor; drama also gets story beats and a next-episode teaser."
    slots:
      content_mode: "Content mode axis value (drama / narration), used to resolve named variant partials"
      source_kind: "Source type axis value (novel / screenplay), used to resolve named variant partials"
      synopsis: "Story synopsis; null when absent"
      genre: "Genre; null when absent"
      unit_noun: "Reading unit word (characters / words), following the source language"
      target_volume: "Target size per episode, an object with all keys {units, seconds, units_per_second}; seconds and units_per_second are set only when converted from the target episode length, with the rate formatted as text; null if not set"
      max_episodes: "Most episodes to plan in this batch, derived from the text model's output limit"
      context_entries: "The last few planned episodes, a list of objects with all keys {episode, title, hook}, title null when missing; an empty list when none"
      instructions: "Additional instructions; null when absent"
      progress: "Overall progress, an object with all keys {planned_count, remaining_units, window_units}; passed only with additional instructions, otherwise null"
      window_is_final: "Whether this window reaches the end of the text (when planning an unsplit stretch of source, whether it reaches the end of that stretch)"
      followed_by_episode: "Whether an already planned episode follows right after this window (true when planning an unsplit stretch and this window reaches its end)"
      failure: "Reasons the previous output failed validation; null on the first round"
      window: "Source text in this batch's window"
  ru:
    title: "Планирование серий"
    description: "Делит исходный текст на серии, у каждой есть название, крючок в конце и якорь окончания; для драмы также сюжетные точки и анонс следующей серии."
    slots:
      content_mode: "Значение оси типа контента (drama / narration), для выбора именованных вариантов фрагментов"
      source_kind: "Значение оси типа источника (novel / screenplay), для выбора именованных вариантов фрагментов"
      synopsis: "Синопсис; null, если его нет"
      genre: "Жанр; null, если не указан"
      unit_noun: "Единица чтения (иероглифы / слова), по языку источника"
      target_volume: "Целевой объём серии, объект со всеми ключами {units, seconds, units_per_second}; seconds и units_per_second заполнены только при пересчёте из целевой длительности серии, темп оформлен текстом; null, если не задан"
      max_episodes: "Максимум серий для планирования в этой партии, выведенный из лимита вывода текстовой модели"
      context_entries: "Последние спланированные серии, список объектов со всеми ключами {episode, title, hook}, title — null, если названия нет; пустой список, если серий нет"
      instructions: "Дополнительные указания; null, если их нет"
      progress: "Общий прогресс, объект со всеми ключами {planned_count, remaining_units, window_units}; передаётся только при дополнительных указаниях, иначе null"
      window_is_final: "Доходит ли окно до конца текста (при планировании неразделённого отрывка — до конца этого отрывка)"
      followed_by_episode: "Следует ли сразу за окном уже спланированная серия (true при планировании неразделённого отрывка, если окно доходит до его конца)"
      failure: "Причины, по которым предыдущий ответ не прошёл проверку; null в первом раунде"
      window: "Исходный текст в окне этой партии"
  vi:
    title: "Lập kế hoạch chia tập"
    description: "Chia văn bản nguồn thành nhiều tập, mỗi tập có tiêu đề, điểm móc cuối tập và mốc kết thúc; phim truyện có thêm các nút truyện và lời giới thiệu tập sau."
    slots:
      content_mode: "Giá trị trục chế độ nội dung (drama / narration), dùng để chọn các đoạn biến thể có tên"
      source_kind: "Giá trị trục loại nguồn (novel / screenplay), dùng để chọn các đoạn biến thể có tên"
      synopsis: "Tóm tắt câu chuyện; null khi không có"
      genre: "Thể loại; null khi không có"
      unit_noun: "Đơn vị đọc (chữ / từ), theo ngôn ngữ nguồn"
      target_volume: "Khối lượng mục tiêu mỗi tập, đối tượng đủ khóa {units, seconds, units_per_second}; seconds và units_per_second chỉ có giá trị khi quy đổi từ thời lượng mục tiêu mỗi tập, tốc độ đã định dạng thành văn bản; null nếu chưa đặt"
      max_episodes: "Số tập tối đa lập trong đợt này, suy ra từ giới hạn đầu ra của mô hình văn bản"
      context_entries: "Vài tập cuối đã lập, danh sách đối tượng đủ khóa {episode, title, hook}, title là null khi thiếu tiêu đề; danh sách rỗng khi không có"
      instructions: "Chỉ dẫn bổ sung; null khi không có"
      progress: "Tiến độ tổng thể, đối tượng đủ khóa {planned_count, remaining_units, window_units}; chỉ truyền khi có chỉ dẫn bổ sung, nếu không thì null"
      window_is_final: "Cửa sổ này đã chứa phần kết của toàn văn chưa (khi lập một đoạn nguồn chưa chia, đã chứa phần kết của đoạn đó chưa)"
      followed_by_episode: "Ngay sau cửa sổ này có tập đã lập hay không (true khi lập một đoạn nguồn chưa chia và cửa sổ đã chứa phần kết của nó)"
      failure: "Danh sách lý do đầu ra lượt trước không qua kiểm tra; null ở lượt đầu"
      window: "Văn bản nguồn trong cửa sổ của đợt này"
stage: episode_plan
invoked_by:
  kind: agent_tool
  name: plan_episodes
applies_to:
  content_mode: [drama, narration]
  source_kind: [novel, screenplay]
output_schema: lib.episode.episode_planner:DramaPlanDraft
slots:
  content_mode: 创作类型轴值（drama / narration），用于解析命名变体片段
  source_kind: 源文类型轴值（novel / screenplay），用于解析命名变体片段
  synopsis: 故事概述；无时传 null
  genre: 题材；无时传 null
  unit_noun: 阅读单位量词（字 / 词），随源文语言
  target_volume: 每集目标体量，键齐全的对象 {units, seconds, units_per_second}；seconds 与 units_per_second 仅按单集目标时长折算时有值，语速已格式化为文本；未设置时传 null
  max_episodes: 本批最多规划的集数，由文本模型的输出上限推导
  context_entries: 已规划末尾若干集，键齐全的对象列表 {episode, title, hook}，标题缺失时 title 为 null；无时传空列表
  instructions: 附加指令正文；无时传 null
  progress: 全局进度，键齐全的对象 {planned_count, remaining_units, window_units}；仅在有附加指令时传入，否则传 null
  window_is_final: 本窗口是否已含全文结尾（规划一段未切分的原文时，是否已含这段原文的结尾）
  followed_by_episode: 本窗口结尾之后紧接着已规划的集（规划一段未切分的原文且本窗口已含其结尾时为 true）
  failure: 上一轮输出未通过校验的原因列表；首轮传 null
  window: 本批源文窗口正文
protected: false
---
{{ variant("text/episode_plan/intro", source_kind) }}

# 项目信息
- 创作类型：{{ variant("text/episode_plan/content_mode_label", content_mode) }}
{% if synopsis %}
- 故事概述：{{ synopsis }}
{% endif %}
{% if genre %}
- 题材：{{ genre }}
{% endif %}
{% if target_volume %}
- 每集目标体量：约 {{ target_volume.units }} {{ unit_noun }}（{% if target_volume.seconds %}按单集目标时长 {{ target_volume.seconds }} 秒、口播语速约 {{ target_volume.units_per_second }} {{ unit_noun }}/秒粗略折算，{% endif %}允许为剧情完整性上下浮动）
{% else %}
- 每集目标体量：未设置，请按短视频节奏自行把握（以剧情弧完整优先）
{% endif %}
{% if max_episodes %}
- 本批最多规划 {{ max_episodes }} 集
{% endif %}
{% if context_entries %}

# 已规划的前情（已定上下文，不可改动，续着它往下规划）
{{ partial("text/episode_plan/lists/context_entries") }}
{% endif %}
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
{% if progress %}

# 全局进度
- 已规划 {{ progress.planned_count }} 集
- 未规划余量约 {{ progress.remaining_units }} {{ unit_noun }}（含本窗口，含后续源文件）
- 本窗口为其中前 {{ progress.window_units }} {{ unit_noun }}
- 若附加指令含总集数、按章节对齐等全局约束，请结合以上进度与余量换算本批的切分节奏与集数。
{% endif %}

# 切分规则
- 每一集给出 title（吸引人的短标题）、hook（集尾钩子说明：这一刀为什么切在这、给观众留了什么悬念）、
  end_anchor（本集结尾处的原文片段，10~30 个字符，必须从下方原文中逐字摘抄、含标点，且在整段原文中唯一出现；
  本集内容 = 上一集结尾之后到该片段末尾为止的全部原文）。
{{ variant("text/episode_plan/author_division_rule", source_kind) }}
{{ variant("text/episode_plan/outline_rule", content_mode) }}
- 各集按顺序排列，end_anchor 位置必须严格递增（范围连续、不重叠、不留空洞）。
{% if window_is_final and followed_by_episode %}
- 这段原文之后紧接着已经规划好的下一集：请规划到这段原文的结尾，最后一集的 end_anchor 取这段原文结尾处的片段，不要留尾巴。
{% elif window_is_final %}
- 这段原文已包含全文结尾：请规划到结尾，最后一集的 end_anchor 取全文结尾处的片段，不要留尾巴。
{% else %}
- 这段原文只是全文的一个窗口：窗口尾部剧情弧不完整的内容不要硬凑成集，留给下一批规划即可。
{% endif %}
- 如果这段原文里找不到任何一个剧情弧完整的切分点，返回空的 episodes 列表，不要硬切。
- 只输出符合 schema 的 JSON，不要输出其他内容。
{% if failure %}

# 上一轮输出未通过校验，请针对性修正后重新输出
{{ partial("text/episode_plan/lists/failure") }}
{% endif %}

{{ variant("text/episode_plan/source_heading", source_kind) }}
---
{{ window }}
---
