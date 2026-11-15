---
id: text/draft_repair
category: text
title: 待修复草稿 AI 修复
description: 按违约报告修改待修复草稿：违约落在条目上时只改这些条目，落在整集层面时整份修改。脚本规划草稿与参考生视频的提示词编写草稿共用。
i18n:
  zh-TW:
    title: "待修復草稿 AI 修復"
    description: "依違規報告修改待修復草稿：違規出在個別條目時只改那些條目，出在整集層面時整份修改。腳本規劃草稿與參考生影片的提示詞編寫草稿共用。"
    slots:
      document: "草稿是哪種文件，以及條目陣列的結構說明"
      root: "草稿內容裡條目陣列的鍵名（scenes / segments / units）"
      draft_json: "完整草稿內容的 JSON"
      targets: "條目模式下要修改的條目，鍵齊全的物件清單 {index, item_json, messages}；整集模式傳 null"
      messages: "整集模式下的所有違規訊息清單；條目模式傳 null"
      source_text: "本集原文內容；沒有原文可參照時傳 null"
      instructions: "附加指示內容；沒有時傳 null"
  en:
    title: "AI repair for drafts"
    description: "Revises a draft that needs repair according to its violation report: only the affected entries when violations are on entries, the whole draft when they concern the episode as a whole. Shared by script planning drafts and reference-to-video prompt writing drafts."
    slots:
      document: "What kind of document the draft is, and how its entry array is structured"
      root: "Key of the entry array in the draft (scenes / segments / units)"
      draft_json: "JSON of the whole draft"
      targets: "Entries to revise in entry mode, a list of objects with all keys {index, item_json, messages}; null in whole-episode mode"
      messages: "All violation messages in whole-episode mode; null in entry mode"
      source_text: "This episode's source text; null when there is no source to refer to"
      instructions: "Additional instructions; null when absent"
  ru:
    title: "ИИ-исправление черновика"
    description: "Исправляет черновик по отчёту о нарушениях: если нарушения в отдельных записях, меняются только они, если на уровне всей серии — весь черновик. Общий для черновиков планирования сценария и черновиков промптов видео по референсу."
    slots:
      document: "Какой это документ и как устроен массив записей"
      root: "Ключ массива записей в черновике (scenes / segments / units)"
      draft_json: "JSON всего черновика"
      targets: "Записи для исправления в режиме записей, список объектов со всеми ключами {index, item_json, messages}; null в режиме всей серии"
      messages: "Все сообщения о нарушениях в режиме всей серии; null в режиме записей"
      source_text: "Исходный текст серии; null, если опереться не на что"
      instructions: "Дополнительные указания; null, если их нет"
  vi:
    title: "AI sửa bản nháp"
    description: "Sửa bản nháp cần sửa theo báo cáo vi phạm: nếu vi phạm nằm ở từng mục thì chỉ sửa các mục đó, nếu ở cấp cả tập thì sửa toàn bộ. Dùng chung cho bản nháp lập kế hoạch kịch bản và bản nháp viết prompt video tham chiếu."
    slots:
      document: "Bản nháp là loại tài liệu nào, và mô tả cấu trúc mảng mục"
      root: "Tên khóa của mảng mục trong bản nháp (scenes / segments / units)"
      draft_json: "JSON của toàn bộ bản nháp"
      targets: "Các mục cần sửa ở chế độ từng mục, danh sách đối tượng đủ khóa {index, item_json, messages}; null ở chế độ cả tập"
      messages: "Toàn bộ thông báo vi phạm ở chế độ cả tập; null ở chế độ từng mục"
      source_text: "Văn bản nguồn của tập; null khi không có nguồn để tham chiếu"
      instructions: "Chỉ dẫn bổ sung; null khi không có"
stage: script_plan
invoked_by:
  kind: user_action
  name: draft_repair
applies_to: {}
slots:
  document: 草稿是哪种文档、条目数组的结构说明
  root: 草稿正文里条目数组的键名（scenes / segments / units）
  draft_json: 完整草稿正文的 JSON
  targets: 条目模式下要修改的条目，键齐全的对象列表 {index, item_json, messages}；整集模式传 null
  messages: 整集模式下的全部违约消息列表；条目模式传 null
  source_text: 本集源文正文；没有源文可参照时传 null
  instructions: 附加指令正文；无时传 null
protected: false
---
你是短视频脚本的校对编辑。下面是一份没有通过校验的草稿，请按违约报告修改它，让它通过校验。

# 草稿说明

{{ document }}

完整草稿（只供参照上下文）：

```json
{{ draft_json }}
```
{% if source_text %}

<source_text>
{{ source_text }}
</source_text>
{% endif %}

# 修改要求

违约消息原本写给能调用工具的 Agent。消息里提到的工具调用（如 `patch_draft`）在这里都不适用，只按消息指出的内容问题修改 JSON。

{% if targets %}
违约只落在下列条目上。只修改这些条目，逐条消除它们的违约；不涉及违约的字段保持原值，条目 ID 不变。

{{ partial("text/draft_repair/lists/targets") }}

只输出一个 JSON 对象：`{"{{ root }}": [...]}`。数组按上面的顺序，依次给出每个条目修改后的完整对象，不输出其他条目。
{% else %}
违约落在整集层面，需要整份修改：

{{ partial("text/draft_repair/lists/messages") }}

没有违约的条目尽量保持原样。只输出修改后的完整草稿 JSON 对象，顶层字段与原草稿相同。
{% endif %}

保持草稿原有的语言与写法，不要输出 JSON 以外的内容。
{% if instructions %}

{{ partial("shared/additional_instructions") }}
{% endif %}
