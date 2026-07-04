"""
pasfmt 代码格式化工具

提供 Delphi 代码格式化功能，使用 pasfmt 工具进行代码格式化
包括下载、安装和配置功能
"""

import os
import sys
import subprocess
import tempfile
import zipfile
import shutil
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from mcp.types import CallToolResult, TextContent

try:
    from ..constants import (
        CHUNK_SIZE_DOWNLOAD,
        REG_KEY_EMBARCADERO_BDS,
        TIMEOUT_NETWORK_REQUEST,
        TIMEOUT_PASFMT,
        TIMEOUT_PASFMT_BUILD,
        TIMEOUT_PASFMT_GIT_CLONE,
    )
    from ..utils.logger import get_logger
    from ..utils.file_backup import create_backup as _create_backup, detect_encoding as _detect_encoding, list_backups as _list_backups
except ImportError:
    try:
        from src.constants import (
            CHUNK_SIZE_DOWNLOAD,
            REG_KEY_EMBARCADERO_BDS,
            TIMEOUT_NETWORK_REQUEST,
            TIMEOUT_PASFMT,
            TIMEOUT_PASFMT_BUILD,
            TIMEOUT_PASFMT_GIT_CLONE,
        )
        from src.utils.logger import get_logger
        from src.utils.file_backup import create_backup as _create_backup, detect_encoding as _detect_encoding, list_backups as _list_backups
    except ImportError:
        import logging
        CHUNK_SIZE_DOWNLOAD = 8192
        REG_KEY_EMBARCADERO_BDS = r"SOFTWARE\Embarcadero\BDS"
        TIMEOUT_NETWORK_REQUEST = 30
        TIMEOUT_PASFMT = 30
        TIMEOUT_PASFMT_BUILD = 600
        TIMEOUT_PASFMT_GIT_CLONE = 300

        def get_logger(name: str) -> logging.Logger:
            logger = logging.getLogger(name)
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
            return logger

logger = get_logger(__name__)

# pasfmt 可执行文件路径
_PASFMT_PATH: Optional[str] = None

# uses 子句风格: "compact"=合并为一行, "pasfmt_default"=保留 pasfmt 每行一个
_USES_STYLE: str = "compact"

# 下载源配置
PASFMT_DOWNLOAD_SOURCES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    },
    {
        "name": "GitHub Mirror 2", 
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    }
]

# pasfmt-rad 下载源配置
PASFMT_RAD_DOWNLOAD_SOURCES = [
    {
        "name": "GitHub",
        "base_url": "https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    },
    {
        "name": "GitHub Mirror 1",
        "base_url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    },
    {
        "name": "GitHub Mirror 2",
        "base_url": "https://download.fastgit.org/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    }
]

# 源码编译配置
PASFMT_SOURCE_REPOSITORIES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt.git",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt.git"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt.git"
    },
    {
        "name": "GitHub Mirror 2",
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt.git"
    }
]

PASFMT_RAD_SOURCE_REPOSITORIES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt-rad.git",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad.git"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad.git"
    },
    {
        "name": "GitHub Mirror 2",
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt-rad.git"
    }
]

# Delphi 版本映射
DELPHI_VERSIONS = {
    "11": {"name": "Alexandria", "bpl_32": "Pasfmt_11_Alexandria.bpl", "bpl_64": None},
    "12": {"name": "Athens", "bpl_32": "Pasfmt_12_Athens.bpl", "bpl_64": "Pasfmt_12_Athens_64.bpl"},
    "13": {"name": "Florence", "bpl_32": "Pasfmt_13_Florence.bpl", "bpl_64": "Pasfmt_13_Florence_64.bpl"}
}

_DELPHI_TO_BDS_REGISTRY_VERSION = {
    "11": "22.0",
    "12": "23.0",
    "13": "37.0",
}


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _pasfmt_default_paths() -> list[str]:
    return [str(_project_root() / "tools" / "pasfmt" / "cli" / "pasfmt.exe")]


def _bds_registry_version(delphi_version: str) -> str:
    return _DELPHI_TO_BDS_REGISTRY_VERSION.get(delphi_version, delphi_version)


def _pasfmt_rad_candidate_dirs(delphi_version: str) -> list[str]:
    project_rad_dir = str(_project_root() / "tools" / "pasfmt" / "rad")
    possible_dirs = [project_rad_dir]
    if sys.platform == "win32":
        try:
            from ..utils.delphi_env import get_delphi_root_dir
        except ImportError:
            from src.utils.delphi_env import get_delphi_root_dir

        root_dir = get_delphi_root_dir(_bds_registry_version(delphi_version))
        if root_dir:
            possible_dirs.append(str(Path(root_dir) / "bin"))
    return possible_dirs


def set_pasfmt_path(path: str):
    """设置 pasfmt 可执行文件路径"""
    global _PASFMT_PATH
    _PASFMT_PATH = path
    logger.info(f"设置 pasfmt 路径: {path}")


