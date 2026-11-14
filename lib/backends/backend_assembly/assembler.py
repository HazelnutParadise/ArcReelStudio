"""assemble_backend — 「provider config + model → backend」统一构造入口。

按 is_custom_provider 单分支分流到内置 / 自定义两族（一道门、门后两个对称房间，见 ADR 0039）。
构造拆两段：async 装载（查 DB/config，产出 LoadedConfig 信封）/ sync 纯闭包构造。缝无状态、纯构造，
backend 实例缓存留在调用方编排层、不进缝。
"""

from __future__ import annotations

import asyncio
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lib.backends.backend_assembly.loaded_config import LoadedConfig
from lib.backends.backend_assembly.specs import PROVIDER_ENDPOINT_SPECS, builtin_model_endpoint, get_provider_endpoints
from lib.catalog import query as catalog
from lib.catalog.errors import ModelNotInCatalogError
from lib.config.registry import PROVIDER_REGISTRY
from lib.config.vertex_credentials import VERTEX_PROVIDER_ID, VertexCredentialMissingError, has_vertex_credentials_file
from lib.custom_provider import is_custom_provider
from lib.db.repositories.credential_repository import CredentialRepository

if TYPE_CHECKING:
    from lib.config.resolver import ConfigResolver


async def _load_builtin_config(
    resolver: ConfigResolver, provider_id: str, rate_limiter: Any | None, credential_id: int | None = None
) -> LoadedConfig:
    """内置侧 async 装载段：查 DB/config 产出 LoadedConfig 信封。

    凭证 overlay 来自 db_config（resolver.provider_config）；registry meta 提供 default_base_url /
    api_model_name 来源；rate_limiter 由调用方注入（共享实例）。这一段是唯一的 await/DB 触点，
    之后 sync 构造闭包只读信封。
    """
    db_config, credential_id = await resolver.provider_config_with_credential(provider_id, credential_id)
    if provider_id == VERTEX_PROVIDER_ID:
        await _require_vertex_credentials_file(resolver, db_config.get("credentials_path"), credential_id)
    return LoadedConfig(
        credentials=dict(db_config),
        provider_meta=PROVIDER_REGISTRY.get(provider_id),
        rate_limiter=rate_limiter,
        credential_id=credential_id,
    )


async def _require_vertex_credentials_file(
    resolver: ConfigResolver, credentials_path: str | None, credential_id: int | None
) -> None:
    """Vertex 只用生效连线（或供应商配置）给出的凭证文件；没有就报出是哪条连线，不挑别的文件顶替。"""
    if await asyncio.to_thread(has_vertex_credentials_file, credentials_path):
        return
    connection: str | None = None
    if credential_id is not None:
        async with resolver._open_session() as (session, _):
            credential = await CredentialRepository(session).get_by_id(credential_id)
        connection = credential.name if credential is not None else None
    raise VertexCredentialMissingError(connection=connection)


