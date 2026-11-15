---
id: storyboard/grid
category: storyboard
title: 宫格联合图
description: 把一组分镜按首尾帧链画进一张宫格联合图的提示词，生成后按画格切回各分镜。
i18n:
  zh-TW:
    title: "宮格分鏡圖"
    description: "把一組分鏡依首尾影格串接畫進一張宮格分鏡圖的提示詞，生成後再依畫格切回各個分鏡。"
    slots:
      reference_images: "參考圖類型宣告，依隨請求送出的參考圖順序編號為「圖N」；沒有參考圖時為空"
      rows: "宮格列數"
      cols: "宮格欄數"
      cell_count: "畫格總數"
      grid_aspect_ratio: "整張宮格分鏡圖的比例"
      panel_aspect_ratio: "單個畫格的比例，由整張圖的比例與行列數算出"
      last_chain_cell: "影格鏈最後一格的序號；只有開場一格時為 0，不渲染過渡影格那一行"
      opening: "格 0 的開場分鏡（scene_id、description）"
      transitions: "過渡格清單（index、row、col、from_id、to_id、action、description）"
      placeholders: "空白佔位格清單（index、row、col）"
      style: "專案畫風"
      style_description: "專案風格描述"
  en:
    title: "Multi-grid storyboard"
    description: "The prompt that draws a group of shots into one grid image, chained by their first and last frames; after generation the image is cut back into the individual shots."
    slots:
      reference_images: "Reference image type declarations, numbered “image N” in the order the images are sent with the request; empty without reference images"
      rows: "Grid rows"
      cols: "Grid columns"
      cell_count: "Total number of panels"
      grid_aspect_ratio: "Aspect ratio of the whole grid image"
      panel_aspect_ratio: "Aspect ratio of one panel, computed from the whole image's ratio and the rows and columns"
      last_chain_cell: "Index of the last panel in the frame chain; 0 when there is only the opening panel, in which case the transition line is not rendered"
      opening: "The opening shot in panel 0 (scene_id, description)"
      transitions: "Transition panels (index, row, col, from_id, to_id, action, description)"
      placeholders: "Empty placeholder panels (index, row, col)"
      style: "Project art style"
      style_description: "Project style description"
  ru:
    title: "Раскадровка-сетка"
    description: "Промпт, который рисует группу кадров на одном изображении-сетке, связывая их по первым и последним кадрам; после генерации изображение разрезается обратно на отдельные кадры."
    slots:
      reference_images: "Объявление типов референсов, пронумерованных «изображение N» в порядке отправки с запросом; пусто, если референсов нет"
      rows: "Число строк сетки"
      cols: "Число столбцов сетки"
      cell_count: "Общее число ячеек"
      grid_aspect_ratio: "Соотношение сторон всего изображения-сетки"
      panel_aspect_ratio: "Соотношение сторон одной ячейки, рассчитанное по соотношению всего изображения и числу строк и столбцов"
      last_chain_cell: "Номер последней ячейки цепочки кадров; 0, если есть только начальная ячейка, тогда строка переходов не выводится"
      opening: "Начальный кадр в ячейке 0 (scene_id, description)"
      transitions: "Ячейки переходов (index, row, col, from_id, to_id, action, description)"
      placeholders: "Пустые ячейки-заполнители (index, row, col)"
      style: "Художественный стиль проекта"
      style_description: "Описание стиля проекта"
  vi:
    title: "Phân cảnh đa lưới"
    description: "Prompt vẽ một nhóm phân cảnh vào một ảnh lưới, nối theo khung đầu và khung cuối; sau khi tạo, ảnh được cắt lại thành từng phân cảnh."
    slots:
      reference_images: "Khai báo loại ảnh tham chiếu, đánh số “ảnh N” theo thứ tự gửi kèm yêu cầu; để trống nếu không có ảnh tham chiếu"
      rows: "Số hàng của lưới"
      cols: "Số cột của lưới"
      cell_count: "Tổng số ô"
      grid_aspect_ratio: "Tỷ lệ của toàn bộ ảnh lưới"
      panel_aspect_ratio: "Tỷ lệ của một ô, tính từ tỷ lệ toàn ảnh và số hàng, cột"
      last_chain_cell: "Số thứ tự ô cuối trong chuỗi khung hình; 0 khi chỉ có ô mở đầu, khi đó dòng khung chuyển tiếp không được kết xuất"
      opening: "Phân cảnh mở đầu ở ô 0 (scene_id, description)"
      transitions: "Danh sách ô chuyển tiếp (index, row, col, from_id, to_id, action, description)"
      placeholders: "Danh sách ô trống giữ chỗ (index, row, col)"
      style: "Phong cách hình ảnh của dự án"
      style_description: "Mô tả phong cách dự án"
stage: grid
invoked_by:
  kind: generation_task
  name: grid
applies_to: {}
slots:
  reference_images: 参考图类型声明，按随请求发出的参考图序位编号为「图N」；无参考图为空
  rows: 宫格行数
  cols: 宫格列数
  cell_count: 画格总数
  grid_aspect_ratio: 整张联合图的比例
  panel_aspect_ratio: 单个画格的比例，由整图比例与行列数算出
  last_chain_cell: 帧链最后一格的序号；只有开场一格时为 0，过渡帧行不渲染
  opening: 格0 的开场分镜（scene_id、description）
  transitions: 过渡格列表（index、row、col、from_id、to_id、action、description）
  placeholders: 空占位格列表（index、row、col）
  style: 项目画风
  style_description: 项目风格描述
protected: false
---
{% if reference_images %}
Reference_Images: {{ reference_images }}

{% endif %}
你是一位专业的分镜画师。请严格按照 {{ rows }}×{{ cols }} 宫格布局生成一张包含恰好 {{ cell_count }} 个等大画格的联合图。

【布局要求】
- 恰好 {{ rows }} 行 {{ cols }} 列，共 {{ cell_count }} 个画格，阅读顺序：从左到右，从上到下
- 整体图片比例：{{ grid_aspect_ratio }}
- 每个画格比例：{{ panel_aspect_ratio }}，所有画格大小完全相同
- 画格之间无边框、无间隙、无留白，紧密排列
- 不得合并画格、不得遗漏画格、不得错位排列
- 所有画格保持一致的角色外观、光线和色彩风格

【帧链节奏】
本宫格采用首尾帧链式结构：
- 格0 是第一个场景的开场画面
{% if last_chain_cell %}
- 格1~格{{ last_chain_cell }} 是相邻场景的过渡帧（前一场景的结束 = 后一场景的开始）
{% endif %}
- 相邻格之间应体现画面的自然过渡和动作延续

【各格内容】
格0（row1 col1）— {{ opening.scene_id }}开场：
  {{ opening.description }}
{{ partial("storyboard/grid/lists/cells") }}

{{ partial("shared/media_style") }}

{{ partial("storyboard/grid/avoid") }}
