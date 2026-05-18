"""
file_tool — 统一 Delphi 文件操作工具

整合读取/写入/格式化/备份管理，覆盖文件操作完整生命周期。

Action 模式:
  read    读取文件内容（继承 read_source_file，支持按路径/类名/函数名搜索）
  write   写入文件内容（自动备份到 __history，支持 DFM 透明转换）
  format  格式化 Delphi 源码（继承 format_delphi，pasfmt 驱动）
  backup  备份管理（创建/恢复/列表/对比）

返回值统一为 dict，遵循项目规范:
  success: {"status": "success", "message": "...", ...}
  error:   {"status": "failed", "message": "..."}
"""

import os
import locale
import shutil
import tempfile
from typing import Any, Optional, Dict
from mcp.types import CallToolResult
from ..utils.logger import get_logger
from ..utils.file_backup import create_backup, list_backups, restore_backup, detect_encoding
from . import pasfmt
from .read_source_file import read_source_file as _read_file, search_and_read_file as _search_read_file
from . import dfm_utils

logger = get_logger(__name__)

# 支持的文件扩展名
_DELPHI_EXTENSIONS = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc', '.dproj'}


def _is_delphi_file(file_path: str) -> bool:
    """判断是否是 Delphi 源文件"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _DELPHI_EXTENSIONS


def _is_dfm_file(file_path: str) -> bool:
    """判断是否是 DFM 文件"""
    return os.path.splitext(file_path)[1].lower() == '.dfm'


def _wrap_error(msg: str) -> Dict[str, Any]:
    """构造错误 dict"""
    return {"status": "failed", "message": msg}


async def _read_content(
    file_path: str,
    start_line: int = 1,
    max_lines: int = 500,
    search_in: str = "all",
    project_path: Optional[str] = None,
    end_line: Optional[int] = None,
) -> Dict[str, Any]:
    """
    读取文件内容的内部实现。

    如果文件在本地直接存在，检测编码后直接读取（支持 UTF-8/GBK/UTF-16 等）。
    否则委托给 read_source_file 走知识库搜索路径。
    """
    # 直接文件读取（支持编码检测 + 降级链）
    if os.path.isfile(file_path):
        # 构建编码降级链：检测编码 → UTF-8 → CP_ACP（系统 ANSI 代码页）
        detected = detect_encoding(file_path)
        fallback_encodings = [detected]

        # UTF-8 无 BOM（与检测编码不同时补充）
        if detected not in ('utf-8', 'utf-8-sig'):
            fallback_encodings.append('utf-8')

        # CP_ACP — 系统 ANSI 代码页（中文 Windows 通常是 GBK）
        try:
            ansi = locale.getpreferredencoding()
            if ansi.lower() not in (e.lower() for e in fallback_encodings):
                fallback_encodings.append(ansi)
        except Exception:
            pass

        last_error = None
        for enc in fallback_encodings:
            try:
                with open(file_path, 'r', encoding=enc, newline='') as f:
                    all_lines = f.readlines()

                total_lines = len(all_lines)
                if start_line < 1:
                    start_line = 1
                if end_line is not None:
                    # clamp end_line 到文件末尾，不超过实际行数
                    end_line = min(end_line, total_lines)
                    selected = all_lines[start_line - 1:end_line]
                else:
                    selected = all_lines[start_line - 1:start_line - 1 + max_lines]

                text = ''.join(selected)
                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                base_name = os.path.basename(file_path)
                summary = (
                    f"文件: {base_name}\n"
                    f"完整路径: {os.path.abspath(file_path)}\n"
                    f"总行数: {total_lines}\n"
                    f"显示范围: 第 {start_line} 行 到 第 {start_line + lines_shown - 1} 行\n"
                    f"编码: {enc}\n"
                    f"============================================================\n\n"
                )
                return {"status": "success", "message": summary + text}
            except UnicodeDecodeError:
                last_error = f"编码 {enc} 解码失败"
                continue
            except Exception as e:
                last_error = str(e)
                continue

        # 所有编码尝试均失败，返回错误（不降级到 KB — 文件在本地，KB 会读空）
        logger.warning(f"读取文件 {file_path} 失败，尝试编码 {fallback_encodings} 均无效: {last_error}")
        return _wrap_error(f"无法读取文件（编码检测失败）: {last_error}")

    # 文件不在本地（可能是知识库中的路径） — 委托给 read_source_file
    args = {
        "file_path": file_path,
        "start_line": start_line,
        "max_lines": max_lines,
        "search_in": search_in,
        "project_path": project_path,
    }
    if end_line is not None:
        args["end_line"] = end_line
    result = await _read_file(args)
    if result.isError:
        return {"status": "failed", "message": result.content[0].text if result.content else "读取失败"}
    return {"status": "success", "message": result.content[0].text if result.content else ""}


async def _search_and_read(
    search_type: str,
    type_name: Optional[str] = None,
    record_name: Optional[str] = None,
    function_name: Optional[str] = None,
    search_in: str = "all",
    start_line: int = 1,
    max_lines: int = 100,
) -> Dict[str, Any]:
    """按类名/函数名搜索并读取文件"""
    args = {
        "type_name": type_name,
        "record_name": record_name,
        "function_name": function_name,
        "search_in": search_in,
        "start_line": start_line,
        "max_lines": max_lines,
    }
    result = await _search_read_file(args)
    if result.isError:
        return {"status": "failed", "message": result.content[0].text if result.content else "搜索失败"}
    return {"status": "success", "message": result.content[0].text if result.content else ""}


async def handle_read(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 read action。

    支持两种模式:
      1. 按路径读取: file_path 参数
      2. 按搜索读取: search_type + type_name/function_name

    DFM 文件透明处理：二进制 DFM 自动转换为文本再读取。
    """
    file_path = arguments.get("file_path")
    search_type = arguments.get("search_type", "path")
    start_line = arguments.get("start_line", 1)
    end_line = arguments.get("end_line")
    if end_line is not None:
        max_lines = min(end_line - start_line + 1, 1000)
    else:
        max_lines = min(arguments.get("max_lines", 500), 1000)
    search_in = arguments.get("search_in", "all")
    project_path = arguments.get("project_path")

    # --- 搜索模式 ---
    if search_type != "path":
        return await _search_and_read(
            search_type=search_type,
            type_name=arguments.get("type_name") or arguments.get("class_name"),
            record_name=arguments.get("record_name"),
            function_name=arguments.get("function_name"),
            search_in=search_in,
            start_line=start_line,
            max_lines=max_lines,
        )

    # --- 路径模式 ---
    if not file_path:
        return _wrap_error("请提供 file_path 参数")

    # DFM 二进制→文本透明转换
    tmp_cleanup = None
    if _is_dfm_file(file_path):
        try:
            fmt = dfm_utils._detect_dfm_format(file_path)
        except FileNotFoundError:
            return _wrap_error(f"DFM 文件不存在: {file_path}")
        except PermissionError:
            return _wrap_error(f"无权限读取 DFM 文件: {file_path}")
        if fmt == "binary":
            tmp_dir = tempfile.mkdtemp(prefix="filetool_")
            tmp_text = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
            result = await dfm_utils.convert_dfm(file_path, tmp_text, to_text=True)
            if result.get("success"):
                file_path = tmp_text
                tmp_cleanup = tmp_dir
            else:
                # 转换失败时返回明确错误，不尝试读二进制文件
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return _wrap_error(
                    f"二进制 DFM 转换失败: {result.get('message', '未知错误')}。"
                    "请检查 Delphi 编译器(dcc32)是否可用"
                )

    try:
        return await _read_content(
            file_path=file_path,
            start_line=start_line,
            max_lines=max_lines,
            search_in=search_in,
            project_path=project_path,
            end_line=end_line,
        )
    finally:
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)


