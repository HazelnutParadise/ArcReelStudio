"""集中维护 provider / AUTH 相关的环境变量 key 清单。

唯一真相源 — 凡是涉及 os.environ 名单的代码都从这里 import。
"""

from __future__ import annotations

from collections.abc import Mapping

# —— SDK 子进程需要的 Anthropic env keys（通过 options.env 注入）——
ANTHROPIC_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)

# —— 其他 provider env keys（options.env 用空值覆盖兜底）——
OTHER_PROVIDER_ENV_KEYS: tuple[str, ...] = (
    # Claude CLI / SDK 会优先读取这些旁路认证变量。它们不属于 ArcReel 的
    # provider 凭证模型，但必须在 Agent 会话中显式置空，避免继承宿主环境。
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    # 让 CLI 改走宿主云账号（Bedrock / Vertex）的开关，同样不能从宿主环境继承
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "ARK_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "VIDU_API_KEY",
    "DASHSCOPE_API_KEY",
    "MINIMAX_API_KEY",
    "AGNES_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    # OpenAI SDK 在 client 未显式传值时回落读的 env 旋钮（非密钥命名，
    # _SECRET_ENV_NAME_PATTERNS 的子串匹配兜不到）。整组纳入覆盖名单，
    # 避免它们经 fork 漏进 SDK / Bash 子进程。
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "OPENAI_CUSTOM_HEADERS",
    "GEMINI_BASE_URL",
    "GEMINI_IMAGE_MODEL",
    "GEMINI_VIDEO_MODEL",
    "GEMINI_IMAGE_BACKEND",
    "GEMINI_VIDEO_BACKEND",
    "VERTEX_GCS_BUCKET",
    "FILE_SERVICE_BASE_URL",
    "DEFAULT_VIDEO_PROVIDER",
)

# —— Claude CLI 从宿主环境继承的认证、供应商与路由变量（按前缀）——
# SDK 把整个父进程环境传给 CLI，只用 options.env 覆盖；凡这些前缀的变量，应用没有自己设值的一律空值覆盖，
# 新出现的同类变量（如 Foundry、自定义请求头）不必逐个登记。
CLAUDE_CLI_ENV_PREFIXES: tuple[str, ...] = ("ANTHROPIC_", "CLAUDE_CODE_")
#: 按前缀命中但只用于在宿主机器上找到程序、不涉及认证与路由的变量，照常继承
CLAUDE_CLI_ENV_INHERITED: frozenset[str] = frozenset({"CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CODE_ENTRYPOINT"})


def inherited_claude_cli_env_keys(environ: Mapping[str, str]) -> list[str]:
    """宿主环境里要对 Claude CLI 空值覆盖的变量名。"""
    return [key for key in environ if key.startswith(CLAUDE_CLI_ENV_PREFIXES) and key not in CLAUDE_CLI_ENV_INHERITED]


# —— 启动断言：真密钥子集，命中即 fail-fast ——
PROVIDER_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ARK_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "VIDU_API_KEY",
        "DASHSCOPE_API_KEY",
        "MINIMAX_API_KEY",
        "AGNES_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }
)


def is_provider_env_key(name: str) -> bool:
    """判断给定 env key 是否属于 provider 相关。"""
    return name in ANTHROPIC_ENV_KEYS or name in OTHER_PROVIDER_ENV_KEYS
