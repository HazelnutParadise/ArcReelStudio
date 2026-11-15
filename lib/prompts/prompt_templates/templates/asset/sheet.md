---
id: asset/sheet
category: asset
title: 资产图
description: 角色、角色衍生、场景、道具与商品资产图的完整提示词。
i18n:
  zh-TW:
    title: "資產圖"
    description: "角色、角色衍生、場景、道具與商品資產圖的完整提示詞。"
  en:
    title: "Asset image"
    description: "The full prompt for character, character variant, scene, prop and product asset images."
  ru:
    title: "Изображение материала"
    description: "Полный промпт для изображений персонажей, их вариантов, сцен, реквизита и товаров."
  vi:
    title: "Ảnh tài sản"
    description: "Prompt đầy đủ cho ảnh tài sản nhân vật, biến thể nhân vật, cảnh, đạo cụ và sản phẩm."
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