---
id: storyboard/image
category: storyboard
title: 分镜图
description: 分镜图的完整提示词，由风格、参考图声明与分镜画面组成。
i18n:
  zh-TW:
    title: "分鏡圖"
    description: "分鏡圖的完整提示詞，由風格、參考圖宣告與分鏡畫面組成。"
  en:
    title: "Storyboard image"
    description: "The full prompt for a storyboard image, made of the style, reference image declarations and the shot's visuals."
  ru:
    title: "Изображение раскадровки"
    description: "Полный промпт для изображения раскадровки: стиль, объявление референсов и описание кадра."
  vi:
    title: "Ảnh phân cảnh"
    description: "Prompt đầy đủ cho ảnh phân cảnh, gồm phong cách, khai báo ảnh tham chiếu và hình ảnh của phân cảnh."
stage: storyboard_image
invoked_by:
  kind: generation_task
  name: storyboard
applies_to: {}
slots:
  style: 项目画风
  style_description: 项目风格描述
  reference_images: 已序列化的参考图类型声明，无参考图为空
  structured_body: 已序列化的 Scene 与 Composition，纯文本形态为空
  text_body: 纯文本正文，结构化形态为空
protected: false
idempotent: true
---
{{ partial("shared/media_style") }}
{% if reference_images %}
{{ partial("storyboard/image/references") }}
{% endif %}
{% if text_body %}

{{ text_body }}

{% else %}
{{ structured_body }}
{% endif %}
{{ partial("storyboard/image/avoid") }}