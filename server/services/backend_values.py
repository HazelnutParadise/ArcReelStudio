"""项目与全局设置里 ``provider/model`` 字段值的写入校验，供设置接口与协作写回共用。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from lib.catalog import query as catalog
from lib.config.model_setting_keys import MODEL_SETTING_CAPABILITIES, MODEL_SETTING_MEDIA_TYPES
from lib.config.registry import PROVIDER_REGISTRY
from lib.db.repositories.credential_repository import CredentialRepository
from lib.infra.api_errors import BadRequestError


def audio_capabilities(option: str) -> list[str]:
    """``provider/model`` 音频模型的能力：目录登记的按条目事实；目录外（自定义供应商的配音端点等）视为配音。"""
    provider_id, _, model_id = option.partition("/")
    model_info = catalog.get_model(provider_id, model_id)
    if model_info is None:
        return ["text_to_speech"]
    return list(model_info.capabilities)


def validate_backend_value(value: str, field_name: str) -> None:
    """校验 ``provider/model`` 格式的 backend 字段值。

    只接受规范 provider id（``PROVIDER_REGISTRY`` 的 key 或 ``custom-`` 前缀）。legacy provider 名
    （``gemini``/``aistudio``/``vertex``/``seedance``）一律拒绝——它们是待清除的历史数据，由一次性项目迁移
    转为规范 id 后即不再被接受（见 ``docs/adr/0001``）。

    额外校验模型目录内登记模型的 ``media_type`` 与 ``field_name``（经 ``MODEL_SETTING_MEDIA_TYPES``）期望的
    一致（如 text 档位字段不接受 video 模型）；只对模型目录内登记的内置模型判定，目录外
    （自定义供应商等）无逐模型能力事实，放行交由供应商 API 把关，不做猜测。

    Raises:
        BadRequestError: 格式不合法、provider 不在注册表中、为 legacy 名、或 media_type 不匹配。
            字段名只进诊断信息，不进面向使用者的摘要。
    """
    if "/" not in value:
        if value in PROVIDER_REGISTRY:
            return  # 裸 registry id（无 model），下游按全局默认补全
        raise BadRequestError("invalid_backend_format").with_diagnostic(f"field: {field_name}")
    provider_id, model_id = value.split("/", 1)
    if provider_id not in PROVIDER_REGISTRY and not provider_id.startswith("custom-"):
        raise BadRequestError("unknown_provider", value=provider_id).with_diagnostic(f"field: {field_name}")
    # 未登记的字段名不做这项校验：新增字段忘记登记时静默放行，而不是误报
    expected_media_type = MODEL_SETTING_MEDIA_TYPES.get(field_name)
    if expected_media_type is not None:
        model_info = catalog.get_model(provider_id, model_id)
        if model_info is not None and model_info.media_type != expected_media_type:
            raise BadRequestError(
                "backend_media_type_mismatch",
                provider=provider_id,
                model=model_id,
                expected=expected_media_type,
                actual=model_info.media_type,
            ).with_diagnostic(f"field: {field_name}")
    required_capability = MODEL_SETTING_CAPABILITIES.get(field_name)
    if required_capability is not None and required_capability not in audio_capabilities(value):
        raise BadRequestError(
            "backend_capability_mismatch", provider=provider_id, model=model_id, capability=required_capability
        ).with_diagnostic(f"field: {field_name}")


async def validate_backend_credential(
    session: AsyncSession, backend_value: str, credential_id: int | None
) -> int | None:
    """校验与 ``backend_value``（同一字段的 ``provider/model``）同层的连线旁键，返回要存的凭证 id。

    None 表示用该供应商的默认连线。指定的连线必须存在、属于同一个内置供应商；自定义供应商的凭证就在供应商本身，
    没有可选的连线。
    """
    if credential_id is None:
        return None
    provider_id = backend_value.split("/", 1)[0].strip() if backend_value else ""
    credential = await CredentialRepository(session).get_by_id(credential_id)
    if (
        not provider_id
        or provider_id not in PROVIDER_REGISTRY
        or credential is None
        or credential.provider != provider_id
    ):
        raise BadRequestError("credential_not_for_provider", provider=provider_id or "-", credential_id=credential_id)
    return credential_id