def get_pasfmt_path() -> Optional[str]:
    """获取 pasfmt 可执行文件路径"""
    global _PASFMT_PATH
    
    if _PASFMT_PATH:
        return _PASFMT_PATH
    
    # 尝试从环境变量获取
    env_path = os.environ.get('PASFMT_PATH')
    if env_path and os.path.exists(env_path):
        _PASFMT_PATH = env_path
        return _PASFMT_PATH
    
    # 尝试从 PATH 环境变量搜索
    path_in_path = shutil.which('pasfmt') or shutil.which('pasfmt.exe')
    if path_in_path:
        _PASFMT_PATH = path_in_path
        logger.info(f"找到 pasfmt 在 PATH 中: {path_in_path}")
        return path_in_path
    
    # 尝试从默认安装位置获取
    default_paths = _pasfmt_default_paths()
    
    for path in default_paths:
        if os.path.exists(path):
            _PASFMT_PATH = path
            logger.info(f"找到 pasfmt 在默认位置: {path}")
            return path
    
    logger.warning("未找到 pasfmt 可执行文件")
    return None


def set_uses_style(style: str) -> None:
    """设置 uses 子句风格: "compact"=合并为一行, "pasfmt_default"=保留 pasfmt 原样"""
    global _USES_STYLE
    if style not in ("compact", "pasfmt_default"):
        logger.warning(f"未知的 uses_style: {style}，使用默认 compact")
        _USES_STYLE = "compact"
    else:
        _USES_STYLE = style
        logger.info(f"设置 uses 风格: {style}")


def get_uses_style() -> str:
    """获取当前 uses 子句风格设置"""
    return _USES_STYLE


def _compact_uses_clause(content: str) -> str:
    """
    将 pasfmt 展开的多行 uses 子句压缩回单行。

    pasfmt 默认:
      uses
        System.SysUtils,
        System.Classes;

    压缩后:
      uses System.SysUtils, System.Classes;
    """
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        trimmed = line.strip()

        # 检测独占一行的 "uses"（pasfmt 风格）
        if trimmed.lower() == 'uses' and not trimmed.endswith(';'):
            items = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_trimmed = next_line.strip()

                # 空行或非缩进行 = uses 块结束
                if not next_trimmed or not (next_line.startswith(' ') or next_line.startswith('\t')):
                    break

                item = next_trimmed.rstrip(',').rstrip(';').strip()
                if item:
                    items.append(item)

                if next_trimmed.endswith(';'):
                    j += 1
                    break  # 分号结束
                j += 1

            if items:
                indent = line[:len(line) - len(trimmed)]
                result.append(f"{indent}uses {', '.join(items)};")
                i = j
                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


