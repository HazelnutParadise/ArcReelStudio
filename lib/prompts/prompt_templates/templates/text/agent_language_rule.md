---
id: text/agent_language_rule
category: text
title: Agent 语言规范
description: 追加在内置创作 Agent 系统提示里的语言规范段，语言随用户的界面语言。
i18n:
  zh-TW:
    title: "Agent 語言規範"
    description: "附加在內建創作 Agent 系統提示裡的語言規範段落，語言跟著使用者的介面語言。"
  en:
    title: "Agent language rule"
    description: "The language rule appended to the built-in creative Agent's system prompt; it follows the user's interface language."
  ru:
    title: "Языковое правило агента"
    description: "Языковое правило, добавляемое в системный промпт встроенного творческого агента; язык совпадает с языком интерфейса пользователя."
  vi:
    title: "Quy tắc ngôn ngữ của Agent"
    description: "Đoạn quy tắc ngôn ngữ thêm vào system prompt của Agent sáng tác tích hợp; ngôn ngữ theo ngôn ngữ giao diện của người dùng."
stage: agent_session
invoked_by:
  kind: user_action
  name: agent_session
applies_to: {}
slots:
  lang: 界面语言的语言名（中文 / English / Tiếng Việt）
protected: false
---
## 语言规范

- **回答用户必须使用{{ lang }}**：所有回复、思考过程、任务清单及计划文件，均须使用{{ lang }}
- **视频内容语言**：所有生成的视频对话、旁白、字幕均使用{{ lang }}
- **文档使用{{ lang }}**：所有的 Markdown 文件均使用{{ lang }}编写
- **Prompt 使用{{ lang }}**：图片生成/视频生成使用的 prompt 应使用{{ lang }}编写
