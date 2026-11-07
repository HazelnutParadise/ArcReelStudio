"""專案變更事件的條目標籤文案。

事件載荷攜帶穩定的 ``label_key`` 與 ``label_params``，渲染邊界（前端介面 / 後端日誌兜底）
按各自語言查表成文，key 與 ``frontend/src/i18n/*/events.ts`` 的 ``label.*`` 一一對應。
"""

MESSAGES = {
    "event_label_grid": "多宮格分鏡「{id}」",
    "event_label_grid_split": "多宮格分鏡「{id}」切分",
    "event_label_voice_sample": "「{id}」試聽樣本",
    "event_label_asset_image_character": "角色「{id}」資產圖",
    "event_label_asset_image_scene": "場景「{id}」資產圖",
    "event_label_asset_image_prop": "道具「{id}」資產圖",
    "event_label_asset_image_product": "商品「{id}」資產圖",
    "event_label_asset_image_character_derivative": "角色衍生「{id}」資產圖",
    "event_label_skeleton_segments": "分鏡「{id}」",
    "event_label_skeleton_scenes": "分鏡「{id}」",
    "event_label_skeleton_shots": "分鏡「{id}」",
    "event_label_skeleton_video_units": "影片單元「{id}」",
    "event_label_narration_audio": "旁白配音「{id}」",
    "event_label_named_entity_character": "角色「{id}」",
    "event_label_named_entity_scene": "場景「{id}」",
    "event_label_named_entity_prop": "道具「{id}」",
    "event_label_named_entity_product": "商品「{id}」",
    "event_label_named_entity_character_derivative": "角色衍生「{id}」",
    "event_label_character_reference_audio": "角色「{id}」參考音訊",
    "event_label_project_settings": "專案設定",
    "event_label_overview": "專案概覽",
    "event_label_episode": "集（id={episode}）",
    "event_label_draft_normalized_script": "集（id={episode}）的規範化腳本",
    "event_label_draft_segment_splitting": "集（id={episode}）的分鏡拆分",
    "event_label_draft_script_plan": "集（id={episode}）的腳本規劃草稿",
    "event_label_draft_prompt_authoring": "集（id={episode}）的提示詞編寫草稿",
}
