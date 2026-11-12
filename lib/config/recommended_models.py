"""内置供应商的推荐模型：首次配置时写进空的全局默认模型，之后推荐变化只提示（docs/adr/0130）。

模型目录里每个内置供应商按媒体类型给出的默认模型只作推荐，运行时解析不读它。推荐进入用户设置只有两个入口：

- 供应商的第一条连线生效时（API 金钥、Vertex 凭证上传、订阅登录），全局默认模型还没有设置的媒体类型写入推荐
  （:func:`seed_provider_recommendations`）。
- 用户在推荐变化的提示上选择改用（:func:`acknowledge_recommendation`）。

提示的判据是「已见过的推荐」：首次配置或确认时，每个供应商在各媒体类型下记一条推荐模型，各占一个系统设置
（``recommendation_seen:<provider>:<media_type>``），互不覆盖。之后推荐与记下的不同，就在全局默认模型旁提示，
改不改由用户决定（:func:`recommendation_changes`）。

``default_audio_backend`` 专指旁白配音：``audio`` 只认有配音能力的推荐，音乐与音效的默认模型不写推荐。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from lib.catalog import builtin_models
from lib.catalog import query as catalog
from lib.config.model_setting_keys import MODEL_SETTING_CAPABILITIES, credential_key
from lib.config.registry import PROVIDER_REGISTRY
from lib.config.repository import SystemSettingRepository
from lib.config.service import ConfigService

#: 已见过的推荐的系统设置键前缀，完整的键是 ``<前缀><provider>:<media_type>``，值是模型键。
SEEN_KEY_PREFIX = "recommendation_seen:"

#: 各媒体类型的全局默认模型键：推荐只写进默认层，不写任务类型桶、文本档位与音乐音效。
GLOBAL_DEFAULT_KEYS: dict[str, str] = {
    "text": "default_text_backend",
    "image": "default_image_backend",
    "video": "default_video_backend",
    "audio": "default_audio_backend",
}


@dataclass(frozen=True)
class RecommendationChange:
    """一处推荐变化：``provider_id`` 在 ``media_type`` 下现在推荐 ``recommended_model``。

    ``current`` 是这个媒体类型的全局默认模型（``provider/model``），没有设置时为 ``None``。
    """

    media_type: str
    provider_id: str
    recommended_model: str
    current: str | None


class StaleRecommendationError(ValueError):
    """要确认的推荐模型已不是供应商当前的推荐（推荐在提示之后又变了）。"""


def _is_set(value: str | None) -> bool:
    """全局默认模型设置有值：只有 ``provider/model`` 完整形态算，与解析链的全局层同口径。"""
    return isinstance(value, str) and "/" in value


def _seen_key(provider_id: str, media_type: str) -> str:
    return f"{SEEN_KEY_PREFIX}{provider_id}:{media_type}"


async def _recommendation(session: AsyncSession, provider_id: str, media_type: str) -> str | None:
    """供应商在这个媒体类型下能写进全局默认模型的推荐：可用，且具备该默认键要求的能力（音频须能配音）。"""
    model_id = await builtin_models.recommended_builtin_model(session, provider_id, media_type)
    if model_id is None:
        return None
    required = MODEL_SETTING_CAPABILITIES.get(GLOBAL_DEFAULT_KEYS[media_type])
    if required is not None:
        model_info = catalog.get_model(provider_id, model_id)
        if model_info is None or required not in model_info.capabilities:
            return None
    return model_id


async def _read_seen(repo: SystemSettingRepository) -> dict[tuple[str, str], str]:
    seen: dict[tuple[str, str], str] = {}
    for key, model in (await repo.get_prefixed(SEEN_KEY_PREFIX)).items():
        provider_id, _, media_type = key.removeprefix(SEEN_KEY_PREFIX).partition(":")
        seen[(provider_id, media_type)] = model
    return seen


async def _ready_builtin_providers(session: AsyncSession) -> list[str]:
    """有生效连线的内置供应商，按注册顺序。"""
    statuses = await ConfigService(session).get_all_providers_status()
    ready = {status.name for status in statuses if status.status == "ready"}
    return [provider_id for provider_id in PROVIDER_REGISTRY if provider_id in ready]


async def seed_provider_recommendations(session: AsyncSession, provider_id: str) -> None:
    """供应商首次配置：全局默认模型还没有设置的媒体类型写入它的推荐，并为还没有记录的媒体类型记下推荐。

    只写 ``provider/model``，不写连线旁键：没有旁键就用该供应商的默认连线。已有设置不覆盖；已记下的推荐也不覆盖，
    连线删除重建不会吞掉还没处理的推荐变化。不是内置供应商时什么都不写。由调用方提交事务。
    """
    if provider_id not in PROVIDER_REGISTRY:
        return
    repo = SystemSettingRepository(session)
    for media_type, key in GLOBAL_DEFAULT_KEYS.items():
        model_id = await _recommendation(session, provider_id, media_type)
        if model_id is None:
            continue
        if not _is_set(await repo.get(key, "")):
            await repo.upsert(key, f"{provider_id}/{model_id}")
        await repo.insert_if_absent(_seen_key(provider_id, media_type), model_id)


async def recommendation_changes(session: AsyncSession) -> list[RecommendationChange]:
    """推荐变化的提示，每个媒体类型至多一条。

    - 全局默认模型是某个内置供应商的模型：这个供应商现在的推荐与它不同，且不是已见过的推荐时提示。
    - 没有全局默认模型：按注册顺序第一个已配置、推荐不是已见过的推荐的内置供应商提示。
    """
    repo = SystemSettingRepository(session)
    seen = await _read_seen(repo)
    settings = await repo.get_all()
    ready: list[str] | None = None
    changes: list[RecommendationChange] = []
    for media_type, key in GLOBAL_DEFAULT_KEYS.items():
        current = settings.get(key, "")
        if _is_set(current):
            provider_id, model_id = current.split("/", 1)
            if provider_id not in PROVIDER_REGISTRY:
                continue
            recommended = await _recommendation(session, provider_id, media_type)
            if recommended is not None and recommended not in (model_id, seen.get((provider_id, media_type))):
                changes.append(RecommendationChange(media_type, provider_id, recommended, current))
            continue
        if ready is None:
            ready = await _ready_builtin_providers(session)
        for provider_id in ready:
            recommended = await _recommendation(session, provider_id, media_type)
            if recommended is not None and recommended != seen.get((provider_id, media_type)):
                changes.append(RecommendationChange(media_type, provider_id, recommended, None))
                break
    return changes


async def acknowledge_recommendation(
    session: AsyncSession, provider_id: str, media_type: str, model_id: str, *, apply: bool
) -> None:
    """用户处理了一条推荐变化：记下这个推荐；``apply`` 为真时同时把它设为这个媒体类型的全局默认模型。

    改用推荐与默认模型页的写入同一规则：换了供应商时清掉连线旁键（回到新供应商的默认连线），同一供应商保留
    用户选的连线。每个设置单条语句写入，并发确认不同媒体类型互不覆盖。``model_id`` 不是供应商当前的推荐时抛
    :class:`StaleRecommendationError`，什么都不改。由调用方提交事务。
    """
    if media_type not in GLOBAL_DEFAULT_KEYS or provider_id not in PROVIDER_REGISTRY:
        raise StaleRecommendationError(f"{provider_id}:{media_type}")
    if await _recommendation(session, provider_id, media_type) != model_id:
        raise StaleRecommendationError(model_id)
    repo = SystemSettingRepository(session)
    if apply:
        key = GLOBAL_DEFAULT_KEYS[media_type]
        current_provider = (await repo.get(key, "")).split("/", 1)[0]
        await repo.upsert(key, f"{provider_id}/{model_id}")
        if current_provider != provider_id:
            await repo.upsert(credential_key(key), "")
    await repo.upsert(_seen_key(provider_id, media_type), model_id)


__all__ = [
    "GLOBAL_DEFAULT_KEYS",
    "SEEN_KEY_PREFIX",
    "RecommendationChange",
    "StaleRecommendationError",
    "acknowledge_recommendation",
    "recommendation_changes",
    "seed_provider_recommendations",
]
