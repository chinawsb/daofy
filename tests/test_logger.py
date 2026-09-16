"""Tests for logger startup degradation."""

import io
import logging
import os
import time
from importlib import import_module

import pytest

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


def test_safe_stderr_handler_nonblocking_when_pipe_full():
    """核心回归：管道写满（客户端不排空 stderr）时 emit 必须快速返回。

    MCP stdio 场景：客户端不读 stderr → 管道满 → 同步 emit 若阻塞会卡死
    整个 asyncio 事件循环（连 initialize 都回应不了）。_SafeStderrHandler
    必须保证调用方永不阻塞。
    """
    r, w = os.pipe()
    handler = None
    stream = None
    try:
        try:
            os.set_blocking(w, False)
        except OSError:
            pytest.skip("os.set_blocking 不可用")
        # 灌满管道缓冲
        try:
            os.write(w, b"x" * 100000)
        except (BlockingIOError, OSError):
            pass

        stream = io.TextIOWrapper(
            io.FileIO(w, "wb", closefd=False),
            encoding="utf-8", write_through=True, line_buffering=True,
        )
        handler = logger_module._SafeStderrHandler(stream, logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = logging.LogRecord("t", logging.INFO, "f", 1, "fill-click", None, None)

        t0 = time.monotonic()
        handler.emit(record)
        handler.emit(record)
        dt = time.monotonic() - t0
        assert dt < 0.5, f"管道满时 emit 阻塞了 {dt:.3f}s"
    finally:
        if handler is not None:
            handler.close()
        if stream is not None:
            stream.close()
        os.close(r)
        os.close(w)


def test_safe_stderr_handler_close_keeps_stream_open():
    """_SafeStderrHandler.close() 不得关闭底层流（sys.stderr 全局共享）。"""
    stream = io.StringIO()
    handler = logger_module._SafeStderrHandler(stream, logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("t", logging.INFO, "f", 1, "console msg", None, None)
    handler.emit(record)  # StringIO 无 fd → 直写路径
    handler.close()
    assert not stream.closed, "close() 不应关闭底层的 sys.stderr"
    assert "console msg" in stream.getvalue()
