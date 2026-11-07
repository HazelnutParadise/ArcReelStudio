import type enOnboarding from '@/i18n/en/onboarding';

export default {
  // 引導步驟
  'welcome_title': '歡迎使用 [[brand]]',
  'welcome_body':
    '[[brand]] 把小說或劇本製作成短影片。製作由 Agent（代理）執行，每一步都可以人工調整。本引導介紹主要介面和基本流程。',
  'lobby_create_title': '新增專案',
  'lobby_create_body':
    '在這裡新增專案，依次設定基礎資訊、生成設定和畫面風格。要開啟之前匯出的專案，從右側下拉選單選擇「匯入 ZIP」。',
  'lobby_settings_title': '設定',
  'lobby_settings_body': '開始製作前需要完成兩項設定。按鈕上的紅點表示還有必填項未設定。',
  'settings_providers_title': '設定供應商',
  'settings_providers_body':
    '文字、圖片、影片和音訊模型都由這裡的供應商提供。至少設定一個供應商：填入金鑰，並點「測試」確認可用。',
  'settings_agent_title': '設定 [[brand]] Agent',
  'settings_agent_body': '[[brand]] Agent 能完成 [[brand]] 中的全部製作任務。在這裡新增一個 Agent 供應商並填入金鑰。',
  'lobby_demo_title': '演示專案',
  'lobby_demo_body': '點選卡片開啟演示專案，檢視製作介面。',
  'workbench_overview_title': '專案概覽',
  'workbench_overview_body':
    '這裡是從原文自動提煉的梗概、型別、主題和世界觀，可以直接修改。下方顯示資產圖的完成情況和費用，每一集的狀態在側欄檢視。',
  'workbench_agent_title': 'Agent',
  'workbench_agent_body':
    '右側是 Agent 面板。在對話中把任務交給 Agent，它會執行任務並在這裡彙報進度。面板可以用頂欄的「Agent」開關收起或展開。',
  'workbench_lorebook_title': '角色、場景與道具',
  'workbench_lorebook_body':
    '角色、場景和道具在側欄的「角色集」「場景庫」「道具庫」中統一管理。開啟卡片可以修改設定、生成資產圖。生成分鏡圖和影片時，資產圖會作為參考圖，用於保持畫面一致。',
  'workbench_timeline_title': '分鏡',
  'workbench_timeline_body':
    '每一集有腳本規劃、分鏡、剪輯三個檢視。在分鏡檢視中，每個分鏡包含提示詞、分鏡圖和影片：可以先生成分鏡圖確認構圖，再生成影片。',
  'workbench_export_title': '匯出專案',
  'workbench_export_body':
    '從頂欄「匯出專案」把整個專案下載為 ZIP，用於備份或遷移。成片和剪映草稿在各集的剪輯檢視中匯出。演示專案不能匯出。',
  'finish_title': '開始你的第一個專案',
  'finish_body': '新增專案並上傳小說或劇本，然後讓 Agent 開始製作。本引導可以隨時在「設定 → 通用」中重新檢視。',

  // 引導控制元件
  'next': '下一步',
  'prev': '上一步',
  'done': '完成',
  'skip': '跳過',
  'close': '關閉引導',
  'progress': '第 {{current}} 步，共 {{total}} 步',

  // 引導期間大廳裡的「示例專案」區塊
  'demo_section_title': '示例專案',
  'demo_section_note': '僅在引導期間顯示',
  'demo_project_title': '愛麗絲夢遊仙境',
  'demo_project_style': '水彩繪本',

  // 只讀演示工作台：頂欄專案標題旁的徽標與說明
  'demo_badge': '演示 · 只讀',
  'demo_badge_hint': '你正在檢視一個示例專案。編輯、生成、上傳和匯出功能在演示中不可用。',
  'demo_action_unavailable': '演示中不可用',
  'demo_episode_placeholder': '演示內容只到第 {{position}} 集：這一集只有標題，沒有腳本和分鏡。',

  // 演示工作台 Agent 面板的靜態對話：使用者發起製作 → Agent 彙報推進；中間的工序行用資產名稱拼出
  'demo_chat_user_start': '開始製作',
  'demo_chat_agent_progress': '角色形象圖和場景圖已生成。接下來逐集生成分鏡圖和影片，進度會在這裡彙報。',

  // 演示專案概述
  'demo_overview_synopsis':
    '一個悶熱的下午，愛麗絲追著一隻穿馬甲、掏懷錶的白兔跳進洞裡，落進一個尺寸、禮節和邏輯都不作數的地方。她一路變大變小，跟毛毛蟲、瘋帽子和紅心女王周旋，最後在一場荒唐的審判上把整座紙牌宮廷掀翻。',
  'demo_overview_genre': '童話 · 奇幻冒險',
  'demo_overview_theme': '秩序的荒謬，與一個孩子不肯照規矩來的固執',
  'demo_overview_world':
    '維多利亞時代的河岸午後通向仙境：兔子洞底一排鎖著的門、永遠停在下午茶的花園、以槌球和砍頭治國的紙牌宮廷。水彩繪本質感，紙紋可見，邊緣暈染。',

  // 演示分集標題
  'demo_episode_1_title': '掉進兔子洞',
  'demo_episode_2_title': '眼淚池塘',
  'demo_episode_3_title': '毛毛蟲的忠告',
  'demo_episode_4_title': '公爵夫人的廚房',
  'demo_episode_5_title': '瘋帽子的茶會',
  'demo_episode_6_title': '女王的槌球場',
  'demo_episode_7_title': '素甲魚的故事',
  'demo_episode_8_title': '誰偷了餡餅',

  // 演示角色
  'demo_character_1_name': '愛麗絲',
  'demo_character_1_desc':
    '七歲的英國女孩，藍裙配白圍裙，淺金色頭髮用黑髮帶束起。好奇心比謹慎多：遇上荒唐事先講道理，講不通就自己往前走。',
  'demo_character_1_voice': '清亮的童聲，語速偏快，好奇多於害怕',
  'demo_character_2_name': '白兔',
  'demo_character_2_desc':
    '穿格紋馬甲的白兔，一隻爪子攥懷錶、另一隻拿手套，永遠在遲到。心慌全寫在耳朵上，說話像還在趕路。',
  'demo_character_2_voice': '尖細急促，帶著喘氣與自言自語',
  'demo_character_3_name': '柴郡貓',
  'demo_character_3_desc': '灰紫條紋的大貓，笑容從一隻耳朵掛到另一隻。能一段一段消失，只把笑意留在半空。',
  'demo_character_3_voice': '慢條斯理的低音，尾音上挑，總在逗人',
  'demo_character_4_name': '紅心女王',
  'demo_character_4_desc': '紙牌宮廷的統治者，紅黑心形長裙，手握權杖。判決只有一句：砍掉她的頭。',
  'demo_character_4_voice': '洪亮急躁的女聲，一開口就是命令',

  // 演示場景
  'demo_scene_1_name': '河岸柳樹下',
  'demo_scene_1_desc': '悶熱午後的草坡，柳枝垂到水面，河水緩而亮，一本攤開的書裡既沒有圖畫也沒有對話。',
  'demo_scene_2_name': '兔子洞長廊',
  'demo_scene_2_desc':
    '洞底一條低矮長廊，兩側門全都鎖著，盡頭一張三腳玻璃桌，桌上一把小金鑰匙。只有一扇十五英寸高的小門透出光。',
  'demo_scene_3_name': '瘋茶會花園',
  'demo_scene_3_desc': '大樹下一張長桌，杯碟一路擠到桌尾，椅子多得沒人坐。所有鍾都停在六點，茶永遠是剛倒上的。',

  // 演示道具
  'demo_prop_1_name': '白兔的懷錶',
  'demo_prop_1_desc': '黃銅懷錶，鏈子磨得發亮，表蓋內側刻著字。指標走得比任何鍾都快，白兔一路盯著它喊遲到。',
  'demo_prop_2_name': '「喝我」小瓶',
  'demo_prop_2_desc': '小玻璃瓶，瓶頸系一張紙標籤，寫著「喝我」。味道像櫻桃派混著菠蘿，喝完人只剩十英寸高。',
  'demo_prop_3_name': '火烈鳥球杆',
  'demo_prop_3_desc': '夾在腋下當槌球杆用的火烈鳥。脖子剛擺正就自己扭回來，每打一杆都得先跟它商量。',

  // 演示分鏡 — 第 1 集
  'demo_shot_1_text': '那個下午很熱。愛麗絲和姐姐並坐在河岸上，姐姐讀的書裡既沒有圖畫也沒有對話，她開始困得睜不開眼。',
  'demo_shot_1_image':
    '夏日河岸，愛麗絲穿藍裙白圍裙在草坡上打盹，姐姐在一旁讀書，柳枝垂到水面。水彩繪本質感，邊緣柔和暈染，紙紋可見。',
  'demo_shot_1_lighting': '午後側逆光，草地上落著斑駁樹影',
  'demo_shot_1_ambiance': '慵懶、溫熱、昏昏欲睡',
  'demo_shot_1_video': '鏡頭沿河岸緩慢右搖，風吹動草葉與裙襬，她的眼睛慢慢閉上。',
  'demo_shot_1_audio': '流水聲，遠處蟬鳴，翻書頁的輕響',
  'demo_shot_2_text': '一隻穿馬甲的白兔從她身邊跑過，掏出懷錶看了一眼，自言自語：糟了糟了，我要遲到了。',
  'demo_shot_2_image': '白兔立起身穿格紋馬甲快步穿過草叢，一隻爪子高舉黃銅懷錶，愛麗絲在背景裡坐起身。水彩繪本質感。',
  'demo_shot_2_lighting': '明亮日光，兔毛邊緣透光',
  'demo_shot_2_ambiance': '突然、滑稽、催促',
  'demo_shot_2_video': '鏡頭跟著白兔平移，它低頭看錶又抬頭小跑，愛麗絲轉頭追看。',
  'demo_shot_2_audio': '急促的碎步聲，懷錶滴答，兔子的喘氣',
  'demo_shot_3_text': '愛麗絲跳起來追過去，剛好看見白兔鑽進樹籬下一個大兔子洞，她一頭跟著進去，根本沒想過怎麼出來。',
  'demo_shot_3_image': '樹籬下一個黑洞洞的兔子洞，愛麗絲手撐地探身，裙襬揚起，白兔的尾巴剛消失在洞裡。水彩繪本質感。',
  'demo_shot_3_lighting': '亮草地與洞口的黑形成強對比',
  'demo_shot_3_ambiance': '好奇壓過害怕的一瞬',
  'demo_shot_3_video': '鏡頭向洞口推進，她一手撐地探進身子，畫面被洞口的暗吞掉。',
  'demo_shot_3_audio': '草葉摩擦，泥土松落，越收越緊的回聲',
  'demo_shot_4_text': '洞先像隧道一樣平著走，隨後陡然向下。她掉得很慢，一路看得清井壁上的櫥櫃、書架和掛著的地圖。',
  'demo_shot_4_image':
    '深井剖面，愛麗絲裙襬張開緩緩下墜，井壁上掛著櫥櫃、書架、地圖和一盞小燈。水彩繪本質感，越往下越深。',
  'demo_shot_4_lighting': '上方一圈天光，向下漸暗，燈罩投出暖色光斑',
  'demo_shot_4_ambiance': '懸空、失重、時間被拉長',
  'demo_shot_4_video': '鏡頭隨她垂直下降，櫥櫃與書架一層層向上掠過畫面。',
  'demo_shot_4_audio': '空井裡的風聲，衣料翻動，遠處水滴',
  'demo_shot_5_text': '井底是一條長廊，一排門全都鎖著。她在玻璃桌上找到一把小金鑰匙——它只配得上一扇十五英寸高的小門。',
  'demo_shot_5_image': '三腳玻璃桌特寫，桌上一把小金鑰匙和一隻繫著紙標籤的小瓶，背景裡一扇矮門透出光。水彩繪本質感。',
  'demo_shot_5_lighting': '門縫透進一束暖光，四周壓進暗部',
  'demo_shot_5_ambiance': '安靜、逼仄、一線希望',
  'demo_shot_5_video': '鏡頭固定，光斑緩慢移過鑰匙，塵埃在光束裡浮動。',
  'demo_shot_5_audio': '空廊回聲，鑰匙碰玻璃的清響',
  'demo_shot_6_text': '瓶頸上的紙標籤寫著「喝我」。她喝了一口，覺得自己像收起來的望遠鏡，一路縮到只有十英寸高。',
  'demo_shot_6_image': '愛麗絲舉起「喝我」小瓶飲下，同一畫面裡身形縮小，裙子堆在腳邊，矮門變得剛好合身。水彩繪本質感。',
  'demo_shot_6_lighting': '暖光從矮門溢位，人物邊緣發光',
  'demo_shot_6_ambiance': '驚訝多於害怕的轉折',
  'demo_shot_6_video': '鏡頭隨她縮小而拉遠，裙子塌落，視角從平視轉為仰看矮門。',
  'demo_shot_6_audio': '嚥下的一聲，衣料滑動，空瓶輕放在地',

  // 設定 → 通用 的入口
  'replay_title': '使用引導',
  'replay_desc': '重看首次使用引導，瞭解主要介面和基本流程。',
  'replay_action': '重看引導',
} satisfies Record<keyof typeof enOnboarding, string>;
