# AI Anime Generator Library
# 共享 Python 库，用于 Gemini API 封装和项目管理

# 须先于任何 `import httpx` 执行：respx 与仍按 httpx 编写的依赖（方舟 SDK）由此拿到 httpx2 的类，见 docs/agents/dependencies.md。
import httpx2

httpx2.alias_httpx()

# 首先初始化环境（激活 .venv，加载 .env）
from lib.infra.env_init import PROJECT_ROOT
from lib.infra.validation_messages import ValidationResult
from lib.project.data_validator import DataValidator, validate_episode, validate_project
from lib.project.project_manager import ProjectManager

__all__ = [
    "PROJECT_ROOT",
    "DataValidator",
    "ProjectManager",
    "ValidationResult",
    "validate_episode",
    "validate_project",
]
