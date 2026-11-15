---
id: asset/sheet
category: asset
title: 资产图
description: 角色、角色衍生、场景、道具与商品资产图的完整提示词。
i18n:
  zh-TW:
    title: "資產圖"
    description: "角色、角色衍生、場景、道具與商品資產圖的完整提示詞。"
    slots:
      asset_type: "資產類型"
      name: "資產名稱，衍生時為空"
      description: "外觀描述，或相對於本體的變化"
      style: "專案畫風"
      style_description: "專案風格描述"
  en:
    title: "Asset image"
    description: "The full prompt for character, character variant, scene, prop and product asset images."
    slots:
      asset_type: "Asset type"
      name: "Asset name; empty for a variant"
      description: "Appearance description, or how it differs from the base"
      style: "Project art style"
      style_description: "Project style description"
  ru:
    title: "Изображение материала"
    description: "Полный промпт для изображений персонажей, их вариантов, сцен, реквизита и товаров."
    slots:
      asset_type: "Тип материала"
      name: "Название материала; пусто для варианта"
      description: "Описание внешности или отличия от основного"
      style: "Художественный стиль проекта"
      style_description: "Описание стиля проекта"
  vi:
    title: "Ảnh tài sản"
    description: "Prompt đầy đủ cho ảnh tài sản nhân vật, biến thể nhân vật, cảnh, đạo cụ và sản phẩm."
    slots:
      asset_type: "Loại tài sản"
      name: "Tên tài sản; để trống với biến thể"
      description: "Mô tả ngoại hình hoặc thay đổi so với bản gốc"
      style: "Phong cách hình ảnh của dự án"
      style_description: "Mô tả phong cách dự án"
stage: asset_sheet
invoked_by:
  kind: generation_task
  name: asset
applies_to:
  asset_type:
  - character
  - character_derivative
  - scene
  - prop
  - product
slots:
  asset_type: 资产类型
  name: 资产名称，衍生为空
  description: 外观描述或相对本体的变化
  style: 项目画风
  style_description: 项目风格描述
protected: false
---
{{ variant("asset/sheet/style", asset_type) }}

{{ variant("asset/sheet/title", asset_type) }}

{{ description }}

{{ variant("asset/sheet/layout", asset_type) }}

{{ variant("asset/sheet/guard", asset_type) }}

Avoid: {{ variant("asset/sheet/exclusions", asset_type) }}{{ partial("shared/image_avoid") }}