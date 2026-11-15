---
id: reference_video/unit
category: video
title: 参考生视频
description: 参考生视频单元的完整提示词，由参考素材声明、单元正文、风格与负向约束三段组成。
i18n:
  zh-TW:
    title: "參考生影片"
    description: "參考生影片單元的完整提示詞，由參考素材宣告、單元正文、風格與負向限制三段組成。"
    slots:
      declarations: "第一段：主體綁定（<X>@图片N）、同一角色的形態宣告與聲音宣告（@音频N）；沒有參考素材時為空"
      body: "第二段：單元正文，mention 已換成主體記號，台詞記號已重組，旁白記號已捨棄"
      style: "專案畫風"
      style_description: "專案風格描述"
      co_present_characters: "同框的不同角色，本體與衍生合併算一個；不到兩個時為空"
      products: "隨請求送出參考圖的商品名稱，依首次出現順序去重；沒有商品參考圖時為空"
  en:
    title: "Reference-to-Video"
    description: "The full prompt for a reference-to-video unit, made of three parts: reference declarations, the unit body, and style with negative constraints."
    slots:
      declarations: "Part one: subject bindings (<X>@图片N), form declarations for the same character and voice declarations (@音频N); empty without reference material"
      body: "Part two: the unit body, with mentions replaced by subject marks, dialogue marks regrouped and narration marks dropped"
      style: "Project art style"
      style_description: "Project style description"
      co_present_characters: "Different characters in the same frame, a base and its variants counting as one; empty when fewer than two"
      products: "Names of products whose reference images are sent with the request, deduplicated in order of first appearance; empty without product reference images"
  ru:
    title: "Видео по референсу"
    description: "Полный промпт для блока видео по референсу из трёх частей: объявление референсов, текст блока, стиль и негативные ограничения."
    slots:
      declarations: "Часть первая: привязка субъектов (<X>@图片N), объявления облика одного персонажа и объявления голоса (@音频N); пусто без референсов"
      body: "Часть вторая: текст блока, упоминания заменены метками субъектов, метки реплик перегруппированы, метки закадрового текста удалены"
      style: "Художественный стиль проекта"
      style_description: "Описание стиля проекта"
      co_present_characters: "Разные персонажи в одном кадре, основной и его варианты считаются одним; пусто, если их меньше двух"
      products: "Названия товаров, чьи референсы отправляются с запросом, без повторов в порядке первого появления; пусто без референсов товаров"
  vi:
    title: "Video từ ảnh tham chiếu"
    description: "Prompt đầy đủ cho một đơn vị video từ ảnh tham chiếu, gồm ba phần: khai báo tư liệu tham chiếu, nội dung đơn vị, phong cách và ràng buộc loại trừ."
    slots:
      declarations: "Phần một: gắn chủ thể (<X>@图片N), khai báo hình thái của cùng nhân vật và khai báo giọng (@音频N); để trống khi không có tư liệu tham chiếu"
      body: "Phần hai: nội dung đơn vị, mention đã thay bằng ký hiệu chủ thể, ký hiệu lời thoại đã sắp xếp lại, ký hiệu thuyết minh đã bỏ"
      style: "Phong cách hình ảnh của dự án"
      style_description: "Mô tả phong cách dự án"
      co_present_characters: "Các nhân vật khác nhau cùng khung hình, bản gốc và biến thể tính là một; để trống nếu ít hơn hai"
      products: "Tên sản phẩm có ảnh tham chiếu gửi kèm yêu cầu, bỏ trùng theo thứ tự xuất hiện đầu tiên; để trống khi không có ảnh tham chiếu sản phẩm"
stage: reference_video
invoked_by:
  kind: generation_task
  name: reference_video
applies_to: {}
slots:
  declarations: 第一段：主体绑定（<X>@图片N）、同一角色的形态声明与声音声明（@音频N）；无参考素材时为空
  body: 第二段：单元正文，mention 已换成主体记号，台词记号已重组，旁白记号已丢弃
  style: 项目画风
  style_description: 项目风格描述
  co_present_characters: 同框的不同角色，本体与衍生合并计一个；不足两个时为空
  products: 随请求发出参考图的商品名，按首现顺序去重；无商品参考图时为空
protected: false
---
{{ declarations }}

{{ body }}

{{ partial("shared/media_style") }}
{{ partial("reference_video/unit/avoid") }}
{% if products %}

商品高保真还原（最高优先级，优先于前述文字/Logo 禁止项）：画面中的商品{{ partial("reference_video/unit/lists/products") }}必须与商品参考图完全一致——{{ partial("shared/product_fidelity") }}，不得重新设计或美化商品本身；前述文字/Logo 禁止项仅指画面中不得凭空新增文字或 Logo，商品参考图自带的文字与 Logo须原样保留；项目画风只作用于商品以外的画面元素。
{% endif %}
