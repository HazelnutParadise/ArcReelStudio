"""Vertex 凭证文件的定位：后端没有拿到凭证记录给出的文件时，按数据根布局查找。

This module intentionally avoids importing lib/__init__.py to prevent circular
imports during early environment initialization.
"""

from __future__ import annotations

from pathlib import Path


def resolve_vertex_credentials_path(data_root: Path | None = None) -> Path | None:
    """
    Resolve the Vertex credentials JSON file to use.

    Searches ``<credentials_dir>/vertex_credentials.json`` first, then falls
    back to the first ``*.json`` file (by name) in ``<credentials_dir>/``.

    ``credentials_dir`` is the Vertex credentials directory given by the data
    root layout (the configured data root unless ``data_root`` is passed),
    where :func:`server.routers.providers.upload_vertex_credential` writes
    uploads as ``vertex_cred_<credential id>.json``.
    """
    from lib.infra.data_root_layout import DataRootLayout

    layout = DataRootLayout.current() if data_root is None else DataRootLayout(Path(data_root))
    credentials_dir = layout.vertex_keys_dir
    preferred = credentials_dir / "vertex_credentials.json"
    if preferred.exists():
        return preferred
    if not credentials_dir.exists():
        return None
    candidates = sorted(credentials_dir.glob("*.json"))
    return candidates[0] if candidates else None
