"""Vertex 凭证文件：装配 Vertex 后端前确认连线自己的服务账号文件存在。

凭证文件只来自生效连线（凭证记录由 id 经数据根布局推导，推导位置没有文件时用记录上的路径，见
:meth:`lib.db.models.credential.ProviderCredential.credentials_file`）或供应商配置的 ``credentials_path``。
找不到时报 :class:`VertexCredentialMissingError`，不在 ``vertex_keys/`` 里挑别的文件顶替：
那里可能是另一条连线的凭证，生成会悄悄记到别的账号上。
"""

from __future__ import annotations

from pathlib import Path

from lib.infra.api_errors import ConflictError

VERTEX_PROVIDER_ID = "gemini-vertex"


class VertexCredentialMissingError(ConflictError):
    """Vertex 后端拿不到凭证文件。

    ``connection`` 是连线名：连线存在但它的凭证文件不见了时报 ``vertex_credential_file_missing``；
    没有连线、供应商配置里也没有凭证路径时为 None，报 ``vertex_connection_missing``。
    ``key`` 与 ``params`` 同时是任务失败码与其参数（``lib.generation.task_failure.FAILURE_CODE_KEYS``）。
    """

    def __init__(self, *, connection: str | None) -> None:
        if connection is None:
            super().__init__("vertex_connection_missing")
        else:
            super().__init__("vertex_credential_file_missing", connection=connection)
        self.connection = connection


def has_vertex_credentials_file(credentials_path: str | None) -> bool:
    """同步探测文件，调用方在工作线程里调用。"""
    return bool(credentials_path) and Path(credentials_path).is_file()
