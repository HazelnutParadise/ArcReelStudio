"""音乐后端注册表：端点名 → 工厂。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.backends.music_backends.base import MusicBackend

_BACKEND_FACTORIES: dict[str, Callable[..., MusicBackend]] = {}


def register_backend(name: str, factory: Callable[..., MusicBackend]) -> None:
    _BACKEND_FACTORIES[name] = factory


def create_backend(name: str, **kwargs: Any) -> MusicBackend:
    if name not in _BACKEND_FACTORIES:
        raise ValueError(f"Unknown music backend: {name}")
    return _BACKEND_FACTORIES[name](**kwargs)


def get_registered_backends() -> list[str]:
    return list(_BACKEND_FACTORIES.keys())
