"""
delphi_file — Delphi 文件专用操作工具（MCP 注册名 delphi_file，原 file_tool）

整合读取/写入/格式化/备份管理，覆盖 Delphi 文件操作完整生命周期。
MCP 客户端以 delphi_file 名注册，旧名 file_tool 仍作为别名兼容。

Action 模式:
  read        读取文件内容（继承 read_source_file，支持按路径/类名/函数名搜索）
  write       兼容写入入口（自动备份到 __history，支持 DFM 透明转换）
  replace     按行范围替换（现有文件要求 old_content 校验）
  insert      按锚点插入（现有文件要求 old_content 校验，支持 before/after）
  delete      按行范围删除（现有文件要求 old_content 校验）
  format      格式化 Delphi 源码（继承 format_delphi，pasfmt 驱动）
  backup      备份管理（创建/恢复/列表/对比）
  encode      文件编码转换（自动检测源编码，支持 BOM 处理，自动备份）
  uses        增删 uses 子句中的单元（命名空间冲突检测 + 自动排序）
  fix_garbled 修复中文乱码（自动检测 U+FFFD、缺失 BOM、编码误检测等模式并修复）

返回值统一为 dict，遵循项目规范:
  success: {"status": "success", "message": "...", ...}
  error:   {"status": "failed", "message": "..."}
"""

import codecs
import locale
import os
import re
import shutil
import tempfile
import threading
import uuid
from typing import Any, Optional, Dict, List, Set
from mcp.types import CallToolResult
from ..constants import BUFFER_SIZE_1MB
from ..utils.logger import get_logger
from ..utils.file_backup import create_backup, list_backups, restore_backup, detect_encoding
from ..services.delphi_edit_guard import record_authorized_write
from . import pasfmt
from .read_source_file import read_source_file as _read_file, search_and_read_file as _search_read_file
from . import dfm_utils

logger = get_logger(__name__)

_DELPHI_EXTENSIONS = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc', '.dproj'}

_SYSTEM_SENSITIVE_DIRS: List[str] = []
if os.name == 'nt':
    _windir = os.environ.get('WINDIR', r'C:\Windows')
    _SYSTEM_SENSITIVE_DIRS = [
        os.path.join(_windir, 'System32', 'config'),
        os.path.join(_windir, 'System32', 'drivers', 'etc'),
    ]
else:
    _SYSTEM_SENSITIVE_DIRS = ['/etc/shadow', '/etc/ssh']


def _coerce_positive_int(value: Any, default: int, name: str) -> tuple[Optional[int], Optional[str]]:
    """Return a 1-indexed positive integer value, or an error message."""
    if value is None:
        value = default
    if not isinstance(value, int):
        return None, f"{name} 必须是整数"
    if value < 1:
        return None, f"{name} 不能小于 1（实际值: {value}）"
    return value, None


def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
    """校验文件路径安全性，返回 None 表示安全，否则返回错误信息

    Args:
        file_path: 待校验的文件路径
        project_path: 项目路径（可选，提供时限制 file_path 必须在项目目录内）
    """
    # Null 字节注入检查
    if '\0' in file_path:
        return "路径包含 null 字节"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "路径解析失败: %s" % str(e)

    # 系统敏感目录保护
    for sensitive_dir in _SYSTEM_SENSITIVE_DIRS:
        try:
            resolved_relative = os.path.relpath(resolved, sensitive_dir)
            if not resolved_relative.startswith('..'):
                return "路径位于系统敏感目录中: %s" % sensitive_dir
        except ValueError:
            pass

    # 项目目录限制：当传入了 project_path 时，确保文件在项目目录内
    if project_path:
        try:
            proj_resolved = os.path.abspath(os.path.realpath(project_path))
            # project_path 可能是 .dproj 文件，取其目录作为项目根
            proj_dir = proj_resolved if os.path.isdir(proj_resolved) else os.path.dirname(proj_resolved)
            rel = os.path.relpath(resolved, proj_dir)
            if rel.startswith('..'):
                return "路径不在项目目录内: %s (项目: %s)" % (file_path, project_path)
        except (OSError, ValueError):
            # project_path 解析失败时不阻断，由调用方处理
            pass

    return None


def _is_delphi_file(file_path: str) -> bool:
    """判断是否是 Delphi 源文件"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _DELPHI_EXTENSIONS


def _is_dfm_file(file_path: str) -> bool:
    """判断是否是 DFM/FMX 表单文件（Delphi VCL/FireMonkey 表单，可能为二进制或文本格式）"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.dfm', '.fmx'}


def _wrap_error(msg: str) -> Dict[str, Any]:
    """构造错误 dict"""
    return {"status": "failed", "message": msg}


def _is_pascal_word_char(ch: str) -> bool:
    """Return True for identifier/number token characters."""
    return ch == "_" or ch.isalnum()


def _next_non_space(text: str, start: int) -> str:
    """Return the next non-whitespace character after start, or empty string."""
    for idx in range(start, len(text)):
        if not text[idx].isspace():
            return text[idx]
    return ""


def _append_word_boundary_if_needed(result: List[str], next_ch: str) -> None:
    """Preserve token boundaries while ignoring formatting whitespace."""
    if result and next_ch and _is_pascal_word_char(result[-1]) and _is_pascal_word_char(next_ch):
        result.append(" ")


def _normalize_code_for_compare(text: str) -> str:
    """Ignore whitespace outside Pascal string literals for old_content checks.

    规则:
      - 代码区: 删除空白词，只在需要防止 token 粘连时加单空格
      - 注释区: 连续空白折叠为单空格，不全部删除
      - 字符串区: 原样保留
    """
    result: List[str] = []
    i = 0
    state = "code"
    # 注释区内跟踪上个字符是否为空白（用于折叠）
    prev_was_space = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "string":
            result.append(ch)
            if ch == "'":
                if nxt == "'":
                    result.append(nxt)
                    i += 1
                else:
                    state = "code"
        elif state in ("line_comment", "brace_comment", "paren_comment"):
            # ── 注释内: 空白折叠为单空格 ──
            if state == "line_comment" and ch in "\r\n":
                state = "code"
                prev_was_space = False
            elif state == "brace_comment" and ch == "}":
                result.append(ch)
                state = "code"
                prev_was_space = False
            elif state == "paren_comment" and ch == "*" and nxt == ")":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "code"
                prev_was_space = False
            elif ch.isspace():
                if not prev_was_space:
                    result.append(" ")
                    prev_was_space = True
            else:
                result.append(ch)
                prev_was_space = False
        else:
            # ── 代码区: 原逻辑不变 ──
            if ch == "'":
                state = "string"
                result.append(ch)
            elif ch == "/" and nxt == "/":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "line_comment"
                prev_was_space = False
            elif ch == "{":
                result.append(ch)
                state = "brace_comment"
                prev_was_space = False
            elif ch == "(" and nxt == "*":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "paren_comment"
                prev_was_space = False
            elif not ch.isspace():
                result.append(ch)
            else:
                _append_word_boundary_if_needed(result, _next_non_space(text, i + 1))
        i += 1
    return ''.join(result)


def _get_old_content(edit: Dict[str, Any]) -> Optional[str]:
    """Read the old_content guard from an edit.

    自动 strip 尾部 \\r\\n，避免 AI 从 read 输出复制时带入行尾换行符导致校验失败。
    """
    value = edit.get("old_content")
    if isinstance(value, str):
        value = value.rstrip('\r\n')
    return value


def _all_edits_have_old_content(edits: Any) -> bool:
    """Return True when every edit can be guarded by old_content."""
    if not isinstance(edits, (list, tuple)) or not edits:
        return False
    return all(
        isinstance(edit, dict) and _edit_has_non_empty_old_content(edit)
        for edit in edits
    )


def _edit_has_non_empty_old_content(edit: Dict[str, Any]) -> bool:
    """Return True when an edit contains a usable old_content guard."""
    old_content = _get_old_content(edit)
    return old_content is not None and bool(_normalize_code_for_compare(old_content))


def _prepare_insert_content(content: str, has_crlf: bool) -> str:
    """Normalize inserted text and make it occupy complete lines."""
    if has_crlf:
        content = content.replace('\r\n', '\n').replace('\n', '\r\n')
        newline = '\r\n'
    else:
        content = content.replace('\r\n', '\n')
        newline = '\n'
    if content and not content.endswith(('\n', '\r\n')):
        content += newline
    return content


async def _read_structured_anchor_lines(file_path: str) -> tuple[List[str], Optional[str]]:
    """Read text lines for insert anchors, converting binary DFM/FMX first."""
    read_path = file_path
    tmp_cleanup = None
    try:
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
            except (FileNotFoundError, PermissionError) as e:
                raise RuntimeError(str(e)) from e
            if fmt == "binary":
                tmp_cleanup = tempfile.mkdtemp(prefix="filetool_anchor_")
                read_path = os.path.join(tmp_cleanup, os.path.basename(file_path) + ".txt")
                conv_result = await dfm_utils.convert_dfm(file_path, read_path, to_text=True)
                if not conv_result.get("success"):
                    raise RuntimeError(
                        f"二进制 DFM 转换失败: {conv_result.get('message', '未知错误')}"
                    )

        read_enc = detect_encoding(read_path)
        with open(read_path, 'r', encoding=read_enc, newline='',
                  buffering=BUFFER_SIZE_1MB) as f:
            return f.readlines(), tmp_cleanup
    except Exception as exc:
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)
        raise RuntimeError(str(exc)) from exc


def _format_line_snippet(lines: List[str], start_idx: int, end_idx: int, context: int = 2) -> List[str]:
    """Return compact 1-indexed snippet lines around a conflict range."""
    if not lines:
        return ["    <empty file>"]
    lo = max(0, start_idx - context)
    hi = min(len(lines), max(end_idx, start_idx + 1) + context)
    snippet = []
    for idx in range(lo, hi):
        text = lines[idx].rstrip("\r\n")
        if len(text) > 120:
            text = text[:117] + "..."
        snippet.append(f"    L{idx + 1}: {text}")
    return snippet


def _get_history_dir(file_path: str) -> str:
    """Return the __history directory used for backups and temporary writes."""
    return os.path.join(os.path.dirname(os.path.abspath(file_path)), "__history")


def _make_temp_write_path(file_path: str) -> str:
    """Create a unique temporary path on the same volume as the target file."""
    target_dir = os.path.dirname(os.path.abspath(file_path))
    basename = os.path.basename(file_path)
    return os.path.join(target_dir, f".__daofy_tmp_{basename}_{uuid.uuid4().hex}")


def _write_text_temp(temp_path: str, content: str, encoding: str) -> None:
    """Write text to a temp file and flush it before replacement."""
    with open(temp_path, 'w', encoding=encoding, newline='', buffering=BUFFER_SIZE_1MB) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


def _replace_with_temp(temp_path: str, file_path: str) -> None:
    """Atomically replace file_path with temp_path."""
    os.replace(temp_path, file_path)


