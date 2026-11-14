"""TimedRotatingFileHandler 注册与降级行为测试。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from lib.infra import app_data_dir as app_data_dir_mod
from lib.infra import logging_config


@pytest.fixture(autouse=True)
def reset_root_logger():
    """每个用例前后清空 root logger handlers，避免污染。

    setup_logging() / attach_file_handler() 不止改 root.handlers——还动
    root.level 以及 uvicorn*/aiosqlite 等命名 logger 的 handlers/disabled/
    propagate。teardown 必须把这些都恢复，并 close() 临时挂的 file handler
    以释放 fd（Windows 上 file locking 尤其敏感）。
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    named_loggers = {
        name: logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiosqlite")
    }
    saved_named = {
        name: (list(logger.handlers), logger.level, logger.disabled, logger.propagate)
        for name, logger in named_loggers.items()
    }
    root.handlers.clear()
    yield
    # 关闭测试中临时挂的 handler 释放 fd
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(saved_level)
    root.handlers[:] = saved_handlers
    for name, logger in named_loggers.items():
        handlers, level, disabled, propagate = saved_named[name]
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.disabled = disabled
        logger.propagate = propagate


@pytest.fixture
def isolated_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """数据根钉到 tmp_path/data，文件日志应落在 ``<数据根>/logs``。"""
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ARCREEL_LOG_DIR", raising=False)
    monkeypatch.delenv("ARCREEL_LOG_FILE_DISABLED", raising=False)
    app_data_dir_mod.reset_for_tests()
    yield tmp_path / "data" / "logs"
    app_data_dir_mod.reset_for_tests()


def test_file_handler_registered_by_default(isolated_log_dir: Path) -> None:
    logging_config.setup_logging()
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(file_handlers) == 1
    assert Path(file_handlers[0].baseFilename).parent == isolated_log_dir.resolve()


def test_logs_written_to_file(isolated_log_dir: Path) -> None:
    logging_config.setup_logging()
    logging.getLogger("test.persistence").info("hello-arcreel")
    for h in logging.getLogger().handlers:
        h.flush()
    log_file = isolated_log_dir / "arcreel.log"
    assert log_file.exists()
    assert "hello-arcreel" in log_file.read_text(encoding="utf-8")


def test_mkdir_failure_graceful(isolated_log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = isolated_log_dir.resolve()

    real_mkdir = Path.mkdir

    def fake_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == target:
            raise PermissionError("simulated read-only fs")
        real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    logging_config.setup_logging()  # 不抛
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers)


def test_idempotent(isolated_log_dir: Path) -> None:
    logging_config.setup_logging()
    logging_config.setup_logging()
    logging_config.setup_logging()
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(file_handlers) == 1


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_disabled_env_accepts_aliases(isolated_log_dir: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ARCREEL_LOG_FILE_DISABLED", value)
    logging_config.setup_logging()
    root = logging.getLogger()
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers)


# --- 日志位置 -----------------------------------------------------------------


@pytest.fixture
def isolated_data_dir(tmp_path: Path, isolated_log_dir: Path) -> Path:
    """数据根为 tmp_path/data。"""
    (tmp_path / "data").mkdir()
    return tmp_path


def _emit_and_read_log(log_dir: Path) -> str:
    logging.getLogger("test.persistence").info("hello-arcreel")
    for h in logging.getLogger().handlers:
        h.flush()
    return (log_dir / "arcreel.log").read_text(encoding="utf-8")


def test_log_dir_env_is_ignored(isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = isolated_data_dir / "custom-logs"
    monkeypatch.setenv("ARCREEL_LOG_DIR", str(custom))

    logging_config.setup_logging()

    assert "hello-arcreel" in _emit_and_read_log(isolated_data_dir / "data" / "logs")
    assert not custom.exists()


def test_log_dir_env_set_warns_once(
    isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ARCREEL_LOG_DIR", str(isolated_data_dir / "custom-logs"))

    with caplog.at_level(logging.WARNING, logger="lib.infra.logging_config"):
        logging_config.warn_if_log_dir_env_set()

    assert [rec.levelno for rec in caplog.records] == [logging.WARNING]


def test_log_dir_env_unset_no_warning(isolated_data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="lib.infra.logging_config"):
        logging_config.warn_if_log_dir_env_set()

    assert caplog.records == []


def test_log_dir_occupied_by_project_is_left_untouched(
    isolated_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``<数据根>/logs`` 是一个项目目录时不挂文件日志，项目目录原样不动，并告警一次。"""
    project = isolated_data_dir / "data" / "logs"
    project.mkdir()
    (project / "project.json").write_text("{}", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="lib.infra.logging_config"):
        logging_config.setup_logging()
        logging.getLogger("test.persistence").info("hello-arcreel")

    assert sorted(p.name for p in project.iterdir()) == ["project.json"]
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in logging.getLogger().handlers)
    assert [rec.levelno for rec in caplog.records if rec.name == "lib.infra.logging_config"] == [logging.WARNING]


def test_setup_logging_file_false_skips_file_handler(isolated_log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """模块导入期用 file=False 时不应挂 file handler、不应 mkdir 新目录。"""
    # 注意：isolated_log_dir 指向的数据根日志目录尚未创建
    log_dir = isolated_log_dir
    assert not log_dir.exists()

    logging_config.setup_logging(file=False)

    root = logging.getLogger()
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers)
    assert not log_dir.exists(), "file=False 不应触发 mkdir"


def test_attach_file_handler_is_idempotent(isolated_log_dir: Path) -> None:
    """attach_file_handler() 多次调用只挂一个 file handler。"""
    logging_config.setup_logging(file=False)
    logging_config.attach_file_handler()
    logging_config.attach_file_handler()
    logging_config.attach_file_handler()

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(file_handlers) == 1
