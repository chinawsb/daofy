"""
日志工具模块

提供统一的日志配置和获取方法
功能:
- 按日期分文件日志 (delphi_mcp_YYYY-MM-DD.log)
- 历史日志自动 7z 压缩归档
- API 调用参数/返回值日志 (受配置开关控制)
"""

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------

@dataclass
class LogConfig:
    """日志配置"""
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_api_calls: bool = False
    archive_old_logs: bool = True
    keep_days: int = 7


_CONFIG_FILE_NAME = "config/logging_config.json"
_LOG_FORMAT = "%(asctime)s - PID:%(process)d - %(name)s - %(levelname)s - %(message)s"
_LOG_FILE_PREFIX = "delphi_mcp"

# 缓存配置
_log_config: Optional[LogConfig] = None


def _get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


def _load_log_config() -> LogConfig:
    """从 config/logging_config.json 加载日志配置"""
    global _log_config
    if _log_config is not None:
        return _log_config

    cfg_path = _get_project_root() / _CONFIG_FILE_NAME
    config = LogConfig()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.log_level = data.get("log_level", config.log_level).upper()
            config.log_dir = data.get("log_dir", config.log_dir)
            config.log_api_calls = data.get("log_api_calls", config.log_api_calls)
            config.archive_old_logs = data.get("archive_old_logs", config.archive_old_logs)
            config.keep_days = int(data.get("keep_days", config.keep_days))
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))
    _log_config = config
    return config


def reload_log_config() -> LogConfig:
    """重新加载日志配置（运行时更新用）"""
    global _log_config
    _log_config = None
    return _load_log_config()


def should_log_api_calls() -> bool:
    """检查是否启用了 API 调用日志"""
    return _load_log_config().log_api_calls


# ---------------------------------------------------------------------------
# 历史日志 7z 归档
# ---------------------------------------------------------------------------

def _find_7z_path() -> Optional[str]:
    """查找 7z 可执行文件路径"""
    # 优先用项目自带的 tools/7z/7z.exe
    builtin = _get_project_root() / "tools" / "7z" / "7z.exe"
    if builtin.exists():
        return str(builtin)
    # 系统安装路径
    for path in [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]:
        if Path(path).exists():
            return path
    return None


def archive_old_logs(log_dir: Optional[str] = None) -> None:
    """
    将历史日志文件压缩为 7z 并删除原文件。
    每天只保留一个 7z 归档。超过 keep_days 天的旧归档自动删除。

    多进程安全: 使用 pid 文件互斥，避免同时归档。

    Args:
        log_dir: 日志目录，默认从配置读取
    """
    config = _load_log_config()
    if not config.archive_old_logs:
        return

    log_path = Path(log_dir) if log_dir else _get_project_root() / config.log_dir
    if not log_path.exists():
        return

    seven_z = _find_7z_path()
    if not seven_z:
        return  # 无 7z 工具，跳过归档

    # 多进程互斥锁: 用 .archive_lock 文件防止并行归档
    lock_file = log_path / ".archive_lock"
    if lock_file.exists():
        return  # 其他进程正在归档，跳过
    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        return

    try:
        today_str = date.today().isoformat()  # YYYY-MM-DD
        keep_days = max(config.keep_days, 1)

        # ---------------------------------------------------------------
        # 1) 删除超出保留天数的旧 .7z 归档
        # ---------------------------------------------------------------
        for archive_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.7z")):
            stem = archive_file.stem
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            try:
                file_date = date.fromisoformat(date_part)
                if (date.today() - file_date).days > keep_days:
                    archive_file.unlink()
            except (ValueError, OverflowError):
                pass  # 文件名格式不符，跳过

        # ---------------------------------------------------------------
        # 2) 压缩旧 .log 文件到 .7z
        # ---------------------------------------------------------------
        for log_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.log")):
            # 从文件名提取日期: delphi_mcp_YYYY-MM-DD.log
            stem = log_file.stem  # delphi_mcp_YYYY-MM-DD
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            if date_part == today_str:
                continue  # 今天的日志不归档

            archive_name = log_path / f"{stem}.7z"
            if archive_name.exists():
                # 已存在归档，删掉源文件（可能上次压缩成功但没删掉）
                try:
                    log_file.unlink()
                except Exception as e:
                    logger.debug("忽略非致命异常: %s", str(e))
                continue

            # 用 7z 压缩
            try:
                result = subprocess.run(
                    [seven_z, "a", "-t7z", "-mx=5", str(archive_name), str(log_file)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0 and archive_name.exists():
                    log_file.unlink()
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
    finally:
        # 释放锁
        try:
            lock_file.unlink()
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))


# ---------------------------------------------------------------------------
# Logger 核心
# ---------------------------------------------------------------------------

def _resolve_log_level(level_str: str = "INFO") -> int:
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(level_str.upper(), logging.INFO)