async def format_file(
    file_path: str,
    config_path: Optional[str] = None,
    backup: bool = True,
    in_place: bool = True,
    dry_run: bool = False,
    uses_style: Optional[str] = None
) -> Dict[str, Any]:
    """
    格式化 Delphi 源代码文件

    Args:
        file_path: 要格式化的 Delphi 文件路径
        config_path: pasfmt 配置文件路径（可选）
        backup: 是否创建备份文件（在 __history 目录下）
        in_place: 是否原地格式化（修改原文件）
        dry_run: 仅检查格式，不实际修改文件
        uses_style: uses 子句风格，None=使用全局设置, "compact"=合并为一行, "pasfmt_default"=保留 pasfmt 原样

    Returns:
        格式化结果字典
    """
    logger.info(f"收到格式化请求: {file_path}")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        error_msg = f"文件不存在: {file_path}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "FILE_NOT_FOUND",
            "error_message": error_msg,
            "formatted": False
        }
    
    # 获取 pasfmt 路径
    pasfmt_path = get_pasfmt_path()
    if not pasfmt_path:
        error_msg = (
            "pasfmt 未安装。下载地址: https://github.com/integrated-application-development/pasfmt/releases\n"
            "由 AI Agent 根据操作系统下载最新版本并安装"
        )
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "PASFMT_NOT_FOUND",
            "error_message": error_msg,
            "formatted": False
        }
    
    # 检测文件编码（使用公共函数）
    encoding = _detect_encoding(file_path)
    
    # 创建备份（使用公共函数）
    backup_path = None
    if backup:
        backup_path = _create_backup(file_path)
    
    # 构建 pasfmt 命令
    cmd = [pasfmt_path]
    
    # 添加配置文件参数
    if config_path and os.path.exists(config_path):
        cmd.extend(["--config-file", config_path])
    
    # 添加模式参数
    if dry_run:
        cmd.extend(["--mode", "check"])
    elif in_place:
        cmd.extend(["--mode", "files"])
    else:
        cmd.extend(["--mode", "stdout"])
    
    # 添加输入文件
    cmd.append(file_path)
    
    try:
        # 执行 pasfmt
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=TIMEOUT_PASFMT,  # 30秒超时
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        # 处理输出
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if dry_run:
            # check 模式：returncode != 0 表示格式不正确，这是正常行为
            if result.returncode != 0:
                # 有格式问题 - 解析 stderr 获取文件名
                all_output = stderr.strip()
                lines = all_output.split('\n')
                # 提取文件名行 (包含 "ERROR CHECK:" 或 "has incorrect formatting" 的行)
                issues = []
                for line in lines:
                    if line and ('incorrect formatting' in line or 'CHECK:' in line):
                        # 提取文件名
                        if "has incorrect formatting" in line:
                            # 格式: "ERROR CHECK: 'filepath' has incorrect formatting"
                            import re
                            match = re.search(r"'([^']+)'", line)
                            if match:
                                issues.append(match.group(1))
                        elif "CHECK:" in line:
                            issues.append(line)
                
                return {
                    "status": "success",
                    "formatted": False,
                    "dry_run": True,
                    "issues": issues if issues else [all_output],
                    "message": "代码格式检查完成，发现格式问题",
                    "backup_file": backup_path
                }
            else:
                # 格式正确
                return {
                    "status": "success",
                    "formatted": True,
                    "dry_run": True,
                    "issues": [],
                    "message": "代码格式正确",
                    "backup_file": backup_path
                }
        
        # 非 check 模式
        if result.returncode == 0:
            # 格式化成功
            if not in_place:
                # 从 stdout 读取格式化后的内容
                # pasfmt stdout 模式会输出 "filepath:\nformatted_code"，需要去掉文件名前缀
                _lines = stdout.split('\n', 1)
                if len(_lines) > 1 and ':' in _lines[0]:
                    formatted_content = _lines[1]
                else:
                    formatted_content = stdout
                return {
                    "status": "success",
                    "formatted": True,
                    "content": formatted_content,
                    "message": "代码格式化成功",
                    "backup_file": backup_path
                }
            else:
                # in_place 成功，应用 uses 压缩后处理
                effective_uses_style = uses_style if uses_style is not None else _USES_STYLE
                if effective_uses_style == "compact":
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            file_content = f.read()
                        compacted = _compact_uses_clause(file_content)
                        if compacted != file_content:
                            with open(file_path, 'w', encoding=encoding) as f:
                                f.write(compacted)
                            logger.info(f"uses 子句已压缩: {file_path}")
                    except Exception as e:
                        logger.warning(f"uses 压缩失败: {str(e)}")

                return {
                    "status": "success",
                    "formatted": True,
                    "message": "代码格式化成功",
                    "backup_file": backup_path
                }
        else:
            # 失败
            error_msg = f"pasfmt 执行失败 (退出码: {result.returncode})"
            if stderr:
                error_msg += f": {stderr}"
            elif stdout:
                error_msg += f": {stdout}"
            
            logger.error(error_msg)
            return {
                "status": "failed",
                "error_code": "PASFMT_EXECUTION_FAILED",
                "error_message": error_msg,
                "formatted": False,
                "backup_file": backup_path
            }
            
    except subprocess.TimeoutExpired:
        error_msg = "pasfmt 执行超时"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "TIMEOUT",
            "error_message": error_msg,
            "formatted": False,
            "backup_file": backup_path
        }
    except Exception as e:
        error_msg = f"执行 pasfmt 时发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "EXECUTION_ERROR",
            "error_message": error_msg,
            "formatted": False,
            "backup_file": backup_path
        }


async def format_code(
    code: str,
    config_path: Optional[str] = None,
    uses_style: Optional[str] = None
) -> CallToolResult:
    """
    格式化 Delphi 代码字符串

    Args:
        code: 要格式化的 Delphi 代码
        config_path: pasfmt 配置文件路径（可选）
        uses_style: uses 子句风格，None=使用全局设置, "compact"=合并为一行, "pasfmt_default"=保留 pasfmt 原样

    Returns:
        格式化结果字典
    """
    logger.info("收到代码字符串格式化请求")
    
    # 获取 pasfmt 路径
    pasfmt_path = get_pasfmt_path()
    if not pasfmt_path:
        error_msg = (
            "pasfmt 未安装。下载地址: https://github.com/integrated-application-development/pasfmt/releases\n"
            "由 AI Agent 根据操作系统下载最新版本并安装"
        )
        logger.error(error_msg)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
    
    # 创建临时文件（先保存路径再写内容，避免 write 异常导致 temp_input 未定义）
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pas', delete=False, encoding='utf-8') as tmp:
        temp_input = tmp.name
        tmp.write(code)
    
    try:
        # 构建 pasfmt 命令
        cmd = [pasfmt_path]
        
        # 添加配置文件参数
        if config_path and os.path.exists(config_path):
            cmd.extend(["--config-file", config_path])
        
        # 使用 stdout 模式
        cmd.extend(["--mode", "stdout"])
        
        # 添加输入文件
        cmd.append(temp_input)
        
        # 执行 pasfmt
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=TIMEOUT_PASFMT,  # 30秒超时
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        # 清理输入临时文件
        os.unlink(temp_input)
        
        stdout = result.stdout.strip()
        
        if result.returncode == 0:
            # 去掉文件名前缀 (pasfmt stdout 模式会输出 "filepath:\nformatted_code")
            lines = stdout.split('\n', 1)
            if len(lines) > 1 and ':' in lines[0]:
                formatted_content = lines[1]
            else:
                formatted_content = stdout

            # 应用 uses 压缩后处理
            effective_uses_style = uses_style if uses_style is not None else _USES_STYLE
            if effective_uses_style == "compact":
                formatted_content = _compact_uses_clause(formatted_content)

            return CallToolResult(
                content=[{"type": "text", "text": formatted_content}],
                isError=False
            )
        else:
            # 失败
            error_msg = f"pasfmt 执行失败 (退出码: {result.returncode})"
            stderr = result.stderr.strip()
            if stderr:
                error_msg += f": {stderr}"
            
            logger.error(error_msg)
            return CallToolResult(
                content=[{"type": "text", "text": error_msg}],
                isError=True
            )
            
    except subprocess.TimeoutExpired:
        # 清理临时文件
        if os.path.exists(temp_input):
            os.unlink(temp_input)
        
        error_msg = "pasfmt 执行超时"
        logger.error(error_msg)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
    except Exception as e:
        # 清理临时文件
        if os.path.exists(temp_input):
            os.unlink(temp_input)
        
        error_msg = f"执行 pasfmt 时发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


