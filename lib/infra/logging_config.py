"""统一日志配置。"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import httpx2

from lib.infra.data_root_layout import DataRootLayout

_HANDLER_ATTR = "_arcreel_logging"
_FILE_HANDLER_ATTR = "_arcreel_file_logging"
_DISABLED_TRUTHY = frozenset({"1", "true", "yes"})


class _StripUrlQueryFilter(logging.Filter):
    """httpx2 在 INFO 级别记录每个请求的完整 URL。预签名 URL 的 query 在有效期内等同下载凭证，记录前去掉 query。"""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and any(isinstance(arg, httpx2.URL) and arg.query for arg in args):
            record.args = tuple(
                arg.copy_with(query=None) if isinstance(arg, httpx2.URL) and arg.query else arg for arg in args
            )
        return True


def _install_httpx_url_redaction() -> None:
    httpx_logger = logging.getLogger("httpx2")
    if not any(isinstance(f, _StripUrlQueryFilter) for f in httpx_logger.filters):
        httpx_logger.addFilter(_StripUrlQueryFilter())


def _file_logging_disabled() -> bool:
    return os.environ.get("ARCREEL_LOG_FILE_DISABLED", "").strip().lower() in _DISABLED_TRUTHY


def resolve_log_dir() -> Path:
    """文件日志目录：``<数据根>/logs``（``DataRootLayout.log_dir``）。"""
    return DataRootLayout.current().log_dir


def setup_logging(level: str | None = None, *, file: bool = True) -> None:
    """配置根 logger。

    Args:
        level: 日志级别字符串（DEBUG/INFO/WARNING/ERROR）。
               如未提供，从环境变量 LOG_LEVEL 读取，默认 INFO。
        file: 是否挂 TimedRotatingFileHandler。模块导入期传 False 推迟到
              lifespan 之后挂——避免 import 期在数据根下创建 logs/。
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 幂等：避免重复添加 stream handler
    if not any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        setattr(handler, _HANDLER_ATTR, True)
        root.addHandler(handler)

    if file:
        attach_file_handler(formatter)

    # 统一 uvicorn 的日志格式，避免两种格式并存
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # 禁用 uvicorn.access：请求日志由 app.py 的 middleware 统一处理
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True

    # 抑制 aiosqlite 的 DEBUG 噪音（每次 SQL 操作都会输出两行日志）
    logging.getLogger("aiosqlite").setLevel(max(numeric_level, logging.INFO))

    # TOS SDK 在 INFO 级别记录重试时会带上请求体（上传的对象内容），DEBUG 级别记录签名过程；
    # 媒体内容与签名不进普通诊断日志，只放行 WARNING 及以上。
    logging.getLogger("tos").setLevel(max(numeric_level, logging.WARNING))

    # 供应商签发的素材与产物下载地址带签名参数，请求日志只保留去掉 query 的地址。
    _install_httpx_url_redaction()


def attach_file_handler(formatter: logging.Formatter | None = None) -> None:
    """为 root logger 挂 TimedRotatingFileHandler（默认开启，按天切，保留 7 份）。

    幂等：已挂则直接返回。被 setup_logging 调用，也可在 lifespan 内单独触发。
    """
    if _file_logging_disabled():
        return

    root = logging.getLogger()
    if any(getattr(h, _FILE_HANDLER_ATTR, False) for h in root.handlers):
        return

    if formatter is None:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    try:
        log_dir = resolve_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=str(log_dir / "arcreel.log"),
            when="midnight",
            backupCount=7,
            encoding="utf-8",
            utc=False,
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _FILE_HANDLER_ATTR, True)
        root.addHandler(file_handler)
    except Exception as exc:
        logging.getLogger(__name__).warning("file logging disabled: %s", exc)
