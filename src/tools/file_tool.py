"""
delphi_file — Delphi 文件专用操作工具（MCP 注册名 delphi_file，原 file_tool）

整合读取/写入/格式化/备份管理，覆盖 Delphi 文件操作完整生命周期。
MCP 客户端以 delphi_file 名注册，旧名 file_tool 仍作为别名兼容。

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
import re
from typing import Any, Optional, Dict, List
from mcp.types import CallToolResult
from ..utils.logger import get_logger
from ..utils.file_backup import create_backup, list_backups, restore_backup, detect_encoding
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


def _validate_path(file_path: str) -> Optional[str]:
    """校验文件路径安全性，返回 None 表示安全，否则返回错误信息"""
    if '\0' in file_path:
        return "路径包含 null 字节"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "路径解析失败: %s" % str(e)
    for sensitive_dir in _SYSTEM_SENSITIVE_DIRS:
        try:
            resolved_relative = os.path.relpath(resolved, sensitive_dir)
            if not resolved_relative.startswith('..'):
                return "路径位于系统敏感目录中: %s" % sensitive_dir
        except ValueError:
            pass
    return None


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
    start_line: int = 0,
    limit: int = 500,
    search_in: str = "all",
    project_path: Optional[str] = None,
    end_line: Optional[int] = None,
    show_line_numbers: bool = False,
) -> Dict[str, Any]:
    """
    读取文件内容的内部实现。

    如果文件在本地直接存在，检测编码后直接读取（支持 UTF-8/GBK/UTF-16 等）。
    否则委托给 read_source_file 走知识库搜索路径。

    start_line/end_line 为 0-indexed 左闭右开区间：
      - start_line=0 表示从文件第 1 行开始
      - end_line 不传时等价于「读到 limit 行为止」

    show_line_numbers: 为 True 时每行前面添加行号前缀（如 "     1: unit Unit1;"），
                       行号为 1-based 绝对行号。
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
            logger.debug("获取系统默认编码失败，跳过ANSI回退")

        last_error = None
        for enc in fallback_encodings:
            try:
                # 流式读取：只读取需要的行，避免大文件全量读入内存
                # 对于读取开头 N 行或指定行范围的场景，线性扫描比 readlines() 更省内存
                # target_start/target_end 是内部 1-indexed inclusive 表示
                target_start = max(start_line, 0) + 1
                target_end = end_line if end_line is not None else (start_line + limit)
                selected = []
                reached_eof = True  # 跟踪是否读到文件末尾
                line_no = 0  # 空文件时 for 循环体不会执行，需初始化
                with open(file_path, 'r', encoding=enc, newline='',
                          buffering=1048576) as f:
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

                text = ''.join(selected)

                # show_line_numbers: 为每行添加 1-based 绝对行号前缀
                if show_line_numbers and selected:
                    line_offset = max(start_line, 0)  # 0-indexed start
                    numbered_lines = []
                    for i, line in enumerate(selected):
                        abs_lineno = line_offset + i + 1  # 1-based 绝对行号
                        numbered_lines.append(f"{abs_lineno:>6}: {line}")
                    text = ''.join(numbered_lines)

                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                base_name = os.path.basename(file_path)
                actual_end_line = start_line + lines_shown  # 0-indexed exclusive end

                if total_lines is not None:
                    total_display = str(total_lines)
                else:
                    total_display = f"至少 {target_end} 行"

                range_suffix = "（带行号）" if show_line_numbers else ""
                summary = (
                    f"文件: {base_name}\n"
                    f"完整路径: {os.path.abspath(file_path)}\n"
                    f"总行数: {total_display}\n"
                    f"显示范围: 第 {start_line} 行 到 第 {actual_end_line} 行 (0-indexed, [start, end)){range_suffix}\n"
                    f"编码: {enc}\n"
                    f"============================================================\n\n"
                )

                result = summary + text

                # 截断提示（与 read_source_file.py 一致）
                if not reached_eof:
                    result += (
                        f"\n... (已截断，文件至少有 {target_end} 行) ...\n"
                        f"提示: 使用 start_line={target_end} 继续读取后续内容 (0-indexed)\n"
                    )

                return {"status": "success", "message": result}
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
    start_line: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """按类名/函数名搜索并读取文件"""
    args = {
        "type_name": type_name,
        "record_name": record_name,
        "function_name": function_name,
        "search_in": search_in,
        "start_line": start_line,
        "max_lines": limit,  # read_source_file 内部仍用 max_lines
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
    start_line = arguments.get("start_line", 0)
    end_line = arguments.get("end_line")
    if end_line is not None:
        limit = min(end_line - start_line, 1000)
    else:
        limit = min(arguments.get("limit", 500), 1000)
    search_in = arguments.get("search_in", "all")
    project_path = arguments.get("project_path")
    show_line_numbers = arguments.get("show_line_numbers", False)

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
        )

    # --- 路径模式 ---
    if not file_path:
        return _wrap_error("请提供 file_path 参数")

    path_err = _validate_path(file_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

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
            limit=limit,
            search_in=search_in,
            project_path=project_path,
            end_line=end_line,
            show_line_numbers=show_line_numbers,
        )
    finally:
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)