def _download_file(url: str, destination: str, source_name: str = "源") -> Tuple[bool, str]:
    """
    下载文件，支持重试和镜像
    
    Args:
        url: 下载URL
        destination: 目标文件路径
        source_name: 源名称（用于日志）
    
    Returns:
        (成功标志, 错误信息)
    """
    try:
        logger.info(f"从 {source_name} 下载: {url}")
        
        # 设置超时和重试
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=TIMEOUT_NETWORK_REQUEST,
        )
        response.raise_for_status()
        
        # 获取文件大小
        total_size = int(response.headers.get('content-length', 0))
        
        # 下载文件
        with open(destination, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # 可以添加进度显示，但为了简洁这里省略
        
        logger.info(f"下载完成: {destination} ({os.path.getsize(destination)} 字节)")
        return True, ""
        
    except requests.exceptions.Timeout:
        error_msg = f"下载超时: {url}"
        logger.error(error_msg)
        return False, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"下载失败: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"下载过程中发生错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


async def download_and_install_pasfmt(install_dir: str = None) -> Dict[str, Any]:
    """
    下载并安装 pasfmt 工具
    
    Args:
        install_dir: 安装目录，默认为项目根目录下的 tools/pasfmt/cli
    
    Returns:
        安装结果字典
    """
    logger.info("开始下载并安装 pasfmt 工具")
    
    # 确定安装目录
    if not install_dir:
        # 使用项目根目录下的 tools/pasfmt/cli 目录
        project_root = Path(__file__).parent.parent.parent
        install_dir = str(project_root / "tools" / "pasfmt" / "cli")
    
    # 创建安装目录
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"创建安装目录: {install_dir}")
    except Exception as e:
        error_msg = f"创建安装目录失败: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "CREATE_DIR_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    # 临时文件路径
    temp_zip = os.path.join(tempfile.gettempdir(), "pasfmt_%d.zip" % os.getpid())
    
    # 尝试从多个源下载
    download_success = False
    last_error = ""
    
    for source in PASFMT_DOWNLOAD_SOURCES:
        url = source["url"]
        source_name = source["name"]
        
        logger.info(f"尝试从 {source_name} 下载: {url}")
        success, error = _download_file(url, temp_zip, source_name)
        
        if success:
            download_success = True
            break
        else:
            last_error = error
            logger.warning(f"从 {source_name} 下载失败: {error}")
            
            # 尝试镜像
            if "mirror" in source:
                mirror_url = source["mirror"]
                logger.info(f"尝试从 {source_name} 镜像下载: {mirror_url}")
                success, error = _download_file(mirror_url, temp_zip, f"{source_name}镜像")
                if success:
                    download_success = True
                    break
                else:
                    last_error = error
                    logger.warning(f"从 {source_name} 镜像下载失败: {error}")
    
    if not download_success:
        logger.warning(f"所有下载源都失败，尝试从源码编译安装。最后错误: {last_error}")
        
        # 尝试从源码编译
        compile_result = await compile_from_source("pasfmt", install_dir, "release")
        
        if compile_result.get("status") == "success":
            logger.info("从源码编译安装成功")
            return compile_result
        else:
            # 编译也失败，返回错误
            return {
                "status": "failed",
                "error_code": "DOWNLOAD_AND_COMPILE_FAILED",
                "error_message": f"下载和编译都失败。下载错误: {last_error}，编译错误: {compile_result.get('error_message', '未知错误')}",
                "install_dir": install_dir,
                "download_error": last_error,
                "compile_error": compile_result.get("error_message")
            }
    
    # 解压文件
    try:
        logger.info(f"解压文件: {temp_zip}")
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            # 查找 pasfmt.exe
            exe_files = [f for f in zip_ref.namelist() if f.endswith('.exe') and 'pasfmt' in f.lower()]
            
            if not exe_files:
                # 尝试查找任何可执行文件
                exe_files = [f for f in zip_ref.namelist() if f.endswith('.exe')]
            
            if not exe_files:
                error_msg = "ZIP文件中未找到可执行文件"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "error_code": "NO_EXECUTABLE_FOUND",
                    "error_message": error_msg,
                    "install_dir": install_dir
                }
            
            # 解压所有文件
            zip_ref.extractall(install_dir)
            logger.info(f"解压完成到: {install_dir}")
            
            # 查找解压后的 pasfmt.exe
            exe_path = None
            for root, dirs, files in os.walk(install_dir):
                for file in files:
                    if file.lower() == 'pasfmt.exe':
                        exe_path = os.path.join(root, file)
                        break
                if exe_path:
                    break
            
            if not exe_path:
                # 查找任何 exe 文件
                for root, dirs, files in os.walk(install_dir):
                    for file in files:
                        if file.endswith('.exe'):
                            exe_path = os.path.join(root, file)
                            # 重命名为 pasfmt.exe
                            new_path = os.path.join(install_dir, 'pasfmt.exe')
                            os.rename(exe_path, new_path)
                            exe_path = new_path
                            break
                    if exe_path:
                        break
            
            if not exe_path:
                error_msg = "解压后未找到可执行文件"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "error_code": "EXE_NOT_FOUND_AFTER_EXTRACT",
                    "error_message": error_msg,
                    "install_dir": install_dir
                }
            
            # 设置路径
            global _PASFMT_PATH
            _PASFMT_PATH = exe_path
            
            # 清理临时文件
            try:
                os.unlink(temp_zip)
                logger.info(f"清理临时文件: {temp_zip}")
            except OSError:
                pass
            
            return {
                "status": "success",
                "message": f"pasfmt 安装成功到: {install_dir}",
                "install_dir": install_dir,
                "exe_path": exe_path,
                "pasfmt_path": exe_path
            }
            
    except zipfile.BadZipFile:
        error_msg = "下载的文件不是有效的ZIP文件"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "INVALID_ZIP",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    except Exception as e:
        error_msg = f"解压文件失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "EXTRACT_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }


async def download_and_install_pasfmt_rad(
    delphi_version: str = "11",
    install_64bit: bool = False,
    install_dir: str = None
) -> Dict[str, Any]:
    """
    下载并安装 pasfmt-rad IDE 插件
    
    Args:
        delphi_version: Delphi 版本 (11, 12, 13)
        install_64bit: 是否安装64位版本
        install_dir: 安装目录，默认为项目根目录下的 tools/pasfmt/rad
    
    Returns:
        安装结果字典
    """
    logger.info(f"开始下载并安装 pasfmt-rad IDE 插件 (Delphi {delphi_version})")
    
    # 检查 Delphi 版本
    if delphi_version not in DELPHI_VERSIONS:
        error_msg = f"不支持的 Delphi 版本: {delphi_version}。支持: {', '.join(DELPHI_VERSIONS.keys())}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_DELPHI_VERSION",
            "error_message": error_msg
        }
    
    version_info = DELPHI_VERSIONS[delphi_version]
    
    # 确定要下载的文件名
    if install_64bit and version_info["bpl_64"]:
        bpl_filename = version_info["bpl_64"]
    else:
        bpl_filename = version_info["bpl_32"]
    
    if not bpl_filename:
        error_msg = f"Delphi {delphi_version} 不支持 {'64位' if install_64bit else '32位'}版本"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_ARCHITECTURE",
            "error_message": error_msg
        }
    
    # 确定安装目录
    if not install_dir:
        # 使用项目根目录下的 tools/pasfmt/rad 目录
        project_root = Path(__file__).parent.parent.parent
        install_dir = str(project_root / "tools" / "pasfmt" / "rad")
    
    # 创建目录（如果不存在）
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"安装目录: {install_dir}")
    except Exception as e:
        error_msg = f"创建安装目录失败: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "CREATE_INSTALL_DIR_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    # 目标文件路径
    target_path = os.path.join(install_dir, bpl_filename)
    
    # 临时文件路径
    temp_bpl = os.path.join(tempfile.gettempdir(), bpl_filename)
    
    # 尝试从多个源下载
    download_success = False
    last_error = ""
    
    for source in PASFMT_RAD_DOWNLOAD_SOURCES:
        url = source["base_url"] + bpl_filename
        source_name = source["name"]
        
        logger.info(f"尝试从 {source_name} 下载: {url}")
        success, error = _download_file(url, temp_bpl, source_name)
        
        if success:
            download_success = True
            break
        else:
            last_error = error
            logger.warning(f"从 {source_name} 下载失败: {error}")
            
            # 尝试镜像
            if "mirror" in source:
                mirror_url = source["mirror"] + bpl_filename
                logger.info(f"尝试从 {source_name} 镜像下载: {mirror_url}")
                success, error = _download_file(mirror_url, temp_bpl, f"{source_name}镜像")
                if success:
                    download_success = True
                    break
                else:
                    last_error = error
                    logger.warning(f"从 {source_name} 镜像下载失败: {error}")
    
    if not download_success:
        logger.warning(f"所有下载源都失败，尝试从源码编译安装。最后错误: {last_error}")
        
        # 尝试从源码编译
        compile_result = await compile_from_source("pasfmt-rad", install_dir, "release")
        
        if compile_result.get("status") == "success":
            logger.info("从源码编译安装成功")
            # 更新目标路径为编译结果中的可执行文件路径
            if "executable" in compile_result:
                target_path = compile_result["executable"]
                bpl_filename = os.path.basename(target_path)
            
            return {
                "status": "success",
                "message": f"pasfmt-rad IDE 插件从源码编译安装成功",
                "delphi_version": delphi_version,
                "delphi_name": version_info["name"],
                "bpl_filename": bpl_filename,
                "install_path": target_path,
                "registry_success": False,  # 编译安装不自动注册
                "source": "compiled"
            }
        else:
            # 编译也失败，返回错误
            return {
                "status": "failed",
                "error_code": "DOWNLOAD_AND_COMPILE_FAILED",
                "error_message": f"下载和编译都失败。下载错误: {last_error}，编译错误: {compile_result.get('error_message', '未知错误')}",
                "install_dir": install_dir,
                "bpl_filename": bpl_filename,
                "download_error": last_error,
                "compile_error": compile_result.get("error_message")
            }
    
    # 复制文件到目标位置
    try:
        shutil.copy2(temp_bpl, target_path)
        logger.info(f"复制文件到: {target_path}")
        
        # 清理临时文件
        try:
            os.unlink(temp_bpl)
            logger.info(f"清理临时文件: {temp_bpl}")
        except OSError:
            pass
        
        # 注册到 IDE（Windows 注册表）
        if sys.platform == "win32":
            try:
                import winreg
                
                # Delphi 注册表路径
                registry_version = _bds_registry_version(delphi_version)
                reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{registry_version}\\Known Packages"
                
                # 打开或创建注册表项
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)
                except FileNotFoundError:
                    # 创建键
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
                
                # 设置值
                package_name = bpl_filename.replace('.bpl', '')
                winreg.SetValueEx(key, target_path, 0, winreg.REG_SZ, package_name)
                winreg.CloseKey(key)
                
                logger.info(f"已注册到注册表: {reg_path}")
                registry_success = True
                
            except Exception as e:
                logger.warning(f"注册表操作失败: {str(e)}，需要手动注册")
                registry_success = False
        else:
            registry_success = True  # 非Windows平台不需要注册表
        
        return {
            "status": "success",
            "message": f"pasfmt-rad IDE 插件安装成功",
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "bpl_filename": bpl_filename,
            "install_path": target_path,
            "registry_success": registry_success if sys.platform == "win32" else None,
            "registry_path": (
                f"HKEY_CURRENT_USER\\{REG_KEY_EMBARCADERO_BDS}\\"
                f"{_bds_registry_version(delphi_version)}\\Known Packages"
                if sys.platform == "win32"
                else None
            ),
            "registry_value": target_path if sys.platform == "win32" else None
        }
        
    except Exception as e:
        error_msg = f"复制文件失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "COPY_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir,
            "bpl_filename": bpl_filename
        }