def _get_today_log_path(log_dir: Path) -> Path:
    """生成当天的日志文件路径: logs/delphi_mcp_YYYY-MM-DD.log"""
    today_str = date.today().isoformat()
    return log_dir / f"{_LOG_FILE_PREFIX}_{today_str}.log"


_initialized = False


_root_handlers_initialized = False


def setup_logger(
    name: str = "delphi_mcp",
    level: Optional[int] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    配置并返回日志记录器。

    handler 会同时挂载到 root logger，确保所有子模块
    (通过 get_logger(__name__) 获取的独立 logger) 的日志也能正常输出。

    Args:
        name: 日志记录器名称
        level: 日志级别, 不传则从配置读取
        log_file: 日志文件路径, 不传则使用日期文件
        format_string: 日志格式字符串

    Returns:
        配置好的日志记录器
    """
    global _root_handlers_initialized

    logger = logging.getLogger(name)
    if logger.handlers and _root_handlers_initialized:
        return logger

    if level is None:
        level = _resolve_log_level(_load_log_config().log_level)
    logger.setLevel(level)

    if format_string is None:
        format_string = _LOG_FORMAT
    formatter = logging.Formatter(format_string)

    # 控制台处理器 (stderr, 避免干扰 MCP stdio)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file or _load_log_config().log_dir:
        if log_file:
            log_path = Path(log_file)
        else:
            log_dir = _get_project_root() / _load_log_config().log_dir
            log_path = _get_today_log_path(log_dir)

        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # 同时挂载 handler 到 root logger
    # 否则 get_logger(__name__) 创建的子 logger 日志传播到 root 时，
    # 因 root 无 handler 而丢失。
    if not _root_handlers_initialized:
        root = logging.getLogger()
        # 避免重复添加
        existing = {str(h) for h in root.handlers}
        for h in logger.handlers:
            if str(h) not in existing:
                root.addHandler(h)
        _root_handlers_initialized = True

    # 禁止 delphi_mcp 向上传播到 root，否则 handler 会执行两次造成重复
    if name != "":
        logger.propagate = False

    return logger


def get_logger(name: str = "delphi_mcp") -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# 默认日志记录器
# ---------------------------------------------------------------------------

_default_logger: Optional[logging.Logger] = None


def init_default_logger(log_file: Optional[str] = None) -> logging.Logger:
    """
    初始化默认日志记录器。
    首次调用时自动执行: 加载配置 + 归档旧日志 + 设置日志记录器。

    注意: 各模块通过 get_logger(__name__) 获取独立子 logger，
    它们的级别继承自 root logger。因此必须同时设置 root 级别。
    否则仅设置 "delphi_mcp" 的级别，其他模块的 DEBUG 日志不会被输出。

    Args:
        log_file: 日志文件路径, 不传则使用日期文件

    Returns:
        默认日志记录器
    """
    global _default_logger, _initialized

    if _default_logger is not None and _initialized:
        return _default_logger

    # 1) 加载配置
    config = _load_log_config()
    level = _resolve_log_level(config.log_level)

    # 2) 设置 root logger 级别（确保所有模块的子 logger 继承正确的级别）
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 3) 归档旧日志 (仅首次)
    if not _initialized:
        archive_old_logs()

    # 4) 设置日志
    if log_file is None:
        log_dir = _get_project_root() / config.log_dir
        log_file = str(_get_today_log_path(log_dir))

    _default_logger = setup_logger(log_file=log_file, level=level)
    _default_logger.info(f"日志系统初始化完成 - 级别: {config.log_level}, 文件: {log_file}")
    _initialized = True
    return _default_logger


def get_default_logger() -> logging.Logger:
    """获取默认日志记录器"""
    global _default_logger
    if _default_logger is None:
        _default_logger = init_default_logger()
    return _default_logger


# ---------------------------------------------------------------------------
# API 调用日志 (受开关控制)
# ---------------------------------------------------------------------------

def log_api_call(logger: logging.Logger, tool_name: str, arguments: dict, result) -> None:
    """
    记录 API 调用参数和返回值。
    只在 log_api_calls=True 时生效。

    Args:
        logger: 日志记录器
        tool_name: 工具名
        arguments: 调用参数
        result: 返回值
    """
    if not should_log_api_calls():
        return

    # 过滤敏感参数 (如路径中的密码)
    safe_args = {}
    for k, v in arguments.items():
        if any(sensitive in k.lower() for sensitive in ("password", "secret", "token", "key")):
            safe_args[k] = "****"
        else:
            safe_args[k] = v

    logger.debug(">>> API 调用: %s | 参数: %s", tool_name, json.dumps(safe_args, ensure_ascii=False))

    # 记录返回值 (截断避免日志过大)
    result_str = str(result)
    if len(result_str) > 2000:
        result_str = result_str[:2000] + "... (truncated)"

    logger.debug("<<< API 返回: %s | 结果: %s", tool_name, result_str)