async def handle_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 write action。

    核心特性:
      - 自动备份原文件到 __history（backup=True 默认）
      - 自动检测并保持原始编码
      - DFM 文件自动处理：如果原文件是二进制，写出后自动转回二进制
    """
    file_path = arguments.get("file_path")
    content = arguments.get("content")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    format_after = arguments.get("format_after_write", False)

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if content is None:
        return _wrap_error("请提供 content 参数")

    # 检测原始文件状态
    backup_path = None
    file_exists = os.path.isfile(file_path)
    original_encoding = None
    is_dfm_binary = False

    if file_exists:
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
                is_dfm_binary = (fmt == "binary")
            except (FileNotFoundError, PermissionError) as e:
                return _wrap_error(str(e))

        if encoding == "auto":
            original_encoding = detect_encoding(file_path)
        else:
            original_encoding = encoding

        if backup:
            backup_path = create_backup(file_path)
    else:
        # 新文件默认 UTF-8 BOM（避免中文 Windows 下 Delphi/pasfmt 误判为 GBK）
        original_encoding = encoding if encoding != "auto" else "utf-8-sig"

    # 写入文件
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=os.path.splitext(file_path)[1],
            dir=os.path.dirname(os.path.abspath(file_path)),
        )
        os.close(tmp_fd)

        write_encoding = original_encoding or "utf-8"
        encoding_fallback = False
        try:
            with open(tmp_path, "w", encoding=write_encoding, newline='') as f:
                f.write(content)
        except UnicodeEncodeError:
            logger.warning(f"编码 {write_encoding} 写出失败，回退到 utf-8")
            with open(tmp_path, "w", encoding="utf-8", newline='') as f:
                f.write(content)
            write_encoding = "utf-8"
            encoding_fallback = True

        # DFM 二进制格式处理
        if is_dfm_binary:
            text_tmp = tmp_path + ".txt"
            os.rename(tmp_path, text_tmp)
            try:
                conv_result = await dfm_utils.convert_dfm(text_tmp, tmp_path, to_text=False)
                if not conv_result.get("success"):
                    os.rename(text_tmp, tmp_path)
                    logger.warning(f"DFM 二进制转换失败，已保留文本格式: {conv_result.get('message')}")
                else:
                    os.remove(text_tmp)
            except Exception as e:
                if os.path.exists(text_tmp):
                    os.rename(text_tmp, tmp_path)
                logger.warning(f"DFM 转换异常，已保留文本格式: {e}")

        shutil.move(tmp_path, file_path)
        tmp_path = None  # 成功写入，标记无需清理

        # 写入后自动格式化
        fmt_msg = ""
        if format_after and _is_delphi_file(file_path):
            try:
                fmt_result = await pasfmt.format_file(file_path=file_path, backup=False)
                if fmt_result.get("formatted"):
                    fmt_msg = "，写入后已格式化"
            except Exception as e:
                logger.warning(f"写入后自动格式化失败: {e}")

        result_lines = [
            f"文件已写入: {file_path}",
            f"编码: {write_encoding}",
        ]
        if encoding_fallback:
            result_lines.append(f"⚠ 原始编码 {original_encoding or 'utf-8'} 无法编码写入内容，已回退到 UTF-8")
        if backup and file_exists:
            result_lines.append(f"备份已创建: {backup_path}")
        if is_dfm_binary:
            result_lines.append("格式: 已转换为二进制 DFM")
        if fmt_msg:
            result_lines.append(fmt_msg)

        return {"status": "success", "message": "\n".join(result_lines)}

    except Exception as e:
        logger.error(f"写入文件失败: {e}", exc_info=True)
        return _wrap_error(f"写入文件失败: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


async def handle_format(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 format action — 委托给 pasfmt.format_file / format_code。
    """
    file_path = arguments.get("file_path")
    action = arguments.get("format_action", "file")
    uses_style = arguments.get("uses_style")
    check_only = arguments.get("check_only", False)
    backup_flag = arguments.get("backup", True)

    if action == "code":
        code = arguments.get("code", "")
        if not code:
            return _wrap_error("请提供 code 参数")
        raw_result = await pasfmt.format_code(
            code=code,
            config_path=arguments.get("config_path"),
            uses_style=uses_style,
        )
        # format_code 返回 CallToolResult，统一转为 dict
        if isinstance(raw_result, CallToolResult):
            text = raw_result.content[0].text if raw_result.content else ""
            if raw_result.isError:
                result = _wrap_error(text)
            else:
                result = {"status": "success", "message": text, "formatted": True}
        else:
            result = raw_result
    else:
        if not file_path:
            return _wrap_error("请提供 file_path 参数")
        if action == "check":
            result = await pasfmt.format_file(
                file_path=file_path,
                check_only=True,
            )
        else:
            result = await pasfmt.format_file(
                file_path=file_path,
                config_path=arguments.get("config_path"),
                backup=backup_flag,
                in_place=True,
                uses_style=uses_style,
            )

    # pasfmt.format_file / format_code 结果已统一为 dict
    return result