async def check_pasfmt_installation() -> CallToolResult:
    """
    检查 pasfmt 安装状态
    
    Returns:
        检查结果字典
    """
    logger.info("检查 pasfmt 安装状态")
    
    # 检查 pasfmt 是否已安装
    pasfmt_path = get_pasfmt_path()
    
    if pasfmt_path and os.path.exists(pasfmt_path):
        return CallToolResult(
            content=[{"type": "text", "text": f"pasfmt 已安装: {pasfmt_path}"}]
        )
    else:
        # 检查可能的安装位置
        default_paths = _pasfmt_default_paths()
        
        found_paths = []
        for path in default_paths:
            if os.path.exists(path):
                found_paths.append(path)
        
        if found_paths:
            # 设置找到的路径
            set_pasfmt_path(found_paths[0])
            return CallToolResult(
                content=[{"type": "text", "text": f"找到 pasfmt: {found_paths[0]}"}]
            )
        else:
            # 建议安装到项目目录下的 tools/pasfmt/cli
            suggested_dir = str(_project_root() / "tools" / "pasfmt" / "cli")
            
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到 pasfmt，建议安装到: {suggested_dir}"}],
                isError=True
            )


async def check_pasfmt_rad_installation(delphi_version: str = "11") -> Dict[str, Any]:
    """
    检查 pasfmt-rad IDE 插件安装状态
    
    Args:
        delphi_version: Delphi 版本 (11, 12, 13)
    
    Returns:
        检查结果字典
    """
    logger.info(f"检查 pasfmt-rad IDE 插件安装状态 (Delphi {delphi_version})")
    
    if delphi_version not in DELPHI_VERSIONS:
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_DELPHI_VERSION",
            "error_message": f"不支持的 Delphi 版本: {delphi_version}"
        }
    
    version_info = DELPHI_VERSIONS[delphi_version]
    
    # 检查 32位和64位版本
    bpl_files = []
    if version_info["bpl_32"]:
        bpl_files.append(version_info["bpl_32"])
    if version_info["bpl_64"]:
        bpl_files.append(version_info["bpl_64"])
    
    # 检查常见安装位置
    possible_dirs = _pasfmt_rad_candidate_dirs(delphi_version)
    
    installed_files = []
    for bpl_file in bpl_files:
        for dir_path in possible_dirs:
            file_path = os.path.join(dir_path, bpl_file)
            if os.path.exists(file_path):
                installed_files.append({
                    "filename": bpl_file,
                    "path": file_path,
                    "directory": dir_path
                })
    
    # 检查注册表（仅Windows）
    registry_installed = False
    registry_path = None
    if sys.platform == "win32" and installed_files:
        try:
            import winreg
            registry_version = _bds_registry_version(delphi_version)
            reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{registry_version}\\Known Packages"
            
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
                
                # 检查是否已注册
                for bpl_file in bpl_files:
                    for dir_path in possible_dirs:
                        file_path = os.path.join(dir_path, bpl_file)
                        try:
                            value, reg_type = winreg.QueryValueEx(key, file_path)
                            if value:
                                registry_installed = True
                                registry_path = reg_path
                                break
                        except FileNotFoundError:
                            continue
                
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass  # 注册表项不存在
                
        except ImportError:
            pass  # 非Windows平台或没有winreg模块
    
    if installed_files:
        return {
            "status": "success",
            "installed": True,
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "installed_files": installed_files,
            "registry_installed": registry_installed,
            "registry_path": registry_path,
            "message": f"找到 {len(installed_files)} 个已安装的插件文件"
        }
    else:
        return {
            "status": "success",
            "installed": False,
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "message": f"未找到 pasfmt-rad IDE 插件 (Delphi {delphi_version})",
            "suggested_paths": possible_dirs
        }