async def _apply_auto_format_atomically(
    file_path: str,
    encoding: str,
    has_crlf: bool,
    backup: bool = False,
    config_path: Optional[str] = None,
    uses_style: Optional[str] = None,
) -> tuple[bool, str, bool, Optional[str]]:
    """Run pasfmt in stdout mode and atomically replace the formatted file."""
    fmt_result = await pasfmt.format_file(
        file_path=file_path,
        backup=False,
        in_place=False,
        config_path=config_path,
        uses_style=uses_style,
    )
    if fmt_result.get("status") == "failed":
        raise RuntimeError(fmt_result.get("message", "pasfmt 格式化失败"))
    if not fmt_result.get("formatted") or not isinstance(fmt_result.get("content"), str):
        return False, encoding, False, None

    formatted_text = fmt_result["content"]
    if has_crlf:
        formatted_text = formatted_text.replace('\r\n', '\n').replace('\n', '\r\n')
    else:
        formatted_text = formatted_text.replace('\r\n', '\n')
    if formatted_text and not formatted_text.endswith(('\n', '\r\n')):
        formatted_text += '\r\n' if has_crlf else '\n'

    temp_write_path = _make_temp_write_path(file_path)
    encoding_fallback = False
    backup_path = None
    try:
        try:
            _write_text_temp(temp_write_path, formatted_text, encoding)
        except UnicodeEncodeError:
            logger.warning(f"编码 {encoding} 写出格式化结果失败，回退到 utf-8")
            _write_text_temp(temp_write_path, formatted_text, "utf-8")
            encoding = "utf-8"
            encoding_fallback = True
        if backup:
            backup_path = create_backup(file_path)
            if not backup_path:
                raise RuntimeError("创建备份失败，已取消格式化")
        record_authorized_write(
            file_path,
            tool="delphi_file",
            operation="format",
        )
        _replace_with_temp(temp_write_path, file_path)
    finally:
        if os.path.exists(temp_write_path):
            try:
                os.remove(temp_write_path)
            except OSError:
                pass

    return True, encoding, encoding_fallback, backup_path


def _warn_if_old_content_too_short(old_content: str) -> Optional[str]:
    """Return a non-blocking warning for weak old_content guards."""
    normalized = _normalize_code_for_compare(old_content)
    line_count = len([line for line in old_content.splitlines() if line.strip()])
    common_tokens = {
        "begin",
        "end",
        "end;",
        "inherited",
        "inherited;",
        "try",
        "finally",
        "except",
    }
    if len(normalized) < 12 or (line_count <= 1 and normalized.lower() in common_tokens):
        return "old_content 很短，若行号偏移到相同短片段仍可能误命中；建议包含更多上下文行"
    return None


def _normalize_encoding_name(enc: str) -> str:
    """
    归一化编码名：去除 BOM 后缀、-/_ 变体，统一小写。

    utf-8-sig 在归一化层面视为 utf-8（BOM 在打开时自动剥离/添加），
    用于编码兼容性比较。
    """
    if not enc:
        return ""
    e = enc.lower().replace("_", "-")
    if e == "utf-8-sig":
        e = "utf-8"
    return e


def _is_encoding_compatible(user_enc: str, detected_enc: str) -> bool:
    """
    检查用户指定的 encoding 与文件实际编码是否兼容。

    兼容规则:
      - 完全相等（归一化后）
      - utf-8 ↔ utf-8-sig 互相兼容
      - utf-16 系列（utf-16/utf-16-le/utf-16-be）只在同子系列内兼容

    Args:
        user_enc: 用户显式指定的 encoding 参数
        detected_enc: detect_encoding 实际检测结果

    Returns:
        True 表示兼容可继续；False 表示编码不匹配需拒绝
    """
    u = _normalize_encoding_name(user_enc)
    d = _normalize_encoding_name(detected_enc)

    if u == d:
        return True

    # utf-8 家族内部互兼
    utf8_family = {"utf-8"}
    if u in utf8_family and d in utf8_family:
        return True

    # utf-16 家族内部互兼（仅在两边都是 utf-16 系列时）
    utf16_family = {"utf-16", "utf-16-le", "utf-16-be"}
    if u in utf16_family and d in utf16_family:
        return True

    return False