async def assemble_backend(
    *,
    provider_id: str,
    media_type: str,
    model_id: str | None,
    resolver: ConfigResolver,
    rate_limiter: Any | None = None,
    generation_type: str | None = None,
    submitted_job: bool = False,
    builtin_endpoint: str | None = None,
    credential_id: int | None = None,
) -> Any:
    """统一构造入口。按 provider_id 是否自定义分流；未登记的内置 provider × media fail-loud。

    ``generation_type`` 是调用点所属的任务类型桶，只在自定义侧消费（默认模型按桶分槽，见
    ``lib.custom_provider.loader.load_custom_backend``）；内置侧的 model 由 registry 定，不分桶。

    ``submitted_job`` 为真表示构造出的 backend 只用于续跑已提交给厂商的任务（只轮询、不发起新的生成）：模型已下线
    也照常构造，其余检查不变。新调用恒为假。

    ``builtin_endpoint`` 是调用方已经定下的内置调用端点：传入时内置供应商按它构造，调用方据同一次读取冻结的续跑守卫
    与构造出的实例一致；为 None 时这里按模型挂接的端点现定（:func:`builtin_model_endpoint`）。自定义供应商不读它。

    ``credential_id`` 是设置里为这个调用处指定的连线（凭证），None 用该供应商的默认连线；自定义供应商的凭证就在
    供应商本身，不读它。
    """
    if is_custom_provider(provider_id):
        from lib.custom_provider.loader import load_custom_backend

        # 借 resolver 的 session（bound 时复用其事务上下文）：自定义装载与简单族装载共用同一
        # session_factory，调用方在 resolver.session() 内构造时复用同一连接，避免另开 factory。
        async with resolver._open_session() as (session, _):
            return await load_custom_backend(
                session=session,
                provider_id=provider_id,
                model_id=model_id,
                media_type=media_type,
                generation_type=generation_type,
                submitted_job=submitted_job,
            )
    get_provider_endpoints(provider_id, media_type)  # 未登记 → ValueError（fail-loud）
    model_id = _callable_builtin_model(provider_id, media_type, model_id, submitted_job=submitted_job)
    # 先定下供应商模型挂接的内置调用端点，再由端点构造：供应商给凭证，端点决定请求
    endpoint = builtin_endpoint or builtin_model_endpoint(provider_id, media_type, model_id)
    spec = PROVIDER_ENDPOINT_SPECS[(provider_id, endpoint)]
    config = await _load_builtin_config(resolver, provider_id, rate_limiter, credential_id)
    # 构造闭包可能读凭证文件（Vertex 服务账号 JSON），放线程里跑，不阻塞事件循环。工作线程里没有事件循环，
    # backend 构造时不能创建要求事件循环的 SDK 客户端（xai_sdk.AsyncClient 的做法见 grok_shared.LazyGrokClient）。
    backend = await asyncio.to_thread(spec.build_backend, config, model_id)
    if media_type == "video":
        backend = _with_model_entry(backend, provider_id, model_id)
    _remember_credential(backend, config.credential_id)
    return backend


#: 内置供应商的 backend 实例 → 构造它时实际用的连线（凭证 id）。记账按它记下这次调用花在哪个账号上。
_ASSEMBLED_CREDENTIALS: weakref.WeakKeyDictionary[Any, int] = weakref.WeakKeyDictionary()


def _remember_credential(backend: Any, credential_id: int | None) -> None:
    if credential_id is None:
        return
    try:
        _ASSEMBLED_CREDENTIALS[backend] = credential_id
    except TypeError:
        # 不支持弱引用的实例（``__slots__`` 且无 ``__weakref__``）：记不下连线，记账留空
        return


def assembled_credential_id(backend: Any) -> int | None:
    """``backend`` 构造时实际用的连线（含默认连线）；自定义供应商或没有凭证记录时为 None。"""
    try:
        return _ASSEMBLED_CREDENTIALS.get(backend)
    except TypeError:
        return None


async def callable_model_key(
    *,
    provider_id: str,
    media_type: str,
    model_id: str | None,
    resolver: ConfigResolver,
    generation_type: str | None = None,
    submitted_job: bool = False,
) -> str | None:
    """复用 backend 实例前的调用检查：按今天的生命周期确认这次调用的模型可以调用，返回实例缓存用的模型键。

    缓存里的实例可能构造于关停日期之前，命中缓存会绕过 :func:`assemble_backend` 里的检查，所以调用方在查缓存前调用本函数。

    - 内置供应商：``model_id`` 为 ``None`` 时抛 ``ModelNotInCatalogError``，不按目录推荐补模型（docs/adr/0130），与装配同一口径；
      返回模型键；已下线抛 ``ModelDiscontinuedError``。这里刻意不查「是否在清单里」，完整检查在真正构造时执行。
    - 自定义供应商：按装载同一条规则（``lib.custom_provider.loader.select_custom_model``）定下模型行，显式引用的模型已下线、
      或回退后没有未下线的默认模型时同样报错；``model_id`` 原样返回（默认模型按任务类型桶分槽，键里另有桶）。
    - 未登记的供应商原样返回，由装配报错。

    ``submitted_job`` 为真（续跑已提交给厂商的任务，见 :func:`assemble_backend`）时不拦已下线的模型，其余照旧。
    续跑写入缓存的实例可能是已下线模型的实例，之后的新调用取缓存前不带这一声明，照常被拦下。
    """
    if is_custom_provider(provider_id):
        from lib.custom_provider.loader import select_custom_model

        async with resolver._open_session() as (session, _):
            await select_custom_model(
                session=session,
                provider_id=provider_id,
                model_id=model_id,
                media_type=media_type,
                generation_type=generation_type,
                submitted_job=submitted_job,
            )
        return model_id
    if provider_id not in PROVIDER_REGISTRY:
        return model_id
    model_id = _require_builtin_model(provider_id, media_type, model_id)
    if not submitted_job:
        catalog.reject_discontinued(provider_id, model_id, media_type)
    return model_id


