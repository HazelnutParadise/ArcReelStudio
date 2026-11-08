"""English translations for provider registry metadata."""

MESSAGES: dict[str, str] = {
    # Provider display names
    "provider_name_gemini-aistudio": "AI Studio",
    "provider_name_gemini-vertex": "Vertex AI",
    "provider_name_ark": "Volcengine Ark",
    "provider_name_ark-agent-plan": "Volcengine Ark Agent Plan",
    "provider_name_grok": "Grok",
    "provider_name_openai": "OpenAI",
    "provider_name_vidu": "Vidu",
    "provider_name_dashscope": "Alibaba Model Studio",
    "provider_name_minimax": "MiniMax",
    "provider_name_kling": "Kling",
    "provider_name_agnes": "Agnes",
    "provider_name_claude-subscription": "Claude subscription",
    "provider_name_chatgpt-subscription": "ChatGPT subscription",
    "provider_name_grok-subscription": "Grok subscription",
    "provider_name_elevenlabs": "ElevenLabs",
    "provider_name_stability": "Stability AI",
    # 失败文案里目录查不到的供应商（已被删除）的泛称
    "deleted_provider_display_name": "Deleted provider",
    "deleted_agent_provider_display_name": "Deleted Agent provider",
    # Provider descriptions：只写平台是什么，取自 docs/api-docs/providers/<id>.md 记录的来源；
    # 不写模型版本与生成模态清单，能力标签由模型目录实时得出，写进描述必然过时；
    # 模型家族名（GPT、Qwen 等）属于平台身份，可以写。
    "provider_desc_gemini-aistudio": "Web-based IDE developed by Google for prototyping applications with generative AI models.",
    "provider_desc_gemini-vertex": "Machine learning service offered by Google Cloud, now renamed Gemini Enterprise Agent Platform.",
    "provider_desc_ark": "Large-model service platform (MaaS) from Volcengine, ByteDance's cloud, offering model fine-tuning, evaluation and inference for businesses.",
    "provider_desc_ark-agent-plan": "Subscription-based model service plan from Volcengine Ark for individual users, billed in credits.",
    "provider_desc_grok": "The Grok API from SpaceX Super Intelligence (formerly xAI), serving its Grok family of generative AI models.",
    "provider_desc_openai": "API platform of OpenAI, the American artificial intelligence company, serving its GPT series and other generative AI models.",
    "provider_desc_vidu": "ShengShu Technology's Vidu API platform for AI video generation.",
    "provider_desc_dashscope": "Alibaba Cloud's model service platform, offering Qwen and other models with API access, fine-tuning and deployment.",
    "provider_desc_minimax": "Open platform of MiniMax, a Shanghai-based AI company, serving its multimodal models and Hailuo video generation. Connects to the domestic site by default; set base_url to the international site for overseas access.",
    "provider_desc_kling": "Open platform of Kling AI, Kuaishou's generative AI service. API Key authentication works with all models; Access Key + Secret Key (JWT) only supports 3.0-and-earlier models. Choose either — when both are set, API Key takes priority.",
    "provider_desc_agnes": "Agnes AI's multimodal AI platform, serving its generative AI models through one unified API.",
    "provider_desc_claude-subscription": "Sign in with a Claude account (Pro, Max and other plans) to use its subscription quota. Currently used by the ArcReel Agent.",
    "provider_desc_chatgpt-subscription": "Sign in with a ChatGPT account (Plus, Pro and other plans) through Codex to use its subscription quota.",
    "provider_desc_grok-subscription": "Sign in with a Grok account (SuperGrok, X Premium and other plans) through the Grok CLI to use its subscription quota.",
    "provider_desc_elevenlabs": "The API platform of US voice AI company ElevenLabs, offering music and sound effect generation. Its music terms forbid making the music models available through a third-party platform, so get ElevenLabs' permission before opening it to outside users.",
    "provider_desc_stability": "The API platform of UK AI company Stability AI, offering generative models such as Stable Audio for music and sound effects.",
    # Agent preset notes (lib/agent/agent_provider_catalog.py)
    "preset_notes_deepseek": "DeepSeek official Anthropic-compat endpoint; needs sk- prefixed key.",
    "preset_notes_xiaomi_mimo": "Xiaomi MiMo only accepts known model names; no public model list.",
    "preset_notes_ark_coding_plan": "Volcengine Ark Coding Plan; no model-list endpoint — pick a suggested model you have enabled in the Ark console.",
    "preset_notes_ark_agent_plan": "Volcengine Ark Agent Plan; no model-list endpoint — pick a suggested model included in your plan tier.",
}