async def _handle_partial_write(
    file_path: str,
    content: str,
    backup: bool,
    encoding: str,
    auto_format: bool,
    start_line: Optional[int],
    end_line: Optional[int],
    original_encoding: str,
    is_dfm_binary: bool,
) -> Dict[str, Any]:
    """
    部分写入：仅替换指定行范围的内容，其余部分保持不变。

    start_line/end_line 为 0-indexed 左闭右开区间：
      - 不传 start_line 时从第 0 行开始 (=文件第1行)
      - 不传 end_line 时到文件末尾

    左闭右开 [start_line, end_line) 的转换：
      Python 切片:  s = start_line (0-indexed inclusive start)
                    e = end_line   (0-indexed exclusive end)
       验证：lines[s:e] = lines[start_line : end_line] = 第 (start_line+1) 到 end_line 行  ✓

    ⚠️ 连续编辑的行号偏移：
      每次部分写入后文件行号会变化（增删行），输出中会包含偏移量信息：
        偏移量: +3（删5行, 插8行）
        后续编辑: 行号 ≥ {e} 的新行号 = 原行号 + 3；行号 < {s} 的不变
      AI Agent 应根据每次 write 返回的偏移量累加计算后续行号，
      而非直接使用上次 read 输出的原始行号。
    """
    read_path = file_path
    tmp_cleanup = None

    # 二进制 DFM → 文本
    if is_dfm_binary:
        tmp_dir = tempfile.mkdtemp(prefix="filetool_")
        text_path = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
        result = await dfm_utils.convert_dfm(file_path, text_path, to_text=True)
        if not result.get("success"):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return _wrap_error(f"二进制 DFM 转换失败: {result.get('message', '未知错误')}")
        read_path = text_path
        tmp_cleanup = tmp_dir

    try:
        # ── 1. 安全网：始终在 __history 创建备份
        #    成功→根据 backup 参数决定保留/删除；失败→从备份恢复
        bak_path = create_backup(file_path)

        enc = original_encoding or "utf-8"
        with open(read_path, 'r', encoding=enc, newline='',
                  buffering=1048576) as f:
            lines = f.readlines()

        total = len(lines)
        original_total = total  # 保存写入前的行数，用于 auto_format 后重新校正偏移量

        # 左闭右开 [start_line, end_line) → Python 切片
        # s = 0-indexed inclusive start = start_line
        # e = 0-indexed exclusive end = end_line
        s = start_line if start_line is not None else 0
        e = end_line if end_line is not None else total

        if s < 0:
            return _wrap_error(f"start_line ({start_line}) 不能小于 0")
        if e > total:
            return _wrap_error(f"end_line ({end_line}) 超出文件总行数 ({total})")
        if s >= e:
            return _wrap_error(f"替换范围为空: start_line ({start_line}) >= end_line ({end_line})。需满足 start_line < end_line")

        before = ''.join(lines[:s])
        after = ''.join(lines[e:])

        # 空内容 = 删除行：before + after 直接拼接
        # 非空内容 = 替换行：统一换行符后拼接
        if content == '':
            new_text = before + after
        else:
            # 检测原文件换行符风格：遍历 lines 列表而非拼接全文
            # 避免对大文件做 O(n) 全量字符串拷贝（''.join(lines) 会复制整个文件）
            has_crlf_in_original = any('\r\n' in line for line in lines)

            # 统一 content 换行符为原文件风格
            if has_crlf_in_original:
                content = content.replace('\r\n', '\n').replace('\n', '\r\n')
            else:
                content = content.replace('\r\n', '\n')

            # 确保 content 末尾有换行，避免替换区最后一行与后续行粘连。
            # readlines() 返回的每行都含换行符，替换区也必须保持一致。
            # 即使 after 为空（替换到 EOF），也应加上结尾换行保持文件规范。
            if not content.endswith('\n') and not content.endswith('\r\n'):
                line_ending = '\r\n' if has_crlf_in_original else '\n'
                content = content + line_ending

            new_text = before + content + after

        # ── 2. 写入（失败时从 __history 备份恢复） ──
        try:
            with open(file_path, 'w', encoding=enc, newline='',
                      buffering=1048576) as f:
                f.write(new_text)
        except (UnicodeEncodeError, OSError, IOError) as write_err:
            logger.warning(f"部分写入失败: {write_err}")

            # UnicodeEncodeError → 先试 UTF-8 回退
            if isinstance(write_err, UnicodeEncodeError):
                try:
                    with open(file_path, 'w', encoding="utf-8", newline='',
                              buffering=1048576) as f:
                        f.write(new_text)
                    enc = "utf-8"
                    logger.warning("编码回退到 utf-8 后写入成功")
                except (UnicodeEncodeError, OSError, IOError):
                    # 回退也失败 → 从备份恢复
                    if bak_path and os.path.exists(bak_path):
                        shutil.copy2(bak_path, file_path)
                    return _wrap_error(
                        f"文件写入失败，已从备份恢复: {write_err}"
                    )
            else:
                # OSError/IOError → 从备份恢复
                if bak_path and os.path.exists(bak_path):
                    shutil.copy2(bak_path, file_path)
                return _wrap_error(
                    f"文件写入失败，已从备份恢复: {write_err}"
                )

        # ── 3. 写入成功，根据 backup 参数决定备份的去留 ──
        if not backup and bak_path and os.path.exists(bak_path):
            try:
                os.remove(bak_path)
            except OSError:
                pass

        # DFM 二进制 → 转换回二进制
        if is_dfm_binary:
            text_tmp = file_path + ".txt"
            os.rename(file_path, text_tmp)
            try:
                conv_result = await dfm_utils.convert_dfm(text_tmp, file_path, to_text=False)
                if not conv_result.get("success"):
                    os.rename(text_tmp, file_path)
                    logger.warning(f"DFM 二进制转换失败，已保留文本: {conv_result.get('message')}")
                else:
                    os.remove(text_tmp)
            except Exception as ex:
                if os.path.exists(text_tmp):
                    os.rename(text_tmp, file_path)
                logger.warning(f"DFM 转换异常，已保留文本: {ex}")

        # 写入后自动格式化
        fmt_msg = ""
        if auto_format:
            try:
                fmt_result = await pasfmt.format_file(file_path=file_path, backup=False)
                if fmt_result.get("formatted"):
                    fmt_msg = "，写入后已格式化"
            except Exception as ex:
                logger.warning(f"写入后自动格式化失败: {ex}")

        # 计算偏移量：插入行数 - 删除行数，供 Agent 累加后续行号
        removed = e - s
        inserted = content.count('\n') if content else 0
        offset = inserted - removed

        # auto_format 可能额外改变行数（展开 uses、调整空行等），重新读取文件计算真实偏移
        fmt_adjustment = ""
        if auto_format and os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding=enc, newline='',
                          buffering=1048576) as f:
                    new_total = sum(1 for _ in f)
                if new_total != original_total:
                    real_offset = new_total - original_total
                    fmt_change = real_offset - offset
                    offset = real_offset
                    inserted += fmt_change
                    fmt_adjustment = f"（含格式化调整{fmt_change:+d}行）"
            except Exception as ex:
                logger.debug(f"auto_format 后重读行数失败: {ex}")

        offset_note = (
            f"偏移量: {offset:+d}（删{removed}行, 插{inserted}行{fmt_adjustment}）"
            if offset != 0
            else f"偏移量: 0（行数未变）"
        )

        range_desc = f"第 {s + 1}~{e} 行 (0-indexed [{s}, {e}), {e - s} 行)"
        result_lines = [
            f"文件已更新: {file_path}",
            f"替换范围: {range_desc}",
            f"{offset_note}",
            f"编码: {enc}",
        ]
        # 后续编辑行号调整公式:
        #   新行号 = 原行号 + 本偏移量   (当原行号 >= e 时)
        #   新行号 = 原行号               (当原行号 < s 时)
        #   原行号在 [s, e) 范围内 ⇒ 已被替换，不能再用
        hint = (
            f"后续编辑: 行号 ≥ {e} 的新行号 = 原行号 + {offset}；"
            f"行号 < {s} 的不变"
        )
        if offset != 0:
            result_lines.append(hint)
        if backup:
            result_lines.append(f"备份已创建: {bak_path}")
        if is_dfm_binary:
            result_lines.append("格式: 已转换为二进制 DFM")
        if fmt_msg:
            result_lines.append(fmt_msg)

        return {"status": "success", "message": "\n".join(result_lines)}

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
      - 支持 start_line/end_line 部分写入：仅替换指定行范围，其余不变

     行范围参数（0-indexed 左闭右开区间）:
       start_line=4, end_line=5  → 只替换第 5 行（0-indexed [4,5)）
       start_line=2, end_line=7  → 替换第 3~7 行（0-indexed [2,7)）
       start_line=4              → 从第 5 行替换到文件末尾
       end_line=10               → 从第 1 行替换到第 10 行（0-indexed [0,10)）
       
     ⚠️ 连续编辑注意事项:
       每次部分写入后文件行号会变化（增删行），输出中会返回偏移量：
         「后续编辑: 行号 ≥ X 的新行号 = 原行号 + N；行号 < X 的不变」
       发下一次 write 时，根据上次返回的偏移量累加计算新行号即可，
        不需要每次都 re-read。但如果偏移量累加后不确定，建议重新读取确认。
    """
    file_path = arguments.get("file_path")
    content = arguments.get("content")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    start_line = arguments.get("start_line")
    end_line = arguments.get("end_line")

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if content is None:
        return _wrap_error("请提供 content 参数")

    path_err = _validate_path(file_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

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

        # 部分写入: 指定行范围替换
        if start_line is not None or end_line is not None:
            return await _handle_partial_write(
                file_path=file_path,
                content=content,
                backup=backup,
                encoding=encoding,
                auto_format=auto_format,
                start_line=start_line,
                end_line=end_line,
                original_encoding=original_encoding,
                is_dfm_binary=is_dfm_binary,
            )

        if backup:
            backup_path = create_backup(file_path)
    else:
        if start_line is not None or end_line is not None:
            return _wrap_error("start_line/end_line 仅对已有文件有效，不能用于新建文件")
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
            with open(tmp_path, "w", encoding=write_encoding, newline='',
                      buffering=1048576) as f:
                f.write(content)
        except UnicodeEncodeError:
            logger.warning(f"编码 {write_encoding} 写出失败，回退到 utf-8")
            with open(tmp_path, "w", encoding="utf-8", newline='',
                      buffering=1048576) as f:
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
        if auto_format and _is_delphi_file(file_path):
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
            except OSError as e:
                logger.debug(f"清理临时DFM文件失败: {tmp_path}: {e}")


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
        path_err = _validate_path(file_path)
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
            result = await pasfmt.format_file(
                file_path=file_path,
                dry_run=True,
            )
        else:
            # 记录格式化前行数，用于计算偏移量
            before_lines = 0
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', newline='',
                              buffering=1048576) as f:
                        before_lines = sum(1 for _ in f)
                except OSError:
                    pass

            result = await pasfmt.format_file(
                file_path=file_path,
                config_path=arguments.get("config_path"),
                backup=backup_flag,
                in_place=True,
                uses_style=uses_style,
            )

            # 格式化成功且文件存在时，计算行数变化并附加到返回消息
            if result.get("status") == "success" and result.get("formatted") and os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', newline='',
                              buffering=1048576) as f:
                        after_lines = sum(1 for _ in f)
                    offset = after_lines - before_lines
                    if offset != 0:
                        offset_info = (
                            f"\n偏移量: {offset:+d}（格式化后行数变化）\n"
                            f"后续编辑: 行号 ≥ 0 的新行号 = 原行号 + {offset}"
                        )
                        if isinstance(result.get("message"), str):
                            result["message"] += offset_info
                except OSError:
                    pass

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

    path_err = _validate_path(file_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

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
# uses 子句操作
# ============================================================

# 匹配 uses 子句的正则：uses Unit1, Unit2; 可以跨多行
# 先剥离 Pascal 花括号注释 { ... }，避免注释内的 ; 干扰匹配
# 捕获组: (1)uses关键字 (2)整个单元列表 (3)分号
_USES_RE = re.compile(
    r'\b(uses)\b\s+(.*?)\s*(;)',
    re.DOTALL | re.IGNORECASE,
)

# 剥离 Pascal 花括号注释（含 $ 开头的条件编译指令）
_STRIP_BRACE_COMMENTS = re.compile(r'\{[^}]*\}', re.DOTALL)


def _find_uses_section(text: str, section: str) -> Optional[tuple]:
    """在指定区域(interface/implementation)查找 uses 子句。

    搜索前会剥离花括号注释，避免 { ... } 内的 ';' 干扰正则匹配。
    返回的偏移量基于原始 text（注释剥离后的偏移映射）。

    返回 (uses_start, uses_end, units_text) 元组，或 None。
    uses_start/uses_end 是基于原始 text 的偏移。
    """
    section_lower = section.lower()

    # 剥离花括号注释，同时构建原始偏移映射
    stripped = _STRIP_BRACE_COMMENTS.sub('', text)

    if section_lower == "interface":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        end = impl_pos.start() if impl_pos else len(stripped)
        header = re.search(r'\b(?:unit|program|library)\b', stripped[:end], re.IGNORECASE)
        start = header.end() if header else 0
        chunk = stripped[start:end]
        match = _USES_RE.search(chunk)
        if match:
            return (match.start() + start, match.end() + start, match.group(2))
        return None

    elif section_lower == "implementation":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        if not impl_pos:
            return None
        start = impl_pos.end()
        chunk = stripped[start:]
        match = _USES_RE.search(chunk)
        if match:
            return (match.start() + start, match.end() + start, match.group(2))
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

    path_err = _validate_path(file_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)
    if uses_action not in ("add", "remove"):
        return _wrap_error("uses_action 必须是 'add' 或 'remove'")

    if not os.path.isfile(file_path):
        return _wrap_error(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.pas', '.dpr', '.dpk', '.inc'):
        return _wrap_error(f"uses 操作仅支持 .pas/.dpr/.dpk/.inc 文件，不支持 {ext}")

    # 读取文件
    original_encoding = detect_encoding(file_path)
    with open(file_path, 'r', encoding=original_encoding, newline='',
              buffering=1048576) as f:
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

    # 备份
    backup_path = None
    backup = arguments.get("backup", True)
    if backup:
        backup_path = create_backup(file_path)

    # 写出
    try:
        with open(file_path, 'w', encoding=original_encoding, newline='',
                  buffering=1048576) as f:
            f.write(new_text)
    except UnicodeEncodeError:
        logger.warning(f"编码 {original_encoding} 写出失败，回退到 utf-8")
        with open(file_path, 'w', encoding="utf-8", newline='',
                  buffering=1048576) as f:
            f.write(new_text)
        original_encoding = "utf-8"

    # 自动格式化
    fmt_msg = ""
    if arguments.get("auto_format", False):
        try:
            fmt_result = await pasfmt.format_file(file_path=file_path, backup=False)
            if fmt_result.get("formatted"):
                fmt_msg = "，已格式化"
        except Exception as ex:
            logger.warning(f"uses 操作后格式化失败: {ex}")

    # 计算偏移量（uses 修改也会影响行号）
    s = text[:uses_start].count('\n')           # 0-indexed: uses 关键字所在行
    uses_old_text = text[uses_start:uses_end]
    removed = uses_old_text.count('\n')          # 旧 uses 子句占用的行数
    inserted = new_uses_clause.count('\n')       # 新 uses 子句占用的行数
    offset = inserted - removed
    # 计算 exclusive end: uses_end 所在行的下一行
    e = text[:uses_end].count('\n') + 1

    action_desc = "添加" if uses_action == "add" else "删除"
    result_lines = [
        f"已{action_desc}单元: {unit_name_stripped}",
        f"区域: {uses_section}",
        f"当前 uses: {', '.join(new_units)}",
        f"替换范围: 第 {s + 1}~{e} 行 (0-indexed [{s}, {e}), {removed} 行)",
    ]
    if offset != 0:
        result_lines.append(
            f"偏移量: {offset:+d}（删{removed}行, 插{inserted}行）"
        )
        result_lines.append(
            f"后续编辑: 行号 ≥ {e} 的新行号 = 原行号 + {offset}；行号 < {s} 的不变"
        )
    result_lines.append(f"编码: {original_encoding}")
    if backup_path:
        result_lines.append(f"备份: {backup_path}")
    if fmt_msg:
        result_lines.append(fmt_msg)

    return {"status": "success", "message": "\n".join(result_lines)}


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
    elif action == "uses":
        return await handle_uses(arguments)
    else:
        return _wrap_error(f"未知 action: {action}。支持的 action: read, write, format, backup, uses")
