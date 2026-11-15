---
id: text/style_analysis
category: text
title: 风格参考图分析
description: 从用户上传的风格参考图提炼画风描述，写入项目的风格描述。
i18n:
  zh-TW:
    title: "風格參考圖分析"
    description: "從使用者上傳的風格參考圖歸納出畫風描述，寫入專案的風格描述。"
  en:
    title: "Style reference analysis"
    description: "Distills an art style description from the style reference image the user uploaded and saves it as the project's style description."
  ru:
    title: "Анализ референса стиля"
    description: "Составляет описание художественного стиля по загруженному пользователем референсу и сохраняет его как описание стиля проекта."
  vi:
    title: "Phân tích ảnh tham chiếu phong cách"
    description: "Rút ra mô tả phong cách hình ảnh từ ảnh tham chiếu phong cách người dùng tải lên và lưu vào mô tả phong cách của dự án."
stage: style_analysis
invoked_by:
  kind: user_action
  name: style_analysis
applies_to: {}
slots: {}
protected: false
---
Analyze the visual style of this image. Describe the lighting, color palette, medium (e.g., oil painting, digital art, photography), texture, and overall mood. Do NOT describe the subject matter (e.g., people, objects) or specific content. Focus ONLY on the artistic style. Provide a concise comma-separated list of descriptors suitable for an image generation prompt.
