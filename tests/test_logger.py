"""Tests for logger startup degradation."""

import logging
from importlib import import_module

logger_module = import_module("src.utils.logger")


def _restore_log_config(original):
    logger_module._log_config = original


def test_setup_logger_default_no_console_handler(monkeypatch, tmp_path, capfd):
    """默认配置 (console_logging=false) 不得挂 console handler。

    控制台只输出版本横幅，日志只写文件——这是用户对启动输出的硬要求。
    """
    logger_name = "test_logger_no_console"
    test_logger = logging.getLogger(logger_name)
    root_logger = logging.getLogger()
    original_handlers = list(test_logger.handlers)
    original_root_handlers = list(root_logger.handlers)
    original_root_initialized = logger_module._root_handlers_initialized
    original_log_config = logger_module._log_config
    log_file = str(tmp_path / "test.log")

    try:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
        logger_module._root_handlers_initialized = False
        # 显式以默认 console_logging=False 配置调用
        logger_module._log_config = logger_module.LogConfig(
            log_level="INFO", log_dir="logs", console_logging=False,
        )

        configured = logger_module.setup_logger(
            name=logger_name,
            level=logging.INFO,
            log_file=log_file,
        )

        # 只有文件 handler，不得有 StreamHandler(stderr)。
        # FileHandler 是 StreamHandler 子类，需显式排除。
        stream_handlers = [
            h for h in configured.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert not stream_handlers, f"默认配置不应挂 console handler: {stream_handlers}"
        assert any(
            isinstance(h, logging.FileHandler) for h in configured.handlers
        )

        configured.error("must not reach console")
        assert capfd.readouterr().err == "", "默认配置下日志不应输出到 stderr"
    finally:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
            handler.close()
        for handler in list(root_logger.handlers):
            if handler not in original_root_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        for handler in original_handlers:
            test_logger.addHandler(handler)
        logger_module._root_handlers_initialized = original_root_initialized
        _restore_log_config(original_log_config)


def test_setup_logger_console_logging_true_adds_stream_handler(
    monkeypatch, tmp_path, capfd
):
    """console_logging=true 时挂 StreamHandler(stderr)，日志可输出到控制台。"""
    logger_name = "test_logger_with_console"
    test_logger = logging.getLogger(logger_name)
    root_logger = logging.getLogger()
    original_handlers = list(test_logger.handlers)
    original_root_handlers = list(root_logger.handlers)
    original_root_initialized = logger_module._root_handlers_initialized
    original_log_config = logger_module._log_config
    log_file = str(tmp_path / "test.log")

    try:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
        logger_module._root_handlers_initialized = False
        logger_module._log_config = logger_module.LogConfig(
            log_level="INFO", log_dir="logs", console_logging=True,
        )

        configured = logger_module.setup_logger(
            name=logger_name,
            level=logging.INFO,
            log_file=log_file,
        )

        # FileHandler 是 StreamHandler 子类，需显式排除
        stream_handlers = [
            h for h in configured.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1, (
            f"console_logging=true 应挂一个 StreamHandler, got {configured.handlers}"
        )

        configured.error("console test message")
        captured = capfd.readouterr()
        assert "console test message" in captured.err, (
            "console_logging=true 时日志应输出到 stderr"
        )
    finally:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
            handler.close()
        for handler in list(root_logger.handlers):
            if handler not in original_root_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        for handler in original_handlers:
            test_logger.addHandler(handler)
        logger_module._root_handlers_initialized = original_root_initialized
        _restore_log_config(original_log_config)


def test_setup_logger_ignores_unwritable_file(monkeypatch, tmp_path, capfd):
    """An unwritable log file must warn once and leave logging usable."""
    logger_name = "test_logger_unwritable_file"
    test_logger = logging.getLogger(logger_name)
    root_logger = logging.getLogger()
    original_handlers = list(test_logger.handlers)
    original_root_handlers = list(root_logger.handlers)
    original_root_initialized = logger_module._root_handlers_initialized
    original_warning_emitted = logger_module._file_logging_warning_emitted

    def raise_permission_error(*args, **kwargs):
        raise PermissionError("test denied")

    try:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
        monkeypatch.setattr(logging, "FileHandler", raise_permission_error)
        logger_module._root_handlers_initialized = False
        logger_module._file_logging_warning_emitted = False

        configured = logger_module.setup_logger(
            name=logger_name,
            level=logging.INFO,
            log_file=str(tmp_path / "denied.log"),
        )

        captured = capfd.readouterr()
        assert "日志目录无法写入" in captured.err
        assert "后续文件日志将被忽略" in captured.err
        assert any(isinstance(h, logging.NullHandler) for h in configured.handlers)

        configured.error("this must be ignored")
        assert capfd.readouterr().err == ""
    finally:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)
            handler.close()
        for handler in list(root_logger.handlers):
            if handler not in original_root_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        for handler in original_handlers:
            test_logger.addHandler(handler)
        logger_module._root_handlers_initialized = original_root_initialized
        logger_module._file_logging_warning_emitted = original_warning_emitted
