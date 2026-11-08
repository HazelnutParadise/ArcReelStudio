"""Chinese translations for provider registry metadata."""

MESSAGES: dict[str, str] = {
    # Provider display names
    "provider_name_gemini-aistudio": "AI Studio",
    "provider_name_gemini-vertex": "Vertex AI",
    "provider_name_ark": "火山方舟",
    "provider_name_ark-agent-plan": "火山方舟 Agent Plan",
    "provider_name_grok": "Grok",
    "provider_name_openai": "OpenAI",
    "provider_name_vidu": "Vidu",
    "provider_name_dashscope": "阿里百鍊",
    "provider_name_minimax": "MiniMax",
    "provider_name_kling": "可靈 Kling",
    "provider_name_agnes": "Agnes",
    "provider_name_claude-subscription": "Claude 訂閱",
    "provider_name_chatgpt-subscription": "ChatGPT 訂閱",
    "provider_name_grok-subscription": "Grok 訂閱",
    "provider_name_elevenlabs": "ElevenLabs",
    "provider_name_stability": "Stability AI",
    # 失敗文案裡目錄查不到的供應商（已被刪除）的泛稱
    "deleted_provider_display_name": "已刪除的供應商",
    "deleted_agent_provider_display_name": "已刪除的 Agent 供應商",
    # Provider descriptions：只寫平台是什麼，取自 docs/api-docs/providers/<id>.md 記錄的來源；
    # 不寫模型版本與生成模態清單，能力標籤由模型目錄即時得出，寫進描述必然過時；
    # 模型家族名（GPT、Qwen 等）屬於平台身份，可以寫。
    "provider_desc_gemini-aistudio": "Google 開發的網頁端整合開發環境，用於基於生成式 AI 模型設計應用原型。",
    "provider_desc_gemini-vertex": "Google Cloud 提供的機器學習服務，已更名為 Gemini Enterprise Agent Platform。",
    "provider_desc_ark": "字節跳動旗下火山引擎的大模型服務平台（MaaS），面向企業提供模型精調、評測與推理等服務。",
    "provider_desc_ark-agent-plan": "火山方舟面向個人使用者推出的訂閱式大模型服務套餐，按積分計費。",
    "provider_desc_grok": "SpaceX Super Intelligence（原 xAI）的 Grok API，提供其 Grok 系列生成式 AI 模型。",
    "provider_desc_openai": "美國人工智慧公司 OpenAI 的 API 平台，提供其 GPT 系列等生成式 AI 模型。",
    "provider_desc_vidu": "生數科技的 Vidu API 平台，提供 AI 影片生成能力。",
    "provider_desc_dashscope": "阿里雲的大模型服務平台，提供通義千問（Qwen）等模型的 API 呼叫、精調與部署。",
    "provider_desc_minimax": "上海人工智慧公司 MiniMax（稀宇科技）的開放平台，提供其多模態模型與海螺影片生成服務。預設連線國內站，海外可將 base_url 切換到國際站。",
    "provider_desc_kling": "快手推出的生成式 AI 服務可靈的開放平台。API Key 鑑權適用於全部模型；Access Key + Secret Key（JWT）僅適用於 3.0 及更早模型，二者二選一，同時填寫時 API Key 優先。",
    "provider_desc_agnes": "Agnes AI 的多模態 AI 平台，通過統一的 API 提供其生成式 AI 模型。",
    "provider_desc_claude-subscription": "用 Claude 帳號（Pro、Max 等訂閱）登入，使用訂閱額度，目前供 ArcReel Agent 使用。",
    "provider_desc_chatgpt-subscription": "用 ChatGPT 帳號（Plus、Pro 等訂閱）透過 Codex 登入，使用訂閱額度。",
    "provider_desc_grok-subscription": "用 Grok 帳號（SuperGrok、X Premium 等訂閱）透過 Grok CLI 登入，使用訂閱額度。",
    "provider_desc_elevenlabs": "美國語音 AI 公司 ElevenLabs 的 API 平台，提供音樂與音效生成。它的音樂條款禁止把音樂模型提供給第三方平台使用，對外開放前請先向 ElevenLabs 取得授權。",
    "provider_desc_stability": "英國 AI 公司 Stability AI 的 API 平台，提供 Stable Audio 等生成式模型，可生成音樂與音效。",
    # Agent preset notes (lib/agent/agent_provider_catalog.py)
    "preset_notes_deepseek": "DeepSeek 官方 Anthropic 相容端點，需 sk- 開頭的 API Key",
    "preset_notes_xiaomi_mimo": "小米 MiMo 僅支援已知模型名，未公開模型清單",
    "preset_notes_ark_coding_plan": "火山方舟 Coding Plan 套餐；不提供模型清單介面，請從建議模型中選擇已在控制台開通的模型",
    "preset_notes_ark_agent_plan": "火山方舟 Agent Plan 套餐；不提供模型清單介面，請從建議模型中選擇當前套餐已開通的模型",
}
