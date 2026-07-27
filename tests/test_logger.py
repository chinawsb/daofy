"""Tests for logger startup degradation."""

import logging
from importlib import import_module

logger_module = import_module("src.utils.logger")


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
