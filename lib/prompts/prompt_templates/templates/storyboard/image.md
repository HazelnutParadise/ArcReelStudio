---
id: storyboard/image
category: storyboard
title: 分镜图
description: 分镜图的完整提示词，由风格、参考图声明与分镜画面组成。
i18n:
  zh-TW:
    title: "分鏡圖"
    description: "分鏡圖的完整提示詞，由風格、參考圖宣告與分鏡畫面組成。"
    slots:
      style: "專案畫風"
      style_description: "專案風格描述"
      reference_images: "已序列化的參考圖類型宣告，沒有參考圖時為空"
      structured_body: "已序列化的 Scene 與 Composition，純文字形態時為空"
      text_body: "純文字正文，結構化形態時為空"
  en:
    title: "Storyboard image"
    description: "The full prompt for a storyboard image, made of the style, reference image declarations and the shot's visuals."
    slots:
      style: "Project art style"
      style_description: "Project style description"
      reference_images: "Serialized reference image type declarations; empty without reference images"
      structured_body: "Serialized Scene and Composition; empty in plain-text form"
      text_body: "Plain-text body; empty in structured form"
  ru:
    title: "Изображение раскадровки"
    description: "Полный промпт для изображения раскадровки: стиль, объявление референсов и описание кадра."
    slots:
      style: "Художественный стиль проекта"
      style_description: "Описание стиля проекта"
      reference_images: "Сериализованное объявление типов референсов; пусто, если референсов нет"
      structured_body: "Сериализованные Scene и Composition; пусто в текстовой форме"
      text_body: "Простой текст; пусто в структурированной форме"
  vi:
    title: "Ảnh phân cảnh"
    description: "Prompt đầy đủ cho ảnh phân cảnh, gồm phong cách, khai báo ảnh tham chiếu và hình ảnh của phân cảnh."
    slots:
      style: "Phong cách hình ảnh của dự án"
      style_description: "Mô tả phong cách dự án"
      reference_images: "Khai báo loại ảnh tham chiếu đã tuần tự hóa; để trống nếu không có ảnh tham chiếu"
      structured_body: "Scene và Composition đã tuần tự hóa; để trống ở dạng văn bản thuần"
      text_body: "Nội dung văn bản thuần; để trống ở dạng có cấu trúc"
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