async def _read_content(
    file_path: str,
    start_line: int = 1,
    limit: int = 500,
    search_in: str = "all",
    project_path: Optional[str] = None,
    end_line: Optional[int] = None,
    show_line_numbers: bool = False,
    encoding: str = "auto",
) -> Dict[str, Any]:
    """
    读取文件内容的内部实现。

    如果文件在本地直接存在，检测编码后直接读取（支持 UTF-8/GBK/UTF-16 等）。
    否则委托给 read_source_file 走知识库搜索路径。

    start_line/end_line 为 1-indexed 左闭右闭区间：
      - start_line=1 表示从文件第 1 行开始
      - end_line 不传时等价于「读到 start_line + limit - 1 行为止」

    show_line_numbers: 为 True 时每行前面添加行号前缀（如 "     1: unit Unit1;"），
                       行号为 1-indexed 绝对行号。
    """
    # 直接文件读取（支持编码检测 + 降级链）
    if os.path.isfile(file_path):
        effective_start = max(1, start_line)
        target_end = end_line if end_line is not None else (effective_start + limit - 1)

        # 构建编码降级链
        detected = detect_encoding(file_path)

        if encoding != "auto":
            # 用户显式指定编码 → 作为首选，自动检测结果作为回退
            fallback_encodings = [encoding]
            if encoding.lower() != detected.lower():
                fallback_encodings.append(detected)
        else:
            fallback_encodings = [detected]

        # UTF-8 无 BOM（与检测编码不同时补充）
        if 'utf-8' not in (e.lower() for e in fallback_encodings) and 'utf-8-sig' not in (e.lower() for e in fallback_encodings):
            fallback_encodings.append('utf-8')

        # CP_ACP — 系统 ANSI 代码页
        try:
            ansi = locale.getpreferredencoding()
            if ansi.lower() not in (e.lower() for e in fallback_encodings):
                fallback_encodings.append(ansi)
        except Exception:
            logger.debug("获取系统默认编码失败，跳过ANSI回退")

        # CJK 编码回退（无论系统 locale 如何，都尝试通用 CJK 编码）
        cjk_fallbacks = ['gbk', 'gb18030', 'big5', 'shift_jis', 'euc-kr', 'euc-jp']
        for cjk_enc in cjk_fallbacks:
            if cjk_enc not in (e.lower() for e in fallback_encodings):
                fallback_encodings.append(cjk_enc)

        last_error = None
        for enc in fallback_encodings:
            try:
                if target_end < effective_start:
                    return {
                        "status": "success",
                        "message": (
                            f"# encoding: {enc}, 1-indexed empty, "
                            f"requested [{effective_start}, {target_end}]\n"
                        ),
                        "range": [effective_start, target_end],
                    }

                # 流式读取：只读取需要的行，避免大文件全量读入内存
                # 对于读取开头 N 行或指定行范围的场景，线性扫描比 readlines() 更省内存
                # target_start/target_end 是内部 1-indexed inclusive 表示
                target_start = effective_start
                selected = []
                reached_eof = True  # 跟踪是否读到文件末尾
                line_no = 0  # 空文件时 for 循环体不会执行，需初始化
                with open(file_path, 'r', encoding=enc, newline='',
                          buffering=BUFFER_SIZE_1MB) as f:
                    for line_no, line in enumerate(f, 1):
                        if line_no > target_end:
                            reached_eof = False
                            break
                        if line_no >= target_start:
                            selected.append(line)

                if reached_eof:
                    total_lines = line_no  # 循环正常结束，line_no 即文件实际总行数
                else:
                    total_lines = None  # 被 target_end 截断，未知实际总行数

                raw_selected_text = ''.join(selected)
                text = raw_selected_text

                # show_line_numbers: 为每行添加 1-indexed 绝对行号前缀
                if show_line_numbers and selected:
                    line_offset = target_start  # 1-indexed start
                    numbered_lines = []
                    for i, line in enumerate(selected):
                        lineno = line_offset + i  # 1-indexed 绝对行号
                        numbered_lines.append(f"{lineno:>6}: {line}")
                    text = ''.join(numbered_lines)

                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                actual_end_line = target_start + lines_shown - 1  # 1-indexed inclusive end

                # 单行 meta: 编码 + 1-indexed 行号范围
                # 所有行号都是 1-indexed，可直接用于 write 的 start_line/edits。
                # 截断时仅追加 (truncated) 标记。
                if lines_shown == 0:
                    total_hint = f", total_lines: {total_lines}" if total_lines is not None else ""
                    meta = (
                        f"# encoding: {enc}, 1-indexed empty, "
                        f"requested [{target_start}, {target_end}]{total_hint}"
                    )
                else:
                    meta = f"# encoding: {enc}, 1-indexed [{target_start}, {actual_end_line}]"
                if not reached_eof:
                    meta += " (truncated)"
                meta += "\n"

                return {
                    "status": "success",
                    "message": meta + text,
                    "range": [target_start, actual_end_line] if lines_shown else [target_start, target_end],
                    "encoding": enc,
                }
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
        "max_lines": limit,  # read_source_file 内部仍用 max_lines
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
    limit: int = 100,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """按类名/函数名搜索并读取文件"""
    args = {
        "type_name": type_name,
        "record_name": record_name,
        "function_name": function_name,
        "search_in": search_in,
        "start_line": start_line,
        "max_lines": limit,  # read_source_file 内部仍用 max_lines
        "project_path": project_path,
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
    start_line, start_err = _coerce_positive_int(arguments.get("start_line"), 1, "start_line")
    if start_err:
        return _wrap_error(start_err)
    end_line = arguments.get("end_line")
    if end_line is not None and not isinstance(end_line, int):
        return _wrap_error("end_line 必须是整数")
    if end_line is not None:
        limit = min(end_line - start_line + 1, 1000)
    else:
        limit_value = arguments.get("limit", 500)
        if not isinstance(limit_value, int):
            return _wrap_error("limit 必须是整数")
        limit = min(max(1, limit_value), 1000)
    search_in = arguments.get("search_in", "all")
    project_path = arguments.get("project_path")
    show_line_numbers = arguments.get("show_line_numbers", False)
    encoding = arguments.get("encoding", "auto")

    # --- 搜索模式 ---
    if search_type != "path":
        return await _search_and_read(
            search_type=search_type,
            type_name=arguments.get("type_name") or arguments.get("class_name"),
            record_name=arguments.get("record_name"),
            function_name=arguments.get("function_name"),
            search_in=search_in,
            start_line=start_line,
            limit=limit,
            project_path=project_path,
        )

    # --- 路径模式 ---
    if not file_path:
        return _wrap_error("请提供 file_path 参数")

    path_err = _validate_path(file_path, project_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    # 获取读取许可（多读单写：多个读取可并发，写入时不可读）
    # 必须在 DFM 检测/转换之前获取，防止并发写入干扰
    read_lock_err = _acquire_read_lock(file_path)
    if read_lock_err:
        return _wrap_error(read_lock_err)

    tmp_cleanup = None
    lock_file_path = file_path  # 保存原始路径，用于锁释放（DFM 转换会改写 file_path）
    try:
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

        result = await _read_content(
            file_path=file_path,
            start_line=start_line,
            limit=limit,
            search_in=search_in,
            project_path=project_path,
            end_line=end_line,
            show_line_numbers=show_line_numbers,
            encoding=encoding,
        )
        if result.get("status") == "success":
            _clear_dirty(lock_file_path)
        return result
    finally:
        _release_read_lock(lock_file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)



# ── 文件级写入锁：防止对同一个文件并行写入 ──────────────────────────────
# 同一个文件同时被多个 agent write 会导致内容错乱。
# 用 in-process dict 做简单互斥：第二个并发写直接拒绝，让 agent 合并后重试。
# 多读单写 (RWLock) — 每个文件路径一个锁条目
# 结构: { normalized_path: {"lock": threading.Lock(), "readers": int, "writer": bool} }
_file_rw_locks: Dict[str, Dict] = {}
_file_rw_dict_lock = threading.Lock()  # 保护 _file_rw_locks 字典本身的并发访问


def _get_rw_entry(file_path: str) -> Dict:
    """获取或创建路径对应的 RWLock 条目（线程安全）"""
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            entry = {
                "lock": threading.Lock(),
                "readers": 0,
                "writer": False,
            }
            _file_rw_locks[normalized] = entry
        return entry


def _acquire_read_lock(file_path: str) -> Optional[str]:
    """
    获取文件的读取许可。
    多个读取可并发进行，但写入进行时不允许读取。
    
    Returns:
        None 表示成功，可以读取
        str  表示冲突，返回错误消息
    """
    normalized = os.path.abspath(file_path)
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        if entry["writer"]:
            return (
                f"文件 {os.path.basename(normalized)} 正在被写入操作占用，无法读取。"
                "请等待写入完成后再试。"
            )
        entry["readers"] += 1
    return None


def _release_read_lock(file_path: str) -> None:
    """释放文件的读取许可"""
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        entry["readers"] = max(0, entry["readers"] - 1)


def _acquire_write_lock(file_path: str) -> Optional[str]:
    """
    获取文件的写入许可。
    写入时不允许其他读取或写入同时进行。
    
    Returns:
        None 表示成功，可以写入
        str  表示冲突，返回错误消息
    """
    normalized = os.path.abspath(file_path)
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        if entry["writer"] or entry["readers"] > 0:
            rc = entry["readers"]
            wc = "是" if entry["writer"] else "否"
            return (
                f"文件 {os.path.basename(normalized)} 正在被其他操作占用"
                f"（读取中: {rc}, 写入中: {wc}）。"
                "同一个文件的所有修改必须合并为一次 write(edits=[...]) 完成，"
                "请重新 read 文件后规划全部 edits，再一次性写入。"
            )
        entry["writer"] = True
    return None


def _release_write_lock(file_path: str) -> None:
    """释放文件的写入许可"""
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        entry["writer"] = False


# ── 脏写入标记：防止 AI 未重读/预览就再次写入同一文件 ──────────────────
# 文件修改后（write/format/uses）行号变化，AI 必须 re-read 或用 old_content 校验后才能再次写入。
_dirty_files: Set[str] = set()
_dirty_lock = threading.Lock()


def _mark_dirty(file_path: str) -> None:
    """标记文件已修改，下次写入前需预览或重读。"""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.add(normalized)


def _clear_dirty(file_path: str) -> None:
    """清除脏标记（成功 read 后标记清除）。"""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.discard(normalized)


def _check_dirty(file_path: str, preview: bool = False) -> None:
    """
    检查文件是否脏（上次修改后未重读/预览）。
    如果 dirty 且不是 preview 模式，抛异常阻止写入。
    """
    if preview:
        return
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        if normalized in _dirty_files:
            raise RuntimeError(
                f"文件 {os.path.basename(normalized)} 上次写入后行号可能已变化。"
                "请先调用 read 获取最新行号，或为每个 edit 提供 old_content 原文校验，"
                "或使用 preview=true 预览本次修改。"
                "基于最新行号规划 edits 后重新发起 write。"
            )


async def handle_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 write action。

    统一使用 edits 参数：
      - 全量替换：edits=[{start_line:1, content:"完整文件内容"}]
      - 部分替换：edits=[{start_line:5, end_line:10, content:"替换内容"}]
      - 多段替换：edits=[{start_line:5, end_line:10, content:"..."},
                       {start_line:20, end_line:22, content:"..."}]
      - 删除行：  edits=[{start_line:10, end_line:15, content:""}]

    核心特性:
      - 自动备份原文件到 __history（backup=True 默认）
      - 自动检测并保持原始编码
      - DFM 文件自动处理：二进制 DFM 自动转文本→编辑→转回二进制
      - 支持 auto_format 写入后自动格式化代码
      - 支持 dry_run 预览 diff 不写盘（preview 已废弃，作为别名临时保留）

    行号均为 1-indexed 左闭右闭:
      edits=[{start_line:5, end_line:10}]  → 替换第 5~10 行
      edits=[{start_line:5}]               → 从第 5 行替换到文件末尾
      edits=[{end_line:10}]                → 从第 1 行替换到第 10 行

    ⚠️ 脏标记保护:
       每次写入（含 auto_format）后文件行号会变化。
       在重新 read 文件或 preview 确认前，不允许对同一文件再次写入，
       防止 AI 使用过期行号导致错位改写。
       续重行检测已降级为警告，不再阻断写入。

       old_content + 每个 edit 的原文校验通过时，可安全跳过脏标记。
       allow_dirty=true 可绕过脏标记检查（风险自负）。
    """
    file_path = arguments.get("file_path")
    edits = arguments.get("edits")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    preview = arguments.get("preview", False) or arguments.get("dry_run", False)
    if arguments.get("preview", False):
        logger.warning("delphi_file: preview 参数已废弃，请使用 dry_run 替代")
    force = arguments.get("force", False)
    allow_dirty = arguments.get("allow_dirty", False)
    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not edits:
        return _wrap_error("请提供 edits 参数（全量替换: [{start_line:1, content:'...'}]）")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    # Normalize insert-type edits (those with position="before"/"after") into
    # single-line replacements before passing to _handle_write_edits.
    # Without this, an insert edit without end_line is treated as "to end of file"
    # by the overlap detection, causing false-positive "覆盖到文件末尾" errors
    # when mixed with later range replacements.
    if edits and any(edit.get("position") is not None for edit in edits):
        if not os.path.isfile(file_path):
            return _wrap_error("新文件不支持含 position 字段的 insert 类型 edits")
        result = await _normalize_insert_edits_for_write(
            file_path, edits, preview=preview
        )
        if result is None:
            return _wrap_error("插入编辑预处理失败")
        err, normalized_edits, cleanup_dir = result
        if err:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
            return _wrap_error(err)
        try:
            return await _handle_write_edits(
                file_path=file_path,
                edits=normalized_edits,
                backup=backup,
                encoding=encoding,
                auto_format=auto_format,
                preview=preview,
                force=force,
                allow_dirty=allow_dirty,
            )
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

    return await _handle_write_edits(
        file_path=file_path,
        edits=edits,
        backup=backup,
        encoding=encoding,
        auto_format=auto_format,
        preview=preview,
        force=force,
        allow_dirty=allow_dirty,
    )


async def _normalize_insert_edits_for_write(
    file_path: str,
    edits: List[Dict[str, Any]],
    preview: bool = False,
):
    """Normalize insert-type edits (those with position field) into single-line replacements.

    When action=write receives a mix of range replacements and position-based inserts,
    this function reads the file, converts each insert edit into a single-line replacement
    (end_line = start_line, content includes both anchor text + inserted text), so that
    _handle_write_edits can apply them correctly with proper overlap detection.

    Returns (error_msg_or_None, normalized_edits, tmp_cleanup_dir).
    """
    detected_encoding = detect_encoding(file_path)
    read_path = file_path
    tmp_cleanup = None
    try:
        if _is_dfm_file(file_path):
            fmt = dfm_utils._detect_dfm_format(file_path)
            if fmt == "binary":
                tmp_cleanup = tempfile.mkdtemp(prefix="filetool_insert_norm_")
                read_path = os.path.join(tmp_cleanup, os.path.basename(file_path) + ".txt")
                conv_result = await dfm_utils.convert_dfm(file_path, read_path, to_text=True)
                if not conv_result.get("success"):
                    return (f"二进制 DFM 转换失败: {conv_result.get('message', '未知错误')}", edits, tmp_cleanup)
        with open(read_path, 'r', encoding=detected_encoding, newline='', buffering=BUFFER_SIZE_1MB) as f:
            lines = f.readlines()
    except Exception as e:
        return (str(e), edits, tmp_cleanup)

    has_crlf = any('\r\n' in line for line in lines)
    total_lines = len(lines)
    normalized: List[Dict[str, Any]] = []

    for i, edit in enumerate(edits):
        position = edit.get("position")
        if position is not None:
            s_1 = edit.get("start_line")
            content = edit.get("content")
            desc = edit.get("description", f"insert #{i}")
            old_content = _get_old_content(edit)

            if s_1 is None or not isinstance(s_1, int):
                return (f"edits[{i}] ({desc}): start_line 必须是整数", normalized, tmp_cleanup)
            if s_1 < 1:
                return (f"edits[{i}] ({desc}): start_line ({s_1}) 不能小于 1", normalized, tmp_cleanup)
            if content is None:
                return (f"edits[{i}] ({desc}): 缺少必需的 content", normalized, tmp_cleanup)
            if position not in ("before", "after"):
                return (f"edits[{i}] ({desc}): position 必须是 before 或 after", normalized, tmp_cleanup)

            anchor_idx = s_1 - 1
            if anchor_idx < 0 or anchor_idx >= total_lines:
                return (f"edits[{i}] ({desc}): start_line {s_1} 超出当前总行数 {total_lines}", normalized, tmp_cleanup)

            anchor_text = lines[anchor_idx]

            # Validate old_content against anchor line if provided
            if old_content is not None:
                if _normalize_code_for_compare(old_content) != _normalize_code_for_compare(anchor_text):
                    expected_lines = old_content.splitlines(keepends=True) or [""]
                    return ((
                        f"edits[{i}] ({desc}): old_content mismatch for insert anchor [{s_1}, {s_1}]\n"
                        f"  expected: {expected_lines[0].rstrip()}\n"
                        f"  actual: {anchor_text.rstrip()}"
                    ), normalized, tmp_cleanup)

            insert_text = _prepare_insert_content(content, has_crlf)
            if position == "before":
                replacement = insert_text + anchor_text
            else:
                anchor_for_replace = anchor_text
                if not anchor_for_replace.endswith(('\n', '\r\n')):
                    anchor_for_replace += '\r\n' if has_crlf else '\n'
                replacement = anchor_for_replace + insert_text

            normalized.append({
                "start_line": s_1,
                "end_line": s_1,
                "content": replacement,
                "old_content": old_content if old_content is not None else anchor_text,
                "description": desc,
            })
        else:
            normalized.append(edit)

    return (None, normalized, tmp_cleanup)


async def handle_replace(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=replace with mandatory old_content for existing files."""
    return await _handle_structured_write_action(arguments, "replace")


async def handle_insert(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=insert using old_content as an anchor line guard."""
    return await _handle_structured_write_action(arguments, "insert")


async def handle_delete(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=delete with mandatory old_content for existing files."""
    return await _handle_structured_write_action(arguments, "delete")


async def _handle_structured_write_action(arguments: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Normalize replace/insert/delete actions to the existing edit engine."""
    file_path = arguments.get("file_path")
    edits = arguments.get("edits")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    preview = arguments.get("preview", False) or arguments.get("dry_run", False)
    if arguments.get("preview", False):
        logger.warning("delphi_file: preview 参数已废弃，请使用 dry_run 替代")
    force = arguments.get("force", False)
    allow_dirty = arguments.get("allow_dirty", False)

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not edits:
        return _wrap_error(f"请提供 edits 参数（action={action}）")
    if not isinstance(edits, (list, tuple)):
        return _wrap_error("edits 必须是一个列表")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    if preview:
        lock_err = _acquire_read_lock(file_path)
    else:
        lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)

    anchor_tmp_cleanup = None
    try:
        file_exists = os.path.isfile(file_path)
        if not file_exists:
            if action != "replace":
                return _wrap_error(f"新文件不支持 action={action}，请使用 action=replace 或兼容 action=write 创建完整文件")
            return await _handle_write_edits(
                file_path=file_path,
                edits=edits,
                backup=backup,
                encoding=encoding,
                auto_format=auto_format,
                preview=preview,
                force=force,
                allow_dirty=allow_dirty,
                lock_already_held=True,
            )

        if not allow_dirty and not _all_edits_have_old_content(edits):
            try:
                _check_dirty(file_path, preview=preview)
            except RuntimeError as e:
                return _wrap_error(str(e))

        lines: List[str] = []
        has_crlf = False
        if action == "insert":
            try:
                lines, anchor_tmp_cleanup = await _read_structured_anchor_lines(file_path)
            except RuntimeError as e:
                return _wrap_error(str(e))
            has_crlf = any('\r\n' in line for line in lines)

        normalized_edits: List[Dict[str, Any]] = []
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return _wrap_error(f"edits[{i}] 必须是 dict")
            desc = edit.get("description", f"{action} #{i}")
            s_1 = edit.get("start_line")
            e_1 = edit.get("end_line")
            content = edit.get("content")
            old_content = _get_old_content(edit)

            if s_1 is None:
                return _wrap_error(f"edits[{i}] ({desc}): 缺少必需的 start_line")
            if not isinstance(s_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): start_line 必须是整数")
            if s_1 < 1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) 不能小于 1")
            if e_1 is not None and not isinstance(e_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): end_line 必须是整数")
            if action in ("replace", "delete") and e_1 is not None and s_1 > e_1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) > end_line ({e_1})，需满足 start_line ≤ end_line")
            if not _edit_has_non_empty_old_content(edit):
                return _wrap_error(f"edits[{i}] ({desc}): action={action} 必须提供非空 old_content")

            if action == "replace":
                if content is None:
                    return _wrap_error(f"edits[{i}] ({desc}): action=replace 必须提供 content")
                new_edit = dict(edit)
            elif action == "delete":
                if content not in (None, ""):
                    return _wrap_error(f"edits[{i}] ({desc}): action=delete 不接受非空 content")
                new_edit = dict(edit)
                new_edit["content"] = ""
            else:
                if content is None:
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert 必须提供 content")
                if content == "":
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert 的 content 不能为空")
                if e_1 is not None and e_1 != s_1:
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert 不支持 end_line 跨行，锚点只能是 start_line")
                position = edit.get("position", "before")
                if position not in ("before", "after"):
                    return _wrap_error(f"edits[{i}] ({desc}): position 必须是 before 或 after")
                anchor_idx = s_1 - 1
                if anchor_idx < 0 or anchor_idx >= len(lines):
                    return _wrap_error(f"edits[{i}] ({desc}): start_line {s_1} 超出当前总行数 {len(lines)}")
                anchor_text = lines[anchor_idx]
                if _normalize_code_for_compare(old_content or "") != _normalize_code_for_compare(anchor_text):
                    expected_lines = (old_content or "").splitlines(keepends=True)
                    msg = [
                        f"edits[{i}] ({desc}): old_content mismatch for insert anchor [{s_1}, {s_1}]",
                        "expected:",
                    ]
                    msg.extend(_format_line_snippet(expected_lines, 0, len(expected_lines)))
                    msg.append("actual:")
                    msg.extend(_format_line_snippet(lines, anchor_idx, anchor_idx + 1))
                    return _wrap_error("\n".join(msg))
                insert_text = _prepare_insert_content(content, has_crlf)
                if position == "before":
                    replacement = insert_text + anchor_text
                else:
                    anchor_for_replace = anchor_text
                    if not anchor_for_replace.endswith(('\n', '\r\n')):
                        anchor_for_replace += '\r\n' if has_crlf else '\n'
                    replacement = anchor_for_replace + insert_text
                new_edit = {
                    "start_line": s_1,
                    "end_line": s_1,
                    "content": replacement,
                    "old_content": old_content,
                    "description": desc,
                }
            normalized_edits.append(new_edit)

        return await _handle_write_edits(
            file_path=file_path,
            edits=normalized_edits,
            backup=backup,
            encoding=encoding,
            auto_format=auto_format,
            preview=preview,
            force=force,
            allow_dirty=True,  # 安全: old_content 校验已保障行号正确性，无需脏标记
            lock_already_held=True,
        )
    finally:
        if anchor_tmp_cleanup:
            shutil.rmtree(anchor_tmp_cleanup, ignore_errors=True)
        if preview:
            _release_read_lock(file_path)
        else:
            _release_write_lock(file_path)


def _format_unchanged_ranges(edit_results: List[Dict[str, Any]], total_lines_before: int) -> str:
    """从 edit 结果列表推导未变区域并格式化为文本

    每个 edit 之间和末尾的区域都是"未变"的，
    标注该区间在最终文件中的偏移量，方便 AI 查表而不需要自己算。

    Args:
        edit_results: 每个 edit 记录，含 actual_start(1-indexed), inserted, delta
        total_lines_before: 编辑前文件总行数

    Returns:
        格式如 "  未变: [1, 4] 不变, [14, 150] +3"
        所有 edit 覆盖了全文时返回空字符串
    """
    parts: List[str] = []
    cursor = 1  # 1-indexed 当前位置
    offset = 0
    for er in edit_results:
        start = er["actual_start"]
        if start > cursor:
            off_str = "不变" if offset == 0 else f"{offset:+d}"
            parts.append(f"[{cursor}, {start - 1}] {off_str}")
        # 跳过被 edit 覆盖的区域
        if er["inserted"] > 0:
            cursor = start + er["inserted"]
        # 删除操作不推进 cursor（没有新增内容占据位置）
        offset += er["delta"]
    # 末尾未变区域
    if cursor <= total_lines_before:
        off_str = "不变" if offset == 0 else f"{offset:+d}"
        parts.append(f"[{cursor}, {total_lines_before}] {off_str}")

    if not parts:
        return ""
    return f"  未变: {', '.join(parts)}"


async def _handle_write_edits(
    file_path: str,
    edits: List[Dict],
    backup: bool = True,
    encoding: str = "auto",
    auto_format: bool = False,
    preview: bool = False,
    force: bool = False,
    allow_dirty: bool = False,
    lock_already_held: bool = False,
) -> Dict[str, Any]:
    """批量写入内部实现（edits 数组，以原始文件为参照系）。"""
    if not edits:
        return _wrap_error("请提供 edits 列表")
    if not isinstance(edits, (list, tuple)):
        return _wrap_error("edits 必须是一个列表")

    if not lock_already_held:
        if preview:
            lock_err = _acquire_read_lock(file_path)
        else:
            lock_err = _acquire_write_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)

    bak_path = None
    read_path = file_path
    tmp_cleanup = None
    try:
        if not allow_dirty and not _all_edits_have_old_content(edits):
            try:
                _check_dirty(file_path, preview=preview)
            except RuntimeError as e:
                return _wrap_error(str(e))

        file_exists = os.path.isfile(file_path)
        if not file_exists:
            if len(edits) != 1:
                return _wrap_error("新文件只能有一个 edit")
            e0 = edits[0]
            if e0.get("start_line", 0) != 1:
                return _wrap_error("新文件必须从 start_line=1 开始")
            if not e0.get("content"):
                return _wrap_error("新文件必须提供 content")
            # 直接走全量写入
            content = e0["content"]
            original_encoding = encoding if encoding != "auto" else "utf-8-sig"

            # 预览模式
            if preview:
                return {
                    "status": "success",
                    "message": (
                        f"[preview] would create new file: {os.path.basename(file_path)}, "
                        f"{len(content.encode('utf-8'))} bytes"
                    ),
                }

            # 写入新文件：先写同卷临时文件，成功后再替换目标。
            temp_write_path = _make_temp_write_path(file_path)
            try:
                _write_text_temp(temp_write_path, content, original_encoding)
                record_authorized_write(
                    file_path,
                    tool="delphi_file",
                    operation="write",
                )
                _replace_with_temp(temp_write_path, file_path)
            except Exception as e:
                if os.path.exists(temp_write_path):
                    try:
                        os.remove(temp_write_path)
                    except OSError:
                        pass
                return _wrap_error(f"创建文件失败: {e}")

            _mark_dirty(file_path)
            return {
                "status": "success",
                "message": f"wrote: {os.path.basename(file_path)}, encoding: {original_encoding}",
            }

        is_dfm_binary = False
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
                is_dfm_binary = (fmt == "binary")
            except (FileNotFoundError, PermissionError) as e:
                return _wrap_error(str(e))

        detected_encoding = detect_encoding(file_path)
        if encoding == "auto":
            read_enc = detected_encoding
            write_enc = detected_encoding
            encoding_transcoded = False
        else:
            read_enc = detected_encoding
            if _is_encoding_compatible(encoding, detected_encoding):
                write_enc = detected_encoding
            else:
                write_enc = encoding
            encoding_transcoded = not _is_encoding_compatible(encoding, detected_encoding)

        validated_edits = []
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return _wrap_error(f"edits[{i}] 必须是 dict")
            s_1 = edit.get("start_line")
            e_1 = edit.get("end_line")
            c = edit.get("content")
            desc = edit.get("description", f"edit #{i}")
            old_content = _get_old_content(edit)
            if s_1 is None:
                return _wrap_error(f"edits[{i}] ({desc}): 缺少必需的 start_line")
            if c is None:
                return _wrap_error(f"edits[{i}] ({desc}): 缺少必需的 content")
            if not isinstance(s_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): start_line 必须是整数")
            if e_1 is not None and not isinstance(e_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): end_line 必须是整数")
            if s_1 < 1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) 不能小于 1")
            if e_1 is not None and s_1 > e_1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) > end_line ({e_1})，需满足 start_line ≤ end_line")
            validated_edits.append((s_1 - 1, e_1, c, desc, s_1, e_1, old_content))

        validated_edits.sort(key=lambda x: x[0])

        for i in range(len(validated_edits) - 1):
            curr_s_0, curr_e_0, _, _, _, _, _ = validated_edits[i]
            next_s_0, _, _, _, _, _, _ = validated_edits[i + 1]
            if curr_e_0 is None:
                return _wrap_error(
                    f"edits 区间重叠: \"{validated_edits[i][3]}\" (start={validated_edits[i][4]}) 覆盖到文件末尾，"
                    f"与 \"{validated_edits[i+1][3]}\" (start={validated_edits[i+1][4]}) 重叠"
                )
            if next_s_0 < curr_e_0:
                return _wrap_error(
                    f"edits 区间重叠: \"{validated_edits[i][3]}\" [{validated_edits[i][4]},{validated_edits[i][5]}] "
                    f"与 \"{validated_edits[i+1][3]}\" [{validated_edits[i+1][4]},...) 重叠"
                )

        if is_dfm_binary:
            tmp_dir = tempfile.mkdtemp(prefix="filetool_")
            text_path = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
            conv_result = await dfm_utils.convert_dfm(file_path, text_path, to_text=True)
            if not conv_result.get("success"):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return _wrap_error(f"二进制 DFM 转换失败: {conv_result.get('message', '未知错误')}")
            read_path = text_path
            read_enc = detect_encoding(read_path)
            tmp_cleanup = tmp_dir
        with open(read_path, 'r', encoding=read_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
            lines = f.readlines()

        total = len(lines)
        original_lines = lines[:]
        has_crlf = any('\r\n' in line for line in lines)

        cumulative_offset = 0
        results = []
        edit_results: List[Dict[str, Any]] = []
        all_success = True

        for s_0, e_0, c, desc, s_1, e_1, old_content in validated_edits:
            adj_s = s_0 + cumulative_offset
            adj_e = (e_0 + cumulative_offset) if e_0 is not None else len(lines)

            if adj_s < 0 or adj_s > len(lines):
                results.append(f"  ❌ {desc}: start_line {s_1}（调整后 {adj_s}）超出当前范围")
                all_success = False
                continue
            if adj_e > len(lines):
                results.append(f"  ❌ {desc}: end_line {e_1 or total}（调整后 {adj_e}）超出当前总行数 {len(lines)}")
                all_success = False
                continue
            if adj_s >= adj_e:
                results.append(f"  ❌ {desc}: 调整后范围为空 [{adj_s}, {adj_e})")
                all_success = False
                continue

            old_text = ''.join(lines[adj_s:adj_e])
            if old_content is not None:
                short_warning = _warn_if_old_content_too_short(old_content)
                if short_warning:
                    results.append(f"  ⚠️ {desc}: {short_warning}")
                expected_norm = _normalize_code_for_compare(old_content)
                actual_norm = _normalize_code_for_compare(old_text)
                if expected_norm != actual_norm:
                    expected_lines = old_content.splitlines(keepends=True)
                    results.append(
                        f"  ❌ {desc}: old_content mismatch for [{adj_s + 1}, {adj_e}]"
                    )
                    results.append("    expected:")
                    results.extend(_format_line_snippet(expected_lines, 0, len(expected_lines)))
                    results.append("    actual:")
                    results.extend(_format_line_snippet(lines, adj_s, adj_e))
                    all_success = False
                    continue

            removed = adj_e - adj_s
            removed_lines_preview = []

            before_len = len(lines)  # 编辑前行数（含此前 edits 累计）
            if c == '':
                if removed > 0 and removed <= 5:
                    actual_lineno = adj_s + 1
                    removed_lines_preview = [
                        (actual_lineno + i, lines[adj_s + i].rstrip('\n\r'))
                        for i in range(removed)
                    ]
                lines[adj_s:adj_e] = []
                inserted = 0
                c_lines = []
            else:
                if has_crlf:
                    c = c.replace('\r\n', '\n').replace('\n', '\r\n')
                else:
                    c = c.replace('\r\n', '\n')
                if not c.endswith('\n') and not c.endswith('\r\n'):
                    c = c + ('\r\n' if has_crlf else '\n')

                c_lines = c.splitlines(keepends=True)
                inserted = len(c_lines)

                if removed > 0 and removed <= 5:
                    actual_lineno = adj_s + 1  # 实际 1-indexed 起始行号
                    removed_lines_preview = [
                        (actual_lineno + i, lines[adj_s + i].rstrip('\n\r'))
                        for i in range(removed)
                    ]

                lines[adj_s:adj_e] = c_lines

            delta = inserted - removed
            prev_cumulative_offset = cumulative_offset  # 此 edit 发生前的累计偏移
            cumulative_offset += delta

            # 显示实际行号区间（指定行号不同时加括号标注）
            adj_s_display = adj_s + 1
            adj_e_display = adj_e  # 0-indexed exclusive → 1-indexed inclusive
            range_suffix = "" if adj_s_display == s_1 else f" (指定 {s_1})"
            if inserted == 0:
                results.append(
                    f"  [{adj_s_display}, {adj_e_display}] → deleted before line {adj_s_display} "
                    f"(offset: {delta:+d}){range_suffix}  {desc}"
                )
            else:
                results.append(
                    f"  [{adj_s_display}, {adj_e_display}] → [{adj_s_display}, {adj_e_display + delta}] "
                    f"(offset: {delta:+d}){range_suffix}  {desc}"
                )

            # Per-edit diff 预览（1-indexed 行号）
            if removed_lines_preview:
                for orig_lineno, rl in removed_lines_preview:
                    display = rl if len(rl) <= 80 else rl[:77] + "..."
                    results.append(f"    - L{orig_lineno}: {display}")
            if c_lines:
                max_show = min(len(c_lines), 5)
                for cl in c_lines[:max_show]:
                    display = cl.rstrip('\n\r')
                    display = display if len(display) <= 80 else display[:77] + "..."
                    results.append(f"    + {display}")
                if len(c_lines) > max_show:
                    results.append(f"    + ...（共 {len(c_lines)} 行）")

            # 此前编辑导致累积偏移时，通知 AI 实际行号偏移量
            if prev_cumulative_offset != 0:
                results.append(
                    f"    ℹ 偏移: 此前 {prev_cumulative_offset:+d} 行偏移, "
                    f"实际行号 = 指定行号{prev_cumulative_offset:+d}"
                )

            # 收集 edit 结果，用于生成"未变区域"提示
            edit_results.append({
                "actual_start": adj_s_display,
                "inserted": inserted,
                "delta": delta,
            })

        new_text = ''.join(lines)
        encoding_fallback = False
        fmt_msg = ""

        # 累计偏移一致性自检
        expected_total = total + cumulative_offset
        actual_total = len(lines)
        if actual_total != expected_total:
            results.append(
                f"  ❌ 内部错误: 编辑应用后行数 {actual_total} ≠ "
                f"原始 {total} + 累计偏移 {cumulative_offset} = {expected_total}，"
                f"请上报此问题"
            )
            all_success = False

        if not all_success and not preview:
            if bak_path and os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            summary = [
                "部分 edit 执行失败，已取消写入磁盘",
                f"failed: {len(validated_edits)} edits, {os.path.basename(file_path)}, encoding: {write_enc}",
                "",
            ]
            summary.extend(results)
            return {"status": "failed", "message": "\n".join(summary)}

        # AI 偏移错误检测
        if not force:
            orig_dup_contents = set()
            for i in range(1, len(original_lines)):
                prev = original_lines[i - 1].rstrip('\r\n')
                curr = original_lines[i].rstrip('\r\n')
                if prev and curr and prev == curr:
                    orig_dup_contents.add(prev)

            new_dup_lines = []
            for i in range(1, len(lines)):
                prev = lines[i - 1].rstrip('\r\n')
                curr = lines[i].rstrip('\r\n')
                if prev and curr and prev == curr and prev not in orig_dup_contents:
                    new_dup_lines.append((i + 1, prev))

            if new_dup_lines:
                dup_msgs = [f"    第 {i} 行: {txt}" for i, txt in new_dup_lines[:10]]
                if len(new_dup_lines) > 10:
                    dup_msgs.append(f"    ... 还有 {len(new_dup_lines) - 10} 处")
                warn = (
                    "⚠️ 写入完成，但检测到连续重复行，请 verify 结果。\n"
                    f"共 {len(new_dup_lines)} 处新增重复：\n" + "\n".join(dup_msgs)
                )
                results.append(warn)
                logger.warning(
                    f"续重行警告 ({os.path.basename(file_path)}): "
                    f"{len(new_dup_lines)} 处"
                )

        # 写入磁盘
        if not preview:
            temp_write_path = _make_temp_write_path(file_path)
            text_tmp = None
            try:
                if is_dfm_binary:
                    text_tmp = temp_write_path + ".txt"
                    _write_text_temp(text_tmp, new_text, write_enc)
                    conv_result = await dfm_utils.convert_dfm(text_tmp, temp_write_path, to_text=False)
                    if not conv_result.get("success"):
                        if bak_path and os.path.exists(bak_path):
                            try:
                                os.remove(bak_path)
                            except OSError:
                                pass
                        return _wrap_error(f"二进制 DFM 转换失败，已取消写入: {conv_result.get('message', '未知错误')}")
                else:
                    try:
                        _write_text_temp(temp_write_path, new_text, write_enc)
                    except UnicodeEncodeError:
                        logger.warning(f"编码 {write_enc} 写出失败，回退到 utf-8")
                        _write_text_temp(temp_write_path, new_text, "utf-8")
                        write_enc = "utf-8"
                        encoding_fallback = True

                if backup:
                    bak_path = create_backup(file_path)
                    if not bak_path:
                        return _wrap_error("创建备份失败，已取消写入")

                record_authorized_write(
                    file_path,
                    tool="delphi_file",
                    operation="write",
                )
                _replace_with_temp(temp_write_path, file_path)
            except Exception as ex:
                return _wrap_error(f"写入文件失败，已取消写入: {ex}")
            finally:
                for cleanup_path in (text_tmp, temp_write_path):
                    if cleanup_path and os.path.exists(cleanup_path):
                        try:
                            os.remove(cleanup_path)
                        except OSError:
                            pass

            # 写入后自动格式化
            if auto_format and _is_delphi_file(file_path):
                try:
                    formatted, write_enc, fmt_encoding_fallback, _ = await _apply_auto_format_atomically(
                        file_path, write_enc, has_crlf
                    )
                    if formatted:
                        fmt_msg = "，写入后已格式化"
                    if fmt_encoding_fallback:
                        encoding_fallback = True
                except Exception as ex:
                    logger.warning(f"写入后自动格式化失败: {ex}")
                    results.append(f"  ⚠ auto_format failed: {ex}")

            # auto_format 可能额外改变行数（展开 uses、调整空行等），重算真实偏移
            fmt_diff = 0
            if auto_format and not preview and os.path.isfile(file_path) and fmt_msg:
                try:
                    with open(file_path, 'r', encoding=write_enc, newline='',
                              buffering=BUFFER_SIZE_1MB) as f:
                        new_total = sum(1 for _ in f)
                    expected_total = total + cumulative_offset
                    if new_total != expected_total:
                        fmt_diff = new_total - expected_total
                        cumulative_offset += fmt_diff
                except Exception as ex:
                    logger.debug(f"auto_format 后重读行数失败: {ex}")
            if fmt_diff:
                results.append(
                    f"  ⚠ auto_format 额外偏移: {fmt_diff:+d}，累计总偏移: {cumulative_offset:+d}"
                )

            # 标记脏
            _mark_dirty(file_path)
        elif all_success:
            results.append("  ℹ preview 不清除脏标记；后续 write 仍需 read 或 old_content 校验")

        # 追加"未变区域"提示（失败时不输出，因为行号已被污染）
        if all_success and not preview:
            unchanged = _format_unchanged_ranges(edit_results, total)
            if unchanged:
                results.append(unchanged)

        # 汇总输出
        summary = []
        basename = os.path.basename(file_path)
        action_label = "preview" if preview else "wrote"
        header_parts = [
            f"{action_label}: {len(validated_edits)} edits, {basename}",
            f"encoding: {write_enc}",
        ]
        if allow_dirty:
            header_parts.append("⚠ allow_dirty: 脏标记绕过（请确保行号准确）")
        if preview:
            header_parts.append("preview: true（未写入磁盘）")
            if auto_format:
                header_parts.append("⚠ preview 不含 auto_format 偏移")
        if encoding_transcoded:
            header_parts.append(f"ℹ transcoded: {detected_encoding} → {write_enc}")
        if encoding_fallback:
            header_parts.append(f"⚠ fallback: {detected_encoding} → utf-8")
        if not preview and bak_path and backup:
            header_parts.append(f"backup: __history\\{os.path.basename(bak_path)}")
        if fmt_msg:
            header_parts.append("formatted: yes")
        if is_dfm_binary:
            header_parts.append("format: binary DFM converted")

        summary.append(", ".join(header_parts))
        summary.append("")
        summary.extend(results)

        if all_success:
            return {
                "status": "success",
                "message": "\n".join(summary),
            }
        else:
            summary.insert(0, "部分 edit 执行失败，请检查上述结果")
            return {"status": "failed", "message": "\n".join(summary)}

    finally:
        if not lock_already_held:
            if preview:
                _release_read_lock(file_path)
            else:
                _release_write_lock(file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)


async def handle_format(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 format action — 委托给 pasfmt.format_file / format_code。
    """
    file_path = arguments.get("file_path")
    action = arguments.get("mode", "file")
    uses_style = arguments.get("uses_style")
    dry_run = arguments.get("dry_run", False)
    backup_flag = arguments.get("backup", True)

    if action != "code" and file_path:
        path_err = _validate_path(file_path, arguments.get("project_path"))
        if path_err:
            return _wrap_error("路径安全校验失败: %s" % path_err)

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
            lock_err = _acquire_read_lock(file_path)
            if lock_err:
                return _wrap_error(lock_err)
            try:
                result = await pasfmt.format_file(
                    file_path=file_path,
                    dry_run=True,
                )
            finally:
                _release_read_lock(file_path)
        else:
            if dry_run:
                lock_err = _acquire_read_lock(file_path)
                if lock_err:
                    return _wrap_error(lock_err)
                try:
                    result = await pasfmt.format_file(
                        file_path=file_path,
                        dry_run=True,
                    )
                finally:
                    _release_read_lock(file_path)
            else:
                lock_err = _acquire_write_lock(file_path)
                if lock_err:
                    return _wrap_error(lock_err)
                try:
                    try:
                        detected_enc = detect_encoding(file_path)
                        with open(file_path, 'r', encoding=detected_enc, newline='',
                                  buffering=BUFFER_SIZE_1MB) as f:
                            original_text = f.read()
                        formatted, write_enc, encoding_fallback, backup_path = await _apply_auto_format_atomically(
                            file_path=file_path,
                            encoding=detected_enc,
                            has_crlf='\r\n' in original_text,
                            backup=backup_flag,
                            config_path=arguments.get("config_path"),
                            uses_style=uses_style,
                        )
                        result = {
                            "status": "success",
                            "formatted": formatted,
                            "message": "代码格式化成功" if formatted else "代码已是格式化状态",
                            "backup_file": backup_path,
                        }
                        if encoding_fallback:
                            result["message"] += f"，编码回退: {detected_enc} → {write_enc}"
                    except Exception as ex:
                        result = _wrap_error(f"格式化失败: {ex}")
                    else:
                        # 格式化成功 → 标记脏（行号已变，强制 re-read）
                        # ⚠ 不计算偏移量：pasfmt 可能重构代码结构（展开 uses、调整 begin/end 等），
                        #   格式化前后的行号无线性对应关系。AI 须通过 dirty flag 触发 re-read。
                        if result.get("status") == "success" and result.get("formatted"):
                            _mark_dirty(file_path)
                finally:
                    _release_write_lock(file_path)

    # pasfmt.format_file / format_code 结果已统一为 dict
    return result


async def handle_encode(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 encode action — 文件编码转换。

    将文件从一种编码转换为另一种编码。
    自动检测源编码（from_encoding="auto"），写入目标编码（to_encoding 必需）。

    参数:
      file_path: 文件路径
      from_encoding: 源编码（"auto"=自动检测，默认 "auto"）
      to_encoding: 目标编码（必需），如 utf-8/utf-8-sig/gbk/utf-16/utf-16-le/utf-16-be
      backup: 转换前是否备份到 __history（默认 true）
      preview: 预览模式（默认 false）
    """
    file_path = arguments.get("file_path")
    from_encoding = arguments.get("from_encoding", "auto")
    to_encoding = arguments.get("to_encoding")
    backup = arguments.get("backup", True)
    preview = arguments.get("preview", False)

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not to_encoding:
        return _wrap_error("请提供 to_encoding 参数（目标编码）")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    if not os.path.isfile(file_path):
        return _wrap_error(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _DELPHI_EXTENSIONS:
        return _wrap_error(f"不支持的文件类型: {ext}，仅支持 Delphi 源文件")

    # 获取写入锁（读+写互斥），预览模式下用读锁
    if preview:
        lock_err = _acquire_read_lock(file_path)
    else:
        lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)

    try:
        # 检测源编码
        detected_enc = detect_encoding(file_path)
        read_enc = detected_enc if from_encoding == "auto" else from_encoding

        # 解析目标编码（支持 "ansi" 别名 → 系统 ANSI 代码页）
        target_enc = to_encoding.lower()
        if target_enc == "ansi":
            try:
                target_enc = locale.getpreferredencoding()
            except Exception:
                target_enc = "utf-8"
        else:
            target_enc = to_encoding

        # 校验编码合法性
        try:
            codecs.lookup(read_enc)
        except LookupError:
            return _wrap_error(f"源编码 '{read_enc}' 不可识别")
        try:
            codecs.lookup(target_enc)
        except LookupError:
            return _wrap_error(f"目标编码 '{target_enc}' 不可识别")

        # 预览模式
        if preview:
            read_size = os.path.getsize(file_path)
            return {
                "status": "success",
                "message": (
                    f"[preview] would convert: {os.path.basename(file_path)}\n"
                    f"  from: {detected_enc} (检测) / {read_enc} (指定)\n"
                    f"  to:   {target_enc}\n"
                    f"  size: {read_size} bytes"
                ),
            }

        # 读取文件内容
        try:
            with open(file_path, 'r', encoding=read_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
                text = f.read()
        except UnicodeDecodeError:
            # 用户显式指定 from_encoding 解码失败时，自动回退到自动检测结果
            if from_encoding != "auto":
                logger.warning(
                    f"用户指定编码 '{read_enc}' 解码失败，回退到自动检测 '{detected_enc}'"
                )
                try:
                    with open(file_path, 'r', encoding=detected_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
                        text = f.read()
                    read_enc = detected_enc
                except UnicodeDecodeError:
                    return _wrap_error(
                        f"指定编码 '{from_encoding}' 与自动检测 '{detected_enc}' 均无法解码。"
                        "请确认文件编码后显式指定正确的 from_encoding"
                    )
            else:
                return _wrap_error(f"自动检测编码 '{detected_enc}' 解码失败。请尝试显式指定 from_encoding")
        except Exception as e:
            return _wrap_error(f"读取文件失败: {e}")

        original_size = len(text.encode(read_enc, errors='replace'))
        new_size = len(text.encode(target_enc, errors='replace'))

        # BOM 处理：读入时剥离现有 BOM，由输出编码决定是否重新添加
        text_stripped = text.lstrip('\ufeff')

        # 校验：先用目标编码回读，确保转换可逆
        try:
            encoded_bytes = text_stripped.encode(target_enc, errors='strict')
            decoded_back = encoded_bytes.decode(target_enc)
            if decoded_back != text_stripped:
                logger.warning(f"编码转换存在不可逆字符")
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            return _wrap_error(f"编码转换失败：目标编码 '{target_enc}' 无法表示文件中的某些字符: {e}")

        # 创建备份
        bak_path = None
        if backup:
            bak_path = create_backup(file_path)
            if not bak_path:
                return _wrap_error("创建备份失败，已取消转换")

        # 写入新编码（使用已剥离 BOM 的文本，输出编码决定是否加 BOM）
        temp_write_path = _make_temp_write_path(file_path)
        try:
            _write_text_temp(temp_write_path, text_stripped, target_enc)
            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="encode",
            )
            _replace_with_temp(temp_write_path, file_path)
        except UnicodeEncodeError:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass
            # 回退备份取消转换
            if bak_path:
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            return _wrap_error(f"写入编码 '{target_enc}' 失败：存在无法编码的字符")
        except Exception as e:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass
            if bak_path:
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            return _wrap_error(f"写入文件失败: {e}")
        finally:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass

        # 标记脏（行号无变化但内容字节已变，防止 AI 基于旧内容继续操作）
        _mark_dirty(file_path)

        # 构造返回消息
        is_bom = target_enc == "utf-8-sig" or "utf-16" in target_enc
        parts = [
            f"converted: {os.path.basename(file_path)}",
            f"from: {read_enc} → to: {target_enc}",
            f"size: {original_size} bytes → {new_size} bytes",
        ]
        if is_bom:
            parts.append("BOM: yes")
        if bak_path:
            parts.append(f"backup: __history\\{os.path.basename(bak_path)}")
        if read_enc != detected_enc:
            parts.append(f"note: detected encoding was {detected_enc}")

        return {
            "status": "success",
            "message": ", ".join(parts),
            "original_encoding": read_enc,
            "new_encoding": target_enc,
            "original_size": original_size,
            "new_size": new_size,
        }
    finally:
        if preview:
            _release_read_lock(file_path)
        else:
            _release_write_lock(file_path)


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

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    if backup_action == "create":
        lock_err = _acquire_read_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)
        try:
            bp = create_backup(file_path)
        finally:
            _release_read_lock(file_path)
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
        lock_err = _acquire_write_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)
        try:
            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="backup_restore",
            )
            bp = restore_backup(file_path, version=version)
        finally:
            _release_write_lock(file_path)
        if bp:
            ver_str = f"v{version}" if version else "最新版本"
            return {"status": "success", "message": f"已从 {ver_str} 恢复: {bp}"}
        return _wrap_error(f"恢复失败: {file_path}")

    else:
        return _wrap_error(f"未知 backup_action: {backup_action}")


# ============================================================
# uses 子句操作
# ============================================================

# 匹配 uses 子句的正则：uses Unit1, Unit2; 可以跨多行
# 先剥离 Pascal 注释（花括号 { } + 星号括号 (* *)），避免注释内的 ; 干扰匹配
# 捕获组: (1)uses关键字 (2)整个单元列表 (3)分号
_USES_RE = re.compile(
    r'\b(uses)\b\s+(.*?)\s*(;)',
    re.DOTALL | re.IGNORECASE,
)

# 匹配 Pascal 注释的正则：花括号 { ... }（含 $ 条件编译指令）和星号括号 (* ... *)
_PASCAL_COMMENTS_RE = re.compile(r'\{[^}]*\}|\(\*.*?\*\)', re.DOTALL)


def _strip_comments_with_offset_map(text: str) -> tuple:
    """剥离 Pascal 注释（花括号 + 星号括号），构建 stripped→original 偏移映射。

    返回 (stripped_text, offset_map):
      - stripped_text: 剥离注释后的文本
      - offset_map: 列表，长度 = len(stripped_text) + 1（含 exclusive end sentinel)
        offset_map[i] = 原始文本中对应字符的位置

    偏移映射用于将 stripped 文本中搜索到的位置映射回原始文本位置，
    避免 uses 子句前存在注释/编译指令时切片错位导致文件破坏。
    """
    offset_map = []
    stripped_segments = []
    pos = 0  # 当前在原始文本中的位置

    for match in _PASCAL_COMMENTS_RE.finditer(text):
        # 保留注释之前的文本段，记录每个字符的原始位置
        segment = text[pos:match.start()]
        if segment:
            offset_map.extend(range(pos, pos + len(segment)))
            stripped_segments.append(segment)
        pos = match.end()

    # 保留最后一段文本
    segment = text[pos:]
    if segment:
        offset_map.extend(range(pos, pos + len(segment)))
        stripped_segments.append(segment)

    # Sentinel: exclusive end 位置映射到原始文本末尾
    offset_map.append(len(text))

    stripped_text = ''.join(stripped_segments)
    return (stripped_text, offset_map)


def _find_uses_section(text: str, section: str) -> Optional[tuple]:
    """在指定区域(interface/implementation)查找 uses 子句。

    搜索前剥离 Pascal 注释（花括号 + 星号括号），避免注释内的 ';' 干扰匹配。
    返回的偏移量通过 offset_map 映射回原始 text，确保切片正确。

    返回 (uses_start, uses_end, units_text) 元组，或 None。
    uses_start/uses_end 是基于原始 text 的偏移（已从 stripped 映射回 original）。
    """
    section_lower = section.lower()

    # 剥离注释，构建偏移映射（stripped 位置 → 原始位置）
    stripped, offset_map = _strip_comments_with_offset_map(text)

    if section_lower == "interface":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        end = impl_pos.start() if impl_pos else len(stripped)
        header = re.search(r'\b(?:unit|program|library)\b', stripped[:end], re.IGNORECASE)
        start = header.end() if header else 0
        chunk = stripped[start:end]
        match = _USES_RE.search(chunk)
        if match:
            s_stripped = match.start() + start
            e_stripped = match.end() + start
            # 通过 offset_map 映射回原始文本位置
            s_original = offset_map[s_stripped]
            e_original = offset_map[e_stripped]
            return (s_original, e_original, match.group(2))
        return None

    elif section_lower == "implementation":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        if not impl_pos:
            return None
        start = impl_pos.end()
        chunk = stripped[start:]
        match = _USES_RE.search(chunk)
        if match:
            s_stripped = match.start() + start
            e_stripped = match.end() + start
            # 通过 offset_map 映射回原始文本位置
            s_original = offset_map[s_stripped]
            e_original = offset_map[e_stripped]
            return (s_original, e_original, match.group(2))
        return None

    return None


def _parse_units_from_uses(units_text: str) -> List[str]:
    """从 uses 子句的单元列表文本中解析出各个单元条目。

    每个条目保留 'in ...' 部分，如 "Unit1 in 'Unit1.pas'"。
    """
    flat = units_text.replace('\r\n', ' ').replace('\n', ' ')
    parts = [p.strip() for p in flat.split(',') if p.strip()]
    return parts


def _build_uses_text(unit_names: List[str], original_text: str) -> str:
    """从单元名列表重建 uses 子句文本，保持原始换行风格。

    如果原始是单行，保持单行；如果跨多行，每行一个单元。
    """
    line_ending = '\r\n' if '\r\n' in original_text else '\n'
    has_multiline = '\n' in original_text.strip()

    if has_multiline and len(unit_names) > 1:
        # 多行格式：每行一个单元，缩进 2 空格，逗号在行尾
        lines = []
        for i, name in enumerate(unit_names):
            if i < len(unit_names) - 1:
                lines.append(f"  {name},{line_ending}")
            else:
                lines.append(f"  {name}")
        return ''.join(lines)
    else:
        # 单行格式
        return ', '.join(unit_names)


async def handle_uses(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 uses action — 增加/删除 uses 子句中的单元。

    参数:
      file_path: 文件路径(.pas/.dpr/.dpk)
      uses_action: "add" 或 "remove"
      unit_name: 单元名(如 "Vcl.Dialogs")，可含命名空间
      uses_section: "interface" 或 "implementation" (默认 "interface")
    """
    file_path = arguments.get("file_path")
    uses_action = arguments.get("uses_action", "add")
    unit_name = arguments.get("unit_name", "")
    uses_section = arguments.get("uses_section", "interface")

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not unit_name:
        return _wrap_error("请提供 unit_name 参数")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)
    if uses_action not in ("add", "remove"):
        return _wrap_error("uses_action 必须是 'add' 或 'remove'")

    if not os.path.isfile(file_path):
        return _wrap_error(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.pas', '.dpr', '.dpk', '.inc'):
        return _wrap_error(f"uses 操作仅支持 .pas/.dpr/.dpk/.inc 文件，不支持 {ext}")

    # 获取写入许可（读+写互斥）
    lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)
    try:
        # 读取文件（始终用实际检测编码读取，避免乱码；写出按 encoding 参数决定）
        encoding = arguments.get("encoding", "auto")
        detected_enc = detect_encoding(file_path)
        if encoding == "auto":
            read_enc = detected_enc
            write_enc = detected_enc
        else:
            read_enc = detected_enc
            if _is_encoding_compatible(encoding, detected_enc):
                write_enc = detected_enc
            else:
                write_enc = encoding

        with open(file_path, 'r', encoding=read_enc, newline='',
                  buffering=BUFFER_SIZE_1MB) as f:
            text = f.read()

        # 查找 uses 子句
        result = _find_uses_section(text, uses_section)
        if not result:
            section_hint = f"{uses_section} 区域"
            return _wrap_error(
                f"在 {section_hint} 中未找到 uses 子句。"
                "如果文件是新单元，请先用 write action 写入完整单元结构"
            )

        uses_start, uses_end, units_text = result
        existing_units = _parse_units_from_uses(units_text)

        # 检查单元是否已存在/不存在
        unit_name_stripped = unit_name.strip()

        # 提取单元名（不含 'in' 子句）用于比较
        def _get_unit_name(entry: str) -> str:
            in_match = re.match(r"(\S+)\s+in\s+", entry, re.IGNORECASE)
            return in_match.group(1) if in_match else entry

        def _get_short_name(name: str) -> str:
            """提取短名（去掉命名空间前缀），如 'Vcl.Forms' → 'Forms'"""
            return name.rsplit('.', 1)[-1]

        existing_names = [_get_unit_name(e) for e in existing_units]
        existing_names_lower = [n.lower() for n in existing_names]
        unit_name_lower = unit_name_stripped.lower()

        if uses_action == "add":
            if unit_name_lower in existing_names_lower:
                return {"status": "success", "message": f"{unit_name_stripped} 已在 {uses_section} uses 中，无需添加"}
            # 检查命名空间前缀冲突：短名相同且至少一方无命名空间时才视为冲突
            # Forms ↔ Vcl.Forms 冲突，Vcl.Forms ↔ FMX.Forms 不冲突（不同单元）
            new_short = _get_short_name(unit_name_stripped).lower()
            collision_idx = None
            for i, existing in enumerate(existing_names):
                if existing.lower() != unit_name_lower and _get_short_name(existing).lower() == new_short:
                    # 至少一方是短名（无命名空间）才算冲突
                    if '.' not in unit_name_stripped or '.' not in existing:
                        collision_idx = i
                        break
            if collision_idx is not None:
                if '.' in unit_name_stripped and '.' not in existing_names[collision_idx]:
                    # 长名替换短名：Vcl.Forms 替换 Forms
                    replaced_unit = existing_units[collision_idx]
                    new_units = existing_units.copy()
                    new_units[collision_idx] = unit_name_stripped
                    new_units.sort(key=lambda e: _get_unit_name(e).lower())
                else:
                    # 短名冲突长名，已有长名则跳过
                    return {"status": "success", "message": f"{unit_name_stripped} 与已有单元 {existing_names[collision_idx]} 短名相同，视为同一单元，跳过"}
            else:
                # 无冲突，直接插入
                new_units = existing_units + [unit_name_stripped]
                new_units.sort(key=lambda e: _get_unit_name(e).lower())
        else:  # remove
            if unit_name_lower not in existing_names_lower:
                return {"status": "success", "message": f"{unit_name_stripped} 不在 {uses_section} uses 中，无需删除"}
            new_units = [e for e in existing_units if _get_unit_name(e).lower() != unit_name_lower]

        if not new_units:
            return _wrap_error(f"删除 {unit_name_stripped} 后 uses 子句将为空，请改用 write action 重写文件")

        # 重建 uses 文本
        new_units_text = _build_uses_text(new_units, units_text)
        new_uses_clause = f"uses {new_units_text};"

        # 替换原 uses 子句
        new_text = text[:uses_start] + new_uses_clause + text[uses_end:]

        # 写出（用 write_enc 编码，与读取编码可能不同 = 透明转码）
        encoding_fallback = False
        backup_path = None
        backup = arguments.get("backup", True)
        temp_write_path = _make_temp_write_path(file_path)
        try:
            try:
                _write_text_temp(temp_write_path, new_text, write_enc)
            except UnicodeEncodeError:
                logger.warning(f"编码 {write_enc} 写出失败，回退到 utf-8")
                _write_text_temp(temp_write_path, new_text, "utf-8")
                write_enc = "utf-8"
                encoding_fallback = True

            if backup:
                backup_path = create_backup(file_path)
                if not backup_path:
                    return _wrap_error("创建备份失败，已取消写入")

            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="uses",
            )
            _replace_with_temp(temp_write_path, file_path)
        except UnicodeEncodeError:
            return _wrap_error("写入文件失败，已取消写入: 编码转换失败")
        except Exception as ex:
            return _wrap_error(f"写入文件失败，已取消写入: {ex}")
        finally:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass

        # 自动格式化
        fmt_msg = ""
        fmt_warning = ""
        if arguments.get("auto_format", False):
            try:
                formatted, write_enc, fmt_encoding_fallback, _ = await _apply_auto_format_atomically(
                    file_path, write_enc, '\r\n' in text
                )
                if formatted:
                    fmt_msg = "，已格式化"
                if fmt_encoding_fallback:
                    encoding_fallback = True
            except Exception as ex:
                logger.warning(f"uses 操作后格式化失败: {ex}")
                fmt_warning = f"⚠ auto_format failed: {ex}"

        # 计算偏移量（uses 修改也会影响行号）
        s_0 = text[:uses_start].count('\n')          # 0-indexed: uses 关键字所在行
        uses_old_text = text[uses_start:uses_end]
        removed = uses_old_text.count('\n')           # 旧 uses 子句占用的行数
        inserted = new_uses_clause.count('\n')        # 新 uses 子句占用的行数
        offset = inserted - removed
        # 计算 exclusive end: uses_end 所在行的下一行
        e_0 = text[:uses_end].count('\n') + 1

        action_desc = "added" if uses_action == "add" else "removed"
        # 单行 meta (与 read/write 对齐，1-indexed)
        basename = os.path.basename(file_path)
        new_e = e_0 + offset
        parts = [
            f"wrote: {basename}",
            f"action: {action_desc} {unit_name_stripped} in {uses_section}",
            f"uses: {', '.join(new_units)}",
            f"1-indexed [{s_0 + 1}, {e_0}] → [{s_0 + 1}, {new_e}] (offset: {offset:+d})",
            f"encoding: {write_enc}",
        ]
        if backup_path:
            parts.append(f"backup: __history\\{os.path.basename(backup_path)}")
        if fmt_msg:
            parts.append("formatted: yes")
        if fmt_warning:
            parts.append(fmt_warning)
        if encoding_fallback:
            parts.append(f"⚠ fallback: {detected_enc} → utf-8")
        if write_enc != detected_enc and not encoding_fallback:
            parts.append(f"ℹ transcoded: {detected_enc} → {write_enc}")

        # uses 操作修改了文件 → 标记脏
        _mark_dirty(file_path)

        return {"status": "success", "message": ", ".join(parts)}
    finally:
        _release_write_lock(file_path)


# ============================================================
# 主入口
# ============================================================

async def handle_fix_garbled(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    修复 Delphi 文件中的中文乱码。

    Delphi 在无 BOM 时按 ANSI/GBK 解读 UTF-8 中文字节，导致编译后乱码。
    本动作自动检测以下乱码模式并修复：

    1. 无 BOM 的 UTF-8（Delphi 误读为 GBK）→ 添加 UTF-8 BOM
    2. U+FFFD 替换字符（�）→ 尝试从残留 GBK 字节恢复原文
    3. UTF-8 字节被存储为 GBK（双重编码）→ 反向恢复

    修复步骤:
      1. 创建备份到 __history
      2. 扫描文件的乱码模式和位置
      3. 根据模式应用对应修复
      4. 返回修复汇总

    Args:
        file_path: 目标文件路径
        backup: 是否创建备份（默认 True）
        target_encoding: 目标编码（默认 utf-8-sig，即带 BOM 的 UTF-8）
    """
    import chardet

    file_path = arguments.get("file_path")
    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)
    backup = arguments.get("backup", True)
    target_enc = arguments.get("target_encoding", "utf-8-sig")

    # 读取原始字节
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
    except FileNotFoundError:
        return _wrap_error(f"文件不存在: {file_path}")
    except PermissionError:
        return _wrap_error(f"无权限读取: {file_path}")

    fixes_applied = []
    original_size = len(raw)

    # ── 检查 1: 是否有 U+FFFD 替换字符（\xef\xbf\xbd）──
    fffd_count = raw.count(b'\xef\xbf\xbd')
    if fffd_count > 0:
        fixes_applied.append(f"发现 {fffd_count} 处 U+FFFD 替换字符（�），尝试恢复…")

        # 策略: 移除 FFFD 序列，将残留字节尝试按 GBK 解码
        # U+FFFD 通常出现在「GBK→UTF-8 误读」时失效的字节被替换
        cleaned = raw.replace(b'\xef\xbf\xbd', b'')
        recovered_text = None
        for enc in ['gbk', 'gb18030', 'gb2312']:
            try:
                decoded = cleaned.decode(enc)
                # 检查解码结果是否含有意义的中文（4E00-9FFF 范围的字符占比）
                cjk_count = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff')
                total_cjk = sum(1 for c in decoded if ord(c) > 127)
                if cjk_count > 0 and (total_cjk == 0 or cjk_count / total_cjk > 0.3):
                    recovered_text = decoded
                    fixes_applied.append(f"  通过 {enc} 恢复 {cjk_count} 个中文字符")
                    break
            except:
                continue

        if recovered_text:
            # 重新编码为目标编码
            raw = recovered_text.encode(target_enc)
            fixes_applied.append(f"  已修复并重新编码为 {target_enc}")
        else:
            fixes_applied.append(f"  无法自动恢复 U+FFFD 内容，已跳过")

    # ── 检查 2: 是否为 UTF-8 无 BOM（Delphi 可能误读为 ANSI）──
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    is_utf16 = raw[:2] in (b'\xff\xfe', b'\xfe\xff')

    if not has_bom and not is_utf16:
        # 检测编码
        enc_result = chardet.detect(raw)
        detected_enc = enc_result.get('encoding', '').lower()
        confidence = enc_result.get('confidence', 0)

        if 'utf-8' in detected_enc and confidence > 0.8:
            # 检查文件中是否有中文
            try:
                text = raw.decode('utf-8')
                has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
                if has_cjk:
                    raw = b'\xef\xbb\xbf' + raw
                    fixes_applied.append(
                        f"  编码检测为 UTF-8（置信度 {confidence:.0%})，包含中文，无 BOM → 已添加 UTF-8 BOM"
                    )
            except UnicodeDecodeError:
                pass

    # ── 检查 3: 编码检测为 GBK 但实际是 UTF-8（Delphi 以 ANSI 保存了 UTF-8 字节）──
    if not has_bom and not is_utf16:
        enc_result = chardet.detect(raw)
        detected_enc = enc_result.get('encoding', '').lower()
        confidence = enc_result.get('confidence', 0)

        if detected_enc in ('gbk', 'gb2312', 'gb18030') and confidence > 0.6:
            # 尝试用 UTF-8 解码，如果有意义的中文，说明是 UTF-8 被误存为 GBK
            try:
                text_utf8 = raw.decode('utf-8')
                cjk_utf8 = sum(1 for c in text_utf8 if '\u4e00' <= c <= '\u9fff')
                if cjk_utf8 > 0:
                    # 已经是有效 UTF-8，只是编码被误检测
                    raw = b'\xef\xbb\xbf' + raw
                    fixes_applied.append(
                        f"  文件被检测为 {detected_enc} 但其实是 UTF-8（含 {cjk_utf8} 个中文），"
                        f"已添加 UTF-8 BOM 防止 Delphi 误读"
                    )
            except UnicodeDecodeError:
                # 尝试反向恢复: 如果 UTF-8 字节被当作 GBK 存储，需要反向修复
                # 即: 把当前文件按 GBK 读出的字符转回其原始 UTF-8 编码
                pass

    # ── 写入修复结果 ──
    if not fixes_applied:
        return {
            "status": "success",
            "message": f"未发现乱码问题: {os.path.basename(file_path)}（{original_size} 字节）"
        }

    # 创建备份
    bak_path = None
    if backup:
        lock_err = _acquire_read_lock(file_path)
        if not lock_err:
            try:
                bak_path = create_backup(file_path)
            finally:
                _release_read_lock(file_path)

    # 写回过修复后内容
    lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)
    try:
        temp_path = _make_temp_write_path(file_path)
        try:
            with open(temp_path, 'wb') as f:
                f.write(raw)
            record_authorized_write(file_path, tool="delphi_file", operation="fix_garbled")
            _replace_with_temp(temp_path, file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return _wrap_error(f"写入文件失败: {e}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    finally:
        _release_write_lock(file_path)

    _mark_dirty(file_path)

    summary = "\n".join(fixes_applied)
    return {
        "status": "success",
        "message": (
            f"修复完成: {os.path.basename(file_path)}\n"
            f"大小: {original_size} → {len(raw)} 字节\n"
            f"{summary}"
        ),
        "fixes": fixes_applied,
    }


async def handle_file_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    file_tool 主入口。
    write 使用 edits 数组处理单处或多处修改。
    """
    action = arguments.get("action", "read")

    if action == "read":
        return await handle_read(arguments)
    elif action == "write":
        return await handle_write(arguments)
    elif action == "replace":
        return await handle_replace(arguments)
    elif action == "insert":
        return await handle_insert(arguments)
    elif action == "delete":
        return await handle_delete(arguments)
    elif action == "format":
        return await handle_format(arguments)
    elif action == "backup":
        return await handle_backup(arguments)
    elif action == "encode":
        return await handle_encode(arguments)
    elif action == "uses":
        return await handle_uses(arguments)
    elif action == "fix_garbled":
        return await handle_fix_garbled(arguments)
    else:
        return _wrap_error(f"未知 action: {action}。支持的 action: read, write, replace, insert, delete, format, backup, encode, uses, fix_garbled")