async def handle_backup(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 backup action — 备份管理。

    子 action:
      create  创建备份（默认）
      list    列出所有备份版本
      restore 恢复指定版本
    """
    file_path = arguments.get("file_path")
    backup_action = arguments.get("backup_action", "create")
    version = arguments.get("version")

    if not file_path:
        return _wrap_error("请提供 file_path 参数")

    if backup_action == "create":
        bp = create_backup(file_path)
        if bp:
            return {"status": "success", "message": f"备份已创建: {bp}"}
        return _wrap_error(f"备份失败: {file_path}")

    elif backup_action == "list":
        backups = list_backups(file_path)
        if not backups:
            return {"status": "success", "message": f"没有找到 {file_path} 的备份文件"}
        lines = [f"文件: {file_path}", f"备份数: {len(backups)}", ""]
        for b in backups:
            from datetime import datetime
            ts = datetime.fromtimestamp(b["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = b["size"] / 1024
            lines.append(f"  v{b['version']}: {ts}  ({size_kb:.1f} KB)  {b['path']}")
        return {"status": "success", "message": "\n".join(lines)}

    elif backup_action == "restore":
        bp = restore_backup(file_path, version=version)
        if bp:
            ver_str = f"v{version}" if version else "最新版本"
            return {"status": "success", "message": f"已从 {ver_str} 恢复: {bp}"}
        return _wrap_error(f"恢复失败: {file_path}")

    else:
        return _wrap_error(f"未知 backup_action: {backup_action}")


# ============================================================
# 主入口
# ============================================================

async def handle_file_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    file_tool 主入口。

    根据 action 参数路由到对应的处理函数:
      read    → handle_read
      write   → handle_write
      format  → handle_format
      backup  → handle_backup
    """
    action = arguments.get("action", "read")

    if action == "read":
        return await handle_read(arguments)
    elif action == "write":
        return await handle_write(arguments)
    elif action == "format":
        return await handle_format(arguments)
    elif action == "backup":
        return await handle_backup(arguments)
    else:
        return _wrap_error(f"未知 action: {action}。支持的 action: read, write, format, backup")
