"""校驗與歸檔診斷訊息（中文）。

由 ``lib.project.data_validator`` / ``server.services.project.project_archive`` / ``lib.script.script_skeleton``
以 ``arcreel_market_core.validation_messages.ValidationMessage`` 的形式產出、在各消費邊界渲染。
"""

MESSAGES = {
    # ---- 透傳 ----
    "val_literal": "{text}",
    # ---- 通用欄位形狀 ----
    "val_missing_field": "缺少必填欄位：{field}",
    "val_missing_field_at": "{prefix}: 缺少必填欄位 {field}",
    "val_field_type_string": "欄位型別錯誤：{field} 應為字串",
    "val_field_type_bool": "欄位型別錯誤：{field} 應為布林值",
    "val_field_type_number": "欄位型別錯誤：{field} 應為數字",
    "val_field_type_integer": "欄位型別錯誤：{field} 應為整數",
    "val_field_out_of_range": "{field} 的值 {value} 超出範圍，應在 {min} 到 {max} 之間",
    "val_field_must_be_string": "{field} 必須是字串",
    "val_field_must_be_string_typed": "{field} 必須是字串，當前為 {actual}",
    "val_field_must_be_array": "{field} 必須是陣列",
    "val_field_must_be_nonempty_array": "{field} 必須是非空陣列",
    "val_field_must_be_nonempty_string": "{field} 必須是非空字串",
    "val_field_must_be_object": "{field} 必須是物件",
    "val_field_invalid": "{field} 不合法：{detail}",
    "val_ledger_source_file_not_relative": "source_file 必須是專案內相對 POSIX 路徑",
    "val_ledger_source_file_escapes": "source_file 不能是絕對路徑或包含 ..",
    "val_ledger_start_after_end": "start 不能大於 end",
    "val_field_bad_timestamp": "{field} 不是合法的 ISO8601 時間戳：{value}",
    "val_item_must_be_object": "{prefix}: 必須是物件",
    "val_item_format_object": "{prefix}: 資料格式錯誤，應為物件",
    # ---- 路徑引用 ----
    "val_path_empty": "{field}: 路徑不能為空",
    "val_path_traversal": "{field}: 引用路徑越界：{path}",
    "val_path_outside_dir": "{field}: 引用路徑必須位於 {dir}/ 目錄下：{path}",
    "val_path_missing": "{field}: 引用的檔案不存在：{path}",
    "val_path_must_be_relative": "{field} 必須是專案內相對路徑：{path}",
    # ---- 專案級欄位 ----
    "val_content_mode_invalid": "content_mode 值無效：'{value}'，必須是 {allowed}",
    "val_source_kind_invalid": "{prefix}: source_kind 值無效：'{value}'，必須是 {allowed}",
    "val_generation_mode_invalid": "generation_mode 值無效：'{value}'，必須是 {allowed}",
    "val_deprecated_clues": "project.json 含已廢棄欄位 clues，請等待自動遷移或手動重啟服務",
    "val_deprecated_field_removable": "{field} 欄位已廢棄（改為讀時計算），可安全移除",
    "val_cannot_load_project_json": "無法載入 project.json",
    "val_cannot_load_script": "無法載入腳本檔案：{path}",
    "val_unrecognized_entry": "發現未識別的附加檔案/目錄：{name}",
    "val_novel_must_be_object": "novel 欄位必須是物件",
    # ---- 劇集條目與帳本 ----
    "val_ledger_status_type": "{prefix}: ledger_status 必須是字串，當前取值：{value}",
    "val_source_origin_invalid": "{prefix}: source_origin 值無效：'{value}'，必須是 {allowed}",
    "val_source_range_requires_whole_source": "{prefix}: 只有切自整本源文（source_origin 為 whole_source）的集可以帶 source_range",
    "val_whole_source_file_invalid": "whole_source_files[{index}] 必須是帶 source_file 的物件，檔案直接位於 source/ 下，副檔名為 .txt 或 .md",
    "val_episode_missing_num_at": "{prefix}: 缺少必填欄位 episode (整數)",
    "val_episode_missing_title_at": "{prefix}: 缺少必填欄位 title (字串，可為空)",
    "val_episode_missing_num": "缺少必填欄位：episode (整數)",
    # ---- 廣告/短片專案 ----
    "val_ad_only_field": "{field} 僅廣告/短片專案（content_mode=ad）可用",
    "val_ad_missing_target_duration": "缺少必填欄位：target_duration（廣告/短片專案的目標總時長，秒）",
    "val_ad_target_duration_invalid": "target_duration 值無效：{value}，必須為正整數秒",
    "val_ad_no_default_duration": "廣告/短片專案不持有 default_duration（分鏡時長按 target_duration 預算逐個分鏡規劃）",
    "val_ad_no_episode_target_duration": "廣告/短片專案不持有 episode_target_duration（整集體量按 target_duration 預算規劃）",
    "val_ad_no_grid_storyboard": "廣告/短片專案不支援多宮格分鏡（grid_storyboard）",
    "val_ad_episodes_single": "廣告/短片專案 episodes 必須恆為第 1 集單條",
    "val_ad_shots_missing": "ad 腳本缺少 shots 陣列",
    "val_ad_duration_drift": (
        "腳本總時長 {total} 秒與 target_duration {target} 秒偏差 {delta:.0%}，"
        "超過 {threshold:.0%} 觀察閾值（僅提示，不阻塞儲存）"
    ),
    # ---- 資產目錄 ----
    "val_asset_format_object": "{asset_type} '{name}' 資料格式錯誤，應為物件",
    "val_asset_field_must_be_object": "{asset_type} '{name}'.{field} 必須是物件",
    "val_asset_field_must_be_string": "{asset_type} '{name}'.{field} 必須是字串，當前為 {actual}",
    "val_asset_field_bad_timestamp": "{asset_type} '{name}'.{field} 不是合法的 ISO8601 時間戳：{value}",
    "val_asset_field_must_be_string_list": "{asset_type} '{name}'.{field} 必須是字串清單，當前為 {actual}",
    "val_asset_field_item_must_be_string": "{asset_type} '{name}'.{field}[{index}] 必須是字串，當前為 {actual}",
    "val_asset_name_duplicate": (
        "專案資產名稱重複：{duplicate_type}「{duplicate_name}」與{first_type}「{first_name}」"
        "按 strip + Unicode NFC 判定同名"
    ),
    # ---- 條目級引用 ----
    "val_refs_unregistered": "{prefix}: {field} 引用了不存在於 project.json 的{asset_type}: {names}",
    "val_missing_defaults_empty_array": "{prefix}: 缺少 {field}，將使用預設空陣列",
    # ---- 條目通用 ----
    "val_id_format": "{prefix}: {field} 格式錯誤 '{value}'，應為 E{{n}}S{{nn}}",
    "val_missing_duration_default": "{prefix}: 缺少 duration_seconds，將使用預設值 {default}",
    "val_duration_invalid": "{prefix}: duration_seconds 值無效 '{value}'，必須為正整數",
    # ---- drama utterances ----
    "val_utterance_must_be_object": "{prefix} 必須是物件",
    "val_utterance_kind_invalid": "{prefix} kind 必須是 dialogue 或 voiceover",
    "val_utterance_text_invalid": "{prefix} text 必須是非空字串",
    "val_utterance_speaker_type": "{prefix} speaker 必須是字串或 null",
    "val_utterance_dialogue_speaker": "{prefix} dialogue 必須帶非空 speaker",
    "val_utterance_voiceover_speaker": "{prefix} voiceover 不得帶 speaker",
    "val_scene_speech_overflow": (
        "{prefix}: 估算說話時長 {spoken:.1f} 秒超過分鏡時長 {duration} 秒逾 {tolerance:.0%}"
        "（容差上界 {budget:.1f} 秒），長對白可能說不完或語速畸快（僅提示，不阻塞儲存）"
    ),
    # ---- ad 分鏡 ----
    "val_shot_duration_missing_zero": "{prefix}: 缺少 duration_seconds，將按 0 計入總時長",
    "val_shot_duration_out_of_range": (
        "{prefix}: duration_seconds 值無效 '{value}'，reference_video 路徑必須是 {low}～{high} 之間的整數"
    ),
    "val_shot_missing_voiceover_text": "{prefix}: 缺少必填欄位 voiceover_text（口播文案，可為空字串）",
    # ---- 參考生影片單元 ----
    "val_unit_id_missing": "{prefix}: 缺少 unit_id",
    "val_unit_id_missing_required": "{prefix}: 缺少必填欄位 unit_id",
    "val_unit_id_duplicate": "{prefix}: unit_id 重複 '{value}'",
    "val_video_units_missing": "reference_video 腳本缺少 video_units 陣列",
    "val_unit_duration_range": "{prefix}: duration_seconds 必須是 {low}～{high} 之間的整數",
    # ---- 骨架與生成模式失配 ----
    "val_skeleton_noun_segments": "分鏡",
    "val_skeleton_noun_scenes": "分鏡",
    "val_skeleton_noun_shots": "分鏡",
    "val_skeleton_noun_video_units": "影片單元",
    "val_route_reference_video": "參考生影片（reference_video）",
    "val_route_storyboard": "分鏡圖生影片（storyboard）",
    "val_skeleton_mismatch_reference_known": (
        "腳本骨架與專案生成模式不符：專案生成模式是{route}，要求 {expected}（{expected_noun}）骨架，"
        "當前腳本是 {actual}（{actual_noun}）骨架。"
        "請呼叫 generate_script_plan 重新拆分該集，再重新生成腳本。該腳本仍可檢視、編輯與匯出。"
    ),
    "val_skeleton_mismatch_reference_none": (
        "腳本骨架與專案生成模式不符：專案生成模式是{route}，要求 {expected}（{expected_noun}）骨架，"
        "當前腳本沒有任何骨架陣列。"
        "請呼叫 generate_script_plan 重新拆分該集，再重新生成腳本。該腳本仍可檢視、編輯與匯出。"
    ),
    "val_skeleton_mismatch_storyboard_known": (
        "腳本骨架與專案生成模式不符：專案生成模式是{route}，要求 {expected}（{expected_noun}）骨架，"
        "當前腳本是 {actual}（{actual_noun}）骨架。"
        "請重跑分集拆分（script_plan）重新拆分該集，再重新生成腳本。該腳本仍可檢視、編輯與匯出。"
    ),
    "val_skeleton_mismatch_storyboard_none": (
        "腳本骨架與專案生成模式不符：專案生成模式是{route}，要求 {expected}（{expected_noun}）骨架，"
        "當前腳本沒有任何骨架陣列。"
        "請重跑分集拆分（script_plan）重新拆分該集，再重新生成腳本。該腳本仍可檢視、編輯與匯出。"
    ),
    # ---- 參考生影片時長收編遷移 ----
    "val_unit_duration_clamped": "unit {unit_id} 時長 {target}s 超出 {low}～{high}s 合理區間，已裁剪為 {clamped}s",
    "val_unit_duration_slotted": ("unit {unit_id} 時長 {duration}s 不是模型檔位（{durations}）成員，已取檔為 {slot}s"),
    # ---- 歸檔修復與匯入匯出診斷 ----
    "arch_source_encoding_unconverted": "原始檔編碼無法識別，未轉換為 UTF-8：source/{name}（分集規劃無法讀取該檔案）",
    "arch_provider_asset_links_not_restored": "專案已匯入，但 {count} 條供應商素材關聯沒能儲存，生成時這些圖片照常傳送圖片內容；需要時重新上傳或從素材庫選擇",
    "arch_non_standard_entry_excluded": "非標準頂層目錄/檔案 '{entry}' 未包含在匯出中",
    "arch_invalid_project_json": "無法解析 {file}",
    "arch_version_history_malformed": "{location}: 版本歷史的結構不符合預期格式",
    "arch_version_snapshot_path_unmanaged": "{location}: 版本記錄的快照路徑不在該資源型別的版本目錄內",
    "arch_script_file_repaired": "{location}: 自動修復為 {path}",
    "arch_missing_script_file_pending": "{location}: 腳本尚未生成：{path}",
    "arch_missing_script_file": "{location}: 引用的檔案不存在：{path}",
    "arch_invalid_script_json": "無法解析腳本檔案：{path}",
    "arch_deprecated_source_file_removed": "novel.source_file 欄位已廢棄，已移除",
    "arch_deprecated_field_removed": "{field} 欄位已廢棄（改為讀時計算），已移除",
    "arch_missing_field_filled": "{items_key}[{index}]: 補全缺失欄位 {field}",
    "arch_unit_unresolved_mentions": (
        "video_units[{index}]: 正文引用了不存在於 project.json 的資產名：{names}；這些引用不會生成參考圖"
    ),
    "arch_generated_assets_defaults": "{label}[{index}].generated_assets: 補全預設欄位 {fields}",
    "arch_missing_generated_assets": "{label}[{index}]: 補全缺失欄位 generated_assets",
    "arch_invalid_generated_assets": "{label}[{index}]: generated_assets 形態異常（{actual}），已重設為預設結構",
    "arch_placeholder_character_added": "自動補充缺失角色定義：{name}",
    "arch_placeholder_asset_added": "自動補充缺失{asset_type}定義：{name}",
    "arch_canonical_path_normalized": "{location}: 規範化為 {path}",
    "arch_current_asset_materialized": "{location}: 從 {source} 恢復當前檔案 {target}",
    "arch_current_asset_restored_from_version": "{location}: 從 {source} 恢復當前檔案 {target}",
    "arch_version_snapshot_restored": "{target}：版本 v{version} 的版本檔案不見了或與版本紀錄不符，{source} 與版本紀錄的內容指紋一致，已依它補回",
    "arch_manifest_unreadable_exported_from_files": "產物清單讀不出來，歸檔依專案裡的檔案重新整理產物登記：影片與配音依版本紀錄裡的產生依據判定，已過期的匯入後仍顯示為已過期；其他產物沒有別處記著產生依據，匯入後顯示為最新，原本的已過期標記不會保留",
    "arch_claim_left_out_unreadable": "{path}：檔案是符號連結或無法安全讀取（來源專案裡顯示為無法讀取），歸檔不帶它和它的登記；匯入後顯示為缺少",
    "arch_missing_reference_cleared": "{location}：引用的檔案 {path} 已不在專案裡，也沒有可還原的版本，歸檔裡清空這條引用；匯入後與現在一樣顯示為缺少",
    "arch_symlink_reference_cleared": "{location}：引用的檔案 {path} 是符號連結，歸檔不帶連結指向的內容，清空這條引用；來源專案裡它顯示為無法讀取，匯入後顯示為缺少",
    "arch_version_record_dropped": "{location}：有版本紀錄的檔案路徑不在版本歷史目錄裡，匯入會拒收，歸檔裡拿掉這幾筆紀錄；其餘版本照常帶上",
    "arch_claim_imported_as_stale": "{path}：包裡沒有能核對的所選版本檔案（缺少或與版本紀錄不符），以已過期匯入，仍可檢視和使用；在版本歷史裡切回該版本即可恢復為最新",
    "arch_claim_carried_as_stale": "{path}：無法確認它仍是所選版本（版本檔案不見了、與版本紀錄不符，或版本紀錄缺漏），檔案與登記照常帶上；匯入後顯示為已過期，仍可檢視和使用",
    "arch_claim_left_out_missing": "{path}：檔案已不在專案裡，歸檔不帶它的登記；匯入後與現在一樣顯示為缺少",
    "arch_presentation_claim_left_out": "{path}：與它依據的影片或配音版本對不上，歸檔不帶它的登記；匯入後預覽、剪輯或匯出剪映草稿時，會在本機依當時選取的媒體重新產生，不會產生費用",
    "arch_old_version_presentation_claim_left_out": "{path}：依據的是舊版本的影片或配音，僅目前版本的歸檔不含舊版本，不帶它的登記；匯入後用到時會在本機依當時選取的媒體重新產生，不會產生費用",
    "arch_claim_left_out_unverifiable": "{path}：無法核對這件產物的登記，歸檔只帶檔案、不帶登記；匯入時依檔案重新判定，能重新登記的顯示為最新，否則顯示為缺少",
    # ---- 歸檔匯入異常 ----
    "arch_invalid_conflict_policy": "無效的衝突策略",
    "arch_conflict_policy_unsupported": "conflict_policy 僅支援 prompt、rename 或 overwrite，收到：{value}",
    "arch_import_validation_failed": "匯入包校驗失敗",
    "arch_artifact_activation_failed": "匯入專案的產物狀態不一致：{reason}",
    "arch_project_migration_failed": "匯入包裡的專案資料無法升級到當前版本：{reason}",
    "arch_project_schema_unsupported": (
        "匯入包裡的專案是 schema 版本 {version}，這個版本只能匯入 {minimum} 以上的專案。請先在上游 ArcReel 開啟這個專案，讓它升級到 schema {minimum} 或更新的版本，再重新匯出後匯入"
    ),
    "arch_import_confirmation_required": "匯入包升級時調整了部分內容，請確認後再匯入",
    "arch_not_a_zip": "上傳檔案不是有效的 ZIP 歸檔",
    "arch_zip_encrypted_entry": "ZIP 包含加密條目，無法匯入：{name}",
    "arch_zip_absolute_path_entry": "ZIP 包含絕對路徑條目：{name}",
    "arch_zip_traversal_entry": "ZIP 包含路徑穿越條目：{name}",
    "arch_zip_symlink_entry": "ZIP 包含符號連結條目：{name}",
    "arch_zip_unparsable_member": "無法解析 {label}: {path}",
    "arch_multiple_manifests": "ZIP 中包含多個 arcreel-export.json，無法確定專案根目錄",
    "arch_manifest_missing_project_json": "官方匯出包缺少 project.json",
    "arch_no_project_json": "ZIP 中未找到 project.json",
    "arch_multiple_project_json": "ZIP 中包含多個 project.json，無法確定專案根目錄",
    "arch_extract_path_traversal": "解壓路徑越界：{path}",
    "arch_conflict_detected": "檢測到專案編號衝突",
    "arch_project_name_conflict": "專案編號 '{name}' 已存在，請選擇覆蓋現有專案或自動重新命名匯入。",
    # ---- 自定義呼叫端點 · 定義校驗 ----
    "val_ce_missing_field": "缺少必填欄位：{field}",
    "val_ce_unknown_field": "不認識的欄位：{field}",
    "val_ce_removed_field": "欄位已移除：{field}——{reason}",
    "val_ce_invalid_type": "型別不符，應為 {expected}",
    "val_ce_invalid_enum_value": "取值不在允許範圍內，可選：{allowed}",
    "val_ce_invalid_value": "取值不符合格式約定：{detail}",
    "val_ce_schema_violation": "不符合定義格式：{detail}",
    "val_ce_schema_minimum_constraint": "允許的最小值或數量：{limit}",
    "val_ce_schema_maximum_constraint": "允許的最大值或數量：{limit}",
    "val_ce_schema_format_constraint": "不符合要求的格式：{constraint}",
    "val_ce_schema_forbidden_constraint": "取值落入了禁止範圍",
    "val_ce_schema_generic_constraint": "未滿足定義約束（{keyword}）",
    "val_ce_removed_reason_request_query": "靜態與動態 query 都寫進 url 範本，憑證 query 歸 auth.query",
    "val_ce_removed_reason_status_codes": "HTTP 碼策略歸執行時：2xx 成功、429 與 5xx 重試、其餘失敗",
    "val_ce_removed_reason_polling_policy": "輪詢間隔與超時是執行時策略，不進定義",
    "val_ce_removed_reason_extract_source": "取值根一律是響應體，HTTP 狀態碼不走 JSONPath",
    "val_ce_removed_reason_extract_usage_keys": "用量改掛 poll.extract.usage",
    "val_ce_removed_reason_mime_types": "素材格式不做白名單，由供應商在提交時拒絕",
    "val_ce_removed_reason_comfyui_capabilities": "ComfyUI 端點的能力只從節點繫結推導，定義不存能力宣告",
    "val_ce_malformed_placeholder": (
        "{fragment} 不是合法佔位符：只支援裸變數（如 prompt、inputs.first_frame），"
        "沒有過濾器、下標與表示式，開括號也必須閉合"
    ),
    "val_ce_undeclared_variable": "佔位符 {name} 引用了未宣告的變數",
    "val_ce_api_key_outside_auth": "api_key 只能出現在 auth 節：憑證不進請求體與 URL，分享出去的定義也不該帶上它",
    "val_ce_auth_without_api_key": "auth 節非空卻沒有引用 api_key：無憑證介面請把這一節留空，否則讓它寫入憑證",
    "val_ce_auth_header_conflict": "{header} 與 auth.headers 同名（不區分大小寫）：憑證 header 只能由 auth 節寫入",
    "val_ce_header_name_duplicate": "{header} 與同表裡的 {first} 只差大小寫：HTTP 頭名不區分大小寫，兩條會一起發出去",
    "val_ce_auth_query_conflict": "URL 自帶的 query 引數 {param} 與 auth.query 同名：憑證 query 只能由 auth 節寫入",
    "val_ce_auth_query_reserved": "auth.query 的 {param} 與取產物那一跳自帶的引數同名：下載時憑證會被它頂掉，請換一個引數名",
    "val_ce_task_id_out_of_scope": "task_id 只在 poll 與 result 節可用",
    "val_ce_result_id_out_of_scope": "result_id 只在 result 節可用",
    "val_ce_result_id_without_extract": "引用了 result_id，但 poll.extract 沒有宣告 result_id",
    "val_ce_input_out_of_scope": "素材 {name} 只能在 submit 節引用：輪詢與取件請求不攜帶素材",
    "val_ce_list_input_requires_each": "{name} 是清單型素材，只能經 $each 展開，不能直接內插",
    "val_ce_each_in_not_list_input": "$each.in 指向的 {name} 不是已宣告的清單型素材",
    "val_ce_each_shape_invalid": "$each 要麼寫 item 鋪成陣列元素，要麼同時寫 key 與 value 鋪成鍵值對，兩種寫法不能混用",
    "val_ce_each_position_mismatch": (
        "$each 的寫法與所在位置不符：陣列位置寫 item 鋪成元素，物件位置寫 key 與 value 鋪成鍵值對"
    ),
    "val_ce_each_alias_reserved": "{name} 是迴圈體內的保留變數，不能用作 $each 的元素別名",
    "val_ce_when_unknown_input": "$when 指向的 {name} 不是已宣告的素材",
    "val_ce_input_not_referenced": "聲明瞭素材卻沒有在 submit 裡引用：既不會發給供應商，也不能據此宣告能力",
    "val_ce_enum_map_variable_not_allowed": "{variable} 不支援列舉對映，可對映的變數：{allowed}",
    "val_ce_default_variable_not_allowed": "{variable} 不支援預設值，可宣告預設值的變數：{allowed}",
    "val_ce_default_value_type_invalid": "{variable} 的預設值須是 {expected} 型別",
    "val_ce_default_value_not_in_enum_map": "{variable} 的預設值 {value} 不在 enum_maps 表內，可用的值：{allowed}",
    "val_ce_status_map_target_invalid": "狀態檔位 {target} 不在 {allowed} 之內，過期語義請對映到 failed",
    "val_ce_capability_declared_without_input": "聲明瞭 {capability}，但 submit 沒有引用任何 {source} 素材，能力會撒謊",
    "val_ce_capability_input_without_declaration": (
        "submit 引用了 {source} 素材，卻沒有宣告 {capability}，素材會發出去而介面不開放該能力"
    ),
    "val_ce_capability_incoherent": "能力 {capability} 與同組宣告矛盾，須滿足：{requirement}",
    "val_ce_capability_not_declared": "須在 capabilities 中把至少一項能力宣告為 true：{allowed}",
    "val_ce_media_type_field_not_allowed": "{name} 不適用於媒體型別為 {media_type} 的定義",
    "val_ce_artifact_extract_missing": "缺少產物提取路徑，至少寫一項：{keys}",
    "val_ce_jsonpath_not_a_string": "取值路徑必須是字串：{path_expression}",
    "val_ce_jsonpath_surrounding_whitespace": "取值路徑首尾不得有空白：{path_expression}",
    "val_ce_jsonpath_missing_root": "取值路徑必須以 $ 開頭：{path_expression}",
    "val_ce_jsonpath_recursive_descent": "取值路徑停用遞迴下降（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_union": "取值路徑停用聯合選擇器（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_slice_step": "取值路徑停用切片步長（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_function_extension": "取值路徑停用函式擴充套件（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_filter_root_reference": "過濾器內不得引用根節點（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_filter_non_singular": "過濾器內只允許單值查詢（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_regex_operator": "取值路徑停用正則匹配運算子（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_syntax": "取值路徑語法錯誤（第 {position} 個字元）：{path_expression}",
    "val_ce_jsonpath_evaluation_failed": "取值路徑求值失敗：{path_expression}",
    "val_ce_template_render_failed": "請求範本渲染失敗：{detail}",
    "val_ce_auth_literal_credential": "該值疑似直接填寫了真實金鑰：請改用 api_key 佔位符引用憑證，否則匯出或分享定義時會洩露該金鑰",
    "val_ce_template_url_not_string": "URL 範本必須渲染為字串",
    "val_ce_unknown_asset_encoding": "未知素材編碼：{encoding}",
    "val_ce_enum_map_value_missing": "enum_maps.{name} 缺少 '{value}' 的對映",
    "val_ce_template_text_variable_null": "變數 {name} 為空，不能嵌入混合文字",
    "val_ce_each_value_not_list": "$each.in 指向的 {name} 在執行時不是清單",
    "val_ce_each_key_duplicate": "物件式 $each 鋪出的鍵 {field} 與同一物件裡的其他鍵重名，請求無法承載全部素材",
    # ---- ComfyUI 端點 · 節點繫結與匯入分流 ----
    "val_ce_comfyui_binding_required": "語義鍵 {binding_key} 必須繫結到節點後才能儲存：提示詞決定畫什麼，產物決定取哪個檔案",
    "val_ce_comfyui_binding_key_not_allowed": "{media_type} 端點沒有 {binding_key} 這一項語義，可用的語義鍵：{allowed}",
    "val_ce_comfyui_node_not_found": "workflow 裡沒有節點 {node}：workflow 改過之後節點 id 會變，請重新匯入並確認節點繫結",
    "val_ce_comfyui_input_not_found": "節點 {node} 沒有名為 {input} 的輸入",
    "val_ce_comfyui_input_is_link": "節點 {node} 的 {input} 接的是上游連線，填進去的值執行時會被上游覆蓋：請綁到字面值欄位",
    "val_ce_comfyui_target_collision": (
        "節點 {node} 的 {input} 已經是 {owner} 的寫入落點，{binding_key} 不能再寫同一個欄位：後填的值會蓋掉先填的"
    ),
    "val_ce_comfyui_class_type_mismatch": (
        "條目記的節點 {node} 是 {class_type}，workflow 裡它現在是 {actual}：重匹配按型別認身份，"
        "對不上會把繫結搬到別的節點上。請重新匯入並確認節點繫結"
    ),
    "val_ce_comfyui_consumer_not_fed": (
        "參考圖節點 {node} 的圖流並沒有接到節點 {consumer} 的 {input} 入口：記錯了消費者，"
        "張數變少時會按一個不相干的入口去改圖"
    ),
    "val_ce_comfyui_fps_conflict": (
        "幀率有多個互相矛盾的來源（{values}）：時長換算成幀數只能按一個幀率，請只保留一處幀率來源"
    ),
    "val_ce_comfyui_ui_format_workflow": "這是 ComfyUI 的 UI 格式 workflow，提交不了：請在 ComfyUI 裡改用「Export (API)」匯出",
    # ---- ComfyUI 端點 · 節點繫結推斷的訊號說明與提示 ----
    "val_ce_infer_manual_binding": "已儲存的節點繫結，沿用使用者確認過的落點",
    "val_ce_infer_title_marker": "節點標題帶 ARCREEL: 標記，按標記認定",
    "val_ce_infer_external_node_family": "{family} 的引數化節點，宣告的引數名是 {parameter}",
    "val_ce_infer_sampler_port_trace": "從節點 {node} 的 {port} 條件埠反溯到這裡",
    "val_ce_infer_alias_with_class_type": "{class_type} 是這項語義的常見承載節點",
    "val_ce_infer_alias_only": "欄位名 {input} 是這項語義的常見叫法",
    "val_ce_infer_link_trace": "它的輸出接到節點 {consumer} 的 {input} 入口",
    "val_ce_infer_class_type_tier": "{class_type} 在同類候選裡更可信",
    "val_ce_infer_output_chain": "它在最終產物那條鏈路上",
    "val_ce_infer_title_polarity": "節點標題「{title}」指向這一極",
    "val_ce_infer_note_reference_consumer_unknown": (
        "參考圖接進節點 {node}（{class_type}）的 {input} 入口，這種入口在張數變少時改不動圖："
        "實際張數少於格子數時會重複填充最後一張"
    ),
    "val_ce_infer_note_batch_size_above_one": (
        "節點 {node}（{class_type}）的 {input} 是 {value}，一次提交會出多張圖；ArcReel 不改這個值"
    ),
    "val_ce_infer_note_manual_only_node": "節點 {node} 是 {class_type}，它承載的 {binding_keys} 推斷不出來，請手動繫結",
    "val_ce_infer_note_computed_source": (
        "{binding_key} 的候選落在節點 {node} 的 {input} 上，但它的值由上游計算節點算出、寫不進去，請手動指定"
    ),
    "val_ce_infer_note_rematched": "{binding_key} 的條目已重匹配到新節點 {nodes}",
    "val_ce_infer_note_binding_lost": (
        "{binding_key} 的條目在新 workflow 裡找不到落點（原節點 {nodes}），已重跑推斷，請確認"
    ),
    "val_ce_infer_note_target_taken": (
        "{binding_key} 的候選落在節點 {node} 的 {input} 上，而 {others} 也要寫這個欄位；"
        "同一個欄位只能寫一項語義，已把它從 {binding_key} 的候選裡去掉"
    ),
    "val_ce_poll_without_task_id": "輪詢請求沒有引用 task_id，請確認這是有意的",
    "val_ce_jsonpath_wildcard_order": (
        "{path_expression} 含通配：物件通配只取首個，鍵序在前端預覽與後端執行之間可能不同"
    ),
    # ---- 市場源校驗 ----
    "val_market_index_unreadable": "無法讀取索引檔案：{detail}",
    "val_market_unsupported_schema_version": "索引格式版本 {version} 高於本工具支援的 {supported}",
    "val_market_missing_field": "缺少必填欄位：{field}",
    "val_market_invalid_type": "型別錯誤，應為 {expected}",
    "val_market_invalid_value": "取值不符合約束 {keyword}：{constraint}",
    "val_market_slug_invalid": "slug「{value}」不合規：只允許小寫字母、數字與連字元，以字母或數字開頭，最長 64 個字元",
    "val_market_slug_duplicate": "slug「{slug}」在本市場源內重複",
    "val_market_slug_directory_mismatch": "slug「{slug}」與定義所在目錄名「{directory}」不一致",
    "val_market_path_not_relative": "「{value}」必須是市場源內的相對路徑：不能以 / 或協議開頭，不能含 ..，不能指向源外",
    "val_market_file_missing": "引用的檔案不存在：{value}",
    "val_market_symlink_not_allowed": "「{value}」是符號連結：客戶端經 GitHub raw 抓取時只能拿到連結目標路徑文字，請改為實體檔案或目錄",
    "val_market_icon_format_invalid": "圖示必須是可讀取的 PNG、WebP 或 SVG，且副檔名與內容一致",
    "val_market_icon_too_large": "圖示 {size} 位元組，超過上限 {limit} 位元組",
    "val_market_icon_not_square": "圖示必須是正方形，當前 {width}×{height}",
    "val_market_icon_ambiguous": "條目目錄裡只能有一個圖示檔案，發現：{icons}",
    "val_market_definition_unreadable": "無法讀取定義：{detail}",
    "val_market_definition_invalid": "定義未通過校驗（{code}）：{detail}",
    "val_market_projection_mismatch": "索引欄位 {field} 為「{index_value}」，與定義 meta 的「{definition_value}」不一致",
    "val_market_min_app_version_invalid": "min_app_version「{value}」不是 semver（x.y.z）",
    "val_market_detail_meta_not_object": "定義缺少 meta 物件",
    "val_market_cli_check_passed": "市場源校驗通過：{directory}",
    "val_market_cli_check_failed": "市場源校驗未通過，共 {count} 個問題",
    "val_market_cli_generate_written": "已寫入 {path}（{count} 個條目）",
    "val_market_cli_generate_failed": "無法生成索引，共 {count} 個問題",
}