async def compile_from_source(
    source_type: str = "pasfmt",
    install_dir: str = None,
    build_type: str = "release"
) -> Dict[str, Any]:
    """
    从源码编译安装 pasfmt 或 pasfmt-rad
    
    Args:
        source_type: 源码类型，'pasfmt' 或 'pasfmt-rad'
        install_dir: 安装目录
        build_type: 构建类型，'release' 或 'debug'
    
    Returns:
        编译结果字典
    """
    logger.info(f"开始从源码编译 {source_type} (构建类型: {build_type})")
    
    # 确定安装目录
    if not install_dir:
        project_root = Path(__file__).parent.parent.parent
        if source_type == "pasfmt":
            install_dir = str(project_root / "tools" / "pasfmt" / "cli")
        else:  # pasfmt-rad
            install_dir = str(project_root / "tools" / "pasfmt" / "rad")
    
    # 创建安装目录
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"安装目录: {install_dir}")
    except Exception as e:
        error_msg = f"创建安装目录失败: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "DIRECTORY_CREATION_FAILED",
            "error_message": error_msg
        }
    
    # 选择源码仓库
    if source_type == "pasfmt":
        repositories = PASFMT_SOURCE_REPOSITORIES
        repo_name = "pasfmt"
    else:  # pasfmt-rad
        repositories = PASFMT_RAD_SOURCE_REPOSITORIES
        repo_name = "pasfmt-rad"
    
    # 创建临时目录用于克隆源码
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"{repo_name}_build_")
        logger.info(f"临时构建目录: {temp_dir}")
        
        # 尝试从不同源克隆代码
        clone_success = False
        last_error = None
        
        for repo in repositories:
            repo_url = repo.get("url")
            repo_mirror = repo.get("mirror", repo_url)
            repo_name_display = repo["name"]
            
            logger.info(f"尝试从 {repo_name_display} 克隆: {repo_url}")
            
            try:
                # 首先尝试主源
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, temp_dir],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_PASFMT_GIT_CLONE,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                
                if result.returncode == 0:
                    clone_success = True
                    logger.info(f"从 {repo_name_display} 克隆成功")
                    break
                else:
                    logger.warning(f"从 {repo_name_display} 克隆失败: {result.stderr}")
                    
                    # 尝试镜像
                    logger.info(f"尝试从镜像克隆: {repo_mirror}")
                    result = subprocess.run(
                        ["git", "clone", "--depth", "1", repo_mirror, temp_dir],
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_PASFMT_GIT_CLONE,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                    
                    if result.returncode == 0:
                        clone_success = True
                        logger.info(f"从镜像克隆成功")
                        break
                    else:
                        last_error = result.stderr
                        logger.warning(f"从镜像克隆失败: {result.stderr}")
                        
            except Exception as e:
                last_error = str(e)
                logger.warning(f"克隆失败: {last_error}")
        
        if not clone_success:
            return {
                "status": "failed",
                "error_code": "GIT_CLONE_FAILED",
                "error_message": f"所有源码仓库都克隆失败。最后错误: {last_error}",
                "install_dir": install_dir
            }
        
        # 构建项目
        logger.info(f"开始构建 {source_type}...")
        
        # 检查构建脚本
        build_script = None
        if source_type == "pasfmt":
            # pasfmt 使用 cargo 构建 (Rust 项目)
            build_script = os.path.join(temp_dir, "Cargo.toml")
            if os.path.exists(build_script):
                logger.info("检测到 Rust 项目，使用 cargo 构建")
                
                # 安装 Rust 工具链（如果未安装）
                try:
                    rustc_check = subprocess.run(["rustc", "--version"], capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if rustc_check.returncode != 0:
                        logger.warning("Rust 工具链未安装，尝试安装...")
                        # 这里可以添加 Rust 安装逻辑
                        return {
                            "status": "failed",
                            "error_code": "RUST_NOT_INSTALLED",
                            "error_message": "Rust 工具链未安装，请先安装 Rust",
                            "install_dir": install_dir
                        }
                    
                    # 使用 cargo 构建
                    build_cmd = ["cargo", "build", "--release"] if build_type == "release" else ["cargo", "build"]
                    result = subprocess.run(
                        build_cmd,
                        cwd=temp_dir,
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_PASFMT_BUILD,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                    
                    if result.returncode != 0:
                        return {
                            "status": "failed",
                            "error_code": "CARGO_BUILD_FAILED",
                            "error_message": f"cargo 构建失败: {result.stderr}",
                            "install_dir": install_dir
                        }
                    
                    # 查找构建产物
                    target_dir = os.path.join(temp_dir, "target", "release" if build_type == "release" else "debug")
                    if not os.path.exists(target_dir):
                        return {
                            "status": "failed",
                            "error_code": "BUILD_OUTPUT_NOT_FOUND",
                            "error_message": f"构建输出目录不存在: {target_dir}",
                            "install_dir": install_dir
                        }
                    
                    # 复制可执行文件
                    if source_type == "pasfmt":
                        exe_name = "pasfmt.exe" if sys.platform == "win32" else "pasfmt"
                        source_exe = os.path.join(target_dir, exe_name)
                        
                        if not os.path.exists(source_exe):
                            # 尝试在子目录中查找
                            for root, dirs, files in os.walk(target_dir):
                                if exe_name in files:
                                    source_exe = os.path.join(root, exe_name)
                                    break
                        
                        if os.path.exists(source_exe):
                            dest_exe = os.path.join(install_dir, exe_name)
                            shutil.copy2(source_exe, dest_exe)
                            logger.info(f"复制可执行文件到: {dest_exe}")
                            
                            # 设置可执行权限（非Windows）
                            if sys.platform != "win32":
                                os.chmod(dest_exe, 0o755)
                            
                            return {
                                "status": "success",
                                "message": f"{source_type} 编译安装成功",
                                "install_dir": install_dir,
                                "executable": dest_exe,
                                "build_type": build_type,
                                "source": "git"
                            }
                        else:
                            return {
                                "status": "failed",
                                "error_code": "EXECUTABLE_NOT_FOUND",
                                "error_message": f"未找到可执行文件: {exe_name}",
                                "install_dir": install_dir
                            }
                except Exception as e:
                    return {
                        "status": "failed",
                        "error_code": "BUILD_PROCESS_FAILED",
                        "error_message": f"构建过程失败: {str(e)}",
                        "install_dir": install_dir
                    }
            else:
                return {
                    "status": "failed",
                    "error_code": "NO_BUILD_SYSTEM",
                    "error_message": "未找到构建系统 (Cargo.toml)",
                    "install_dir": install_dir
                }
        else:  # pasfmt-rad
            # pasfmt-rad 是 Delphi 项目，需要 Delphi 编译器
            logger.warning("pasfmt-rad 是 Delphi 项目，需要 Delphi 编译器进行构建")
            logger.info("建议从预编译的二进制文件安装，或手动使用 Delphi IDE 编译")
            
            return {
                "status": "failed",
                "error_code": "DELPHI_COMPILER_REQUIRED",
                "error_message": "pasfmt-rad 需要 Delphi 编译器进行构建。请从预编译的二进制文件安装，或手动使用 Delphi IDE 编译。",
                "install_dir": install_dir,
                "source_dir": temp_dir
            }
    
    except Exception as e:
        error_msg = f"编译过程失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "COMPILATION_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    finally:
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"清理临时目录: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时目录失败: {str(e)}")