def _require_builtin_model(provider_id: str, media_type: str, model_id: str | None) -> str:
    """``model_id`` 为 ``None`` 时抛 ``ModelNotInCatalogError``：装配层不按目录推荐补模型（docs/adr/0130）。

    调用方的模型都来自用户设置的解析结果；没有模型时报错，不落到目录推荐或 backend 构造函数里写死的模型名。
    """
    if model_id is not None:
        return model_id
    raise ModelNotInCatalogError(provider_id=provider_id, model_id="", media_type=media_type)


def _callable_builtin_model(
    provider_id: str, media_type: str, model_id: str | None, *, submitted_job: bool = False
) -> str:
    """内置供应商这次调用实际使用的模型键，按今天的生命周期检查过可以调用。

    ``model_id`` 为 ``None`` 时报错（:func:`_require_builtin_model`）。
    模型已下线抛 ``ModelDiscontinuedError``，不在清单里抛 ``ModelNotInCatalogError``（见
    :func:`lib.catalog.query.require_callable`）。生命周期按当天日期判定，复用 backend 实例的调用方取缓存前另行检查
    （``server.services.tasks.generation_context``）。``submitted_job`` 为真（续跑已提交的任务）时只查是否在清单里
    （:func:`lib.catalog.query.require_listed`）。
    """
    model_id = _require_builtin_model(provider_id, media_type, model_id)
    if submitted_job:
        catalog.require_listed(provider_id, model_id, media_type)
    else:
        catalog.require_callable(provider_id, model_id, media_type)
    return model_id


def _with_model_entry(backend: Any, provider_id: str, model_id: str) -> Any:
    """让视频调用通道按模型对应的条目的名字认定请求形态，与读侧 ``builtin_video_capabilities_for_model`` 同一个条目。

    官方收录的模型取清单所引的条目，用户添加的取条目绑定或按名字现查的结果（docs/adr/0104、0105）。输入能力
    不在这里认定：执行闸门把通道声明与同一个条目两侧求值。调用通道不读条目时（声明式定义与模型无关）原样返回。
    """
    rebind = getattr(backend, "with_catalog_entry", None)
    if not callable(rebind):
        return backend
    return rebind(catalog.provider_model_entry(provider_id, model_id, "video"))


@dataclass(frozen=True)
class OutputLimitFacts:
    """模型在请求输出上限与截断出路上需要的事实。"""

    #: 模型登记的最大输出长度（单位 token）；未登记时 None。
    registered_max_output_tokens: int | None
    #: 模型由自定义供应商提供。
    custom_model: bool


async def output_limit_facts(*, provider_id: str, model_id: str, resolver: ConfigResolver) -> OutputLimitFacts:
    """读取模型登记的最大输出长度。

    与 :func:`assemble_backend` 同一道门分流：内置模型读注册表，自定义供应商的模型读模型条目。
    """
    if is_custom_provider(provider_id):
        from lib.custom_provider.loader import custom_model_max_output_tokens

        async with resolver._open_session() as (session, _):
            registered = await custom_model_max_output_tokens(
                session=session, provider_id=provider_id, model_id=model_id
            )
        return OutputLimitFacts(registered_max_output_tokens=registered, custom_model=True)
    info = catalog.get_model(provider_id, model_id)
    return OutputLimitFacts(
        registered_max_output_tokens=info.max_output_tokens if info is not None else None, custom_model=False
    )
