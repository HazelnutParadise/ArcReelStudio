---
id: storyboard/video
category: video
title: 分镜视频
description: 分镜生视频的完整提示词，由视频正文与负向约束组成。
i18n:
  zh-TW:
    title: "分鏡影片"
    description: "分鏡生成影片的完整提示詞，由影片正文與負向限制組成。"
    slots:
      body: "已序列化或純文字的影片正文，含依條件推導的發聲宣告"
  en:
    title: "Storyboard video"
    description: "The full prompt for turning a shot into video, made of the video body and negative constraints."
    slots:
      body: "The video body, serialized or plain text, including speech declarations derived from the gating rules"
  ru:
    title: "Видео раскадровки"
    description: "Полный промпт для превращения кадра в видео: текст видео и негативные ограничения."
    slots:
      body: "Текст видео, сериализованный или простым текстом, с объявлениями речи, выведенными по правилам допуска"
  vi:
    title: "Video phân cảnh"
    description: "Prompt đầy đủ để tạo video từ phân cảnh, gồm nội dung video và ràng buộc loại trừ."
    slots:
      body: "Nội dung video đã tuần tự hóa hoặc văn bản thuần, kèm khai báo phát âm suy ra theo quy tắc điều kiện"
stage: storyboard_video
invoked_by:
  kind: generation_task
  name: video
applies_to: {}
slots:
  body: 已序列化或纯文本的视频正文，含按门控派生的发声声明
protected: false
idempotent: true
---
{{ body }}

{{ partial("storyboard/video/avoid") }}
