"""
delphi_file — Delphi 文件专用操作工具（MCP 注册名 delphi_file，原 file_tool）

整合读取/写入/格式化/备份管理，覆盖 Delphi 文件操作完整生命周期。
MCP 客户端以 delphi_file 名注册，旧名 file_tool 仍作为别名兼容。

Action 模式:
  read        读取文件内容（继承 read_source_file，支持按路径/类名/函数名搜索）
  write       写入文件内容（自动备份到 __history，支持 DFM 透明转换）
  batch_write 批量写入（edits 数组，内部自动按 start_line 排序后依次替换，以备份文件为参照系）
  format      格式化 Delphi 源码（继承 format_delphi，pasfmt 驱动）
  backup      备份管理（创建/恢复/列表/对比）
  uses        增删 uses 子句中的单元（命名空间冲突检测 + 自动排序）

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
    """判断是否是 DFM/FMX 表单文件（Delphi VCL/FireMonkey 表单，可能为二进制或文本格式）"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.dfm', '.fmx'}


def _wrap_error(msg: str) -> Dict[str, Any]:
    """构造错误 dict"""
    return {"status": "failed", "message": msg}


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

    show_line_numbers: 为 True 时每行前面添加行号前缀（如 "     0: unit Unit1;"），
                       行号为 0-based 绝对行号（与 batch_write / write 的 start_line 直接对齐）。
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

                # show_line_numbers: 为每行添加 0-based 绝对行号前缀
                # 修复: 之前是 1-based, 导致 AI 用 read 看到的行号传给 batch_write 时
                # 必然错位 1 行 (1-based 第 N 行 = 0-based 第 N-1 行).
                # 现在 read 输出与 batch_write 接受的格式完全对齐: 看到 5 传 5, 看到 0 传 0.
                if show_line_numbers and selected:
                    line_offset = max(start_line, 0)  # 0-indexed start
                    numbered_lines = []
                    for i, line in enumerate(selected):
                        abs_lineno = line_offset + i      # 0-based 绝对行号 (与 batch_write 对齐)
                        numbered_lines.append(f"{abs_lineno:>6}: {line}")
                    text = ''.join(numbered_lines)

                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                actual_end_line = start_line + lines_shown  # 0-indexed exclusive end

                # 单行 meta: 编码 + 0-based 行号范围
                # 0-based 前缀已隐含「行号可直接用于 batch_write / write / format 的 start_line」,
                # 避免 AI 误用 1-based 导致错位 1 行 (历史最常见错误之一).
                # 无论 show_line_numbers 是否开启, 范围都展示, 让 AI 始终知道读到哪段.
                # 截断时仅追加 (truncated) 标记, 不重复暴露行数 (AI 用 start_line={actual_end_line} 续读即可).
                meta = f"# encoding: {enc}, 0-based [{start_line}, {actual_end_line})"
                if not reached_eof:
                    meta += " (truncated)"
                meta += "\n"

                return {"status": "success", "message": meta + text}
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
    preview: bool = False,
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
        # ── 1. 备份（预览模式跳过）
        bak_path = None
        if not preview:
            bak_path = create_backup(file_path)

        # 编码回退标志 (UnicodeEncodeError 时切到 utf-8, 用于输出提示)
        encoding_fallback = False

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

        # ── 预览模式：返回 diff 预览，不写盘 ──
        if preview:
            # 构建 per-edit diff 预览（模仿 batch_write 格式）
            old_lines = [lines[s + i].rstrip('\n\r') for i in range(e - s)]
            new_lines = content.splitlines(keepends=False) if content else []
            diff_lines = []
            for ol in old_lines:
                display = ol if len(ol) <= 80 else ol[:77] + "..."
                diff_lines.append(f"    - {display}")
            for nl in new_lines:
                display = nl if len(nl) <= 80 else nl[:77] + "..."
                diff_lines.append(f"    + {display}")
            removed = e - s
            inserted = len(new_lines) if content else 0
            delta = inserted - removed
            new_e = e + delta
            parts = [
                f"wrote: {os.path.basename(file_path)} (preview)",
                f"0-based [{s}, {e}) → [{s}, {new_e})",
                f"encoding: {enc}",
                "preview: true（未写入磁盘）",
            ]
            summary = [", ".join(parts), ""] + diff_lines
            return {"status": "success", "message": "\n".join(summary)}

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
                    encoding_fallback = True
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

        # 单行 meta (与 read 对齐):
        #   wrote: basename
        #   0-based [s, e) → [s, e+offset)   ← 隐含 offset (右端变化量)
        #   encoding: utf-8
        #   backup: __history\<basename>.~N~
        basename = os.path.basename(file_path)
        new_e = e + offset
        parts = [
            f"wrote: {basename}",
            f"0-based [{s}, {e}) → [{s}, {new_e})",
            f"encoding: {enc}",
        ]
        if backup and bak_path:
            parts.append(f"backup: __history\\{os.path.basename(bak_path)}")
        if is_dfm_binary:
            parts.append("format: binary DFM converted")
        if fmt_msg:
            parts.append("formatted: yes")
        if encoding_fallback:
            parts.append(f"⚠ fallback: {original_encoding or 'utf-8'} → utf-8")

        return {"status": "success", "message": ", ".join(parts)}

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

     preview: 可选，默认 false。设为 true 时只计算 diff 不写盘（不备份、不写入、不格式化）。
              全量写入 preview 返回文件大小变化；部分写入 preview 返回 diff 预览（- / + 行）。
    
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
    preview = arguments.get("preview", False)

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
                preview=preview,
            )

        if backup:
            backup_path = create_backup(file_path)
    else:
        if start_line is not None or end_line is not None:
            return _wrap_error("start_line/end_line 仅对已有文件有效，不能用于新建文件")
        if preview:
            return {"status": "success", "message":
                f"[preview] would create new file: {os.path.basename(file_path)}, "
                f"{len(content.encode('utf-8'))} bytes"}
        # 新文件默认 UTF-8 BOM（避免中文 Windows 下 Delphi/pasfmt 误判为 GBK）
        original_encoding = encoding if encoding != "auto" else "utf-8-sig"

    # 预览模式（全量写入）：读原文件，计算 diff 后返回
    if preview and file_exists:
        original_content = ""
        with open(file_path, 'r', encoding=original_encoding or 'utf-8',
                  buffering=1048576) as f:
            original_content = f.read()
        # 简单的 diff 预览：标记全文替换
        old_bytes = len(original_content.encode('utf-8'))
        new_bytes = len(content.encode('utf-8'))
        return {"status": "success", "message":
            f"[preview] would replace full file: {os.path.basename(file_path)}, "
            f"{old_bytes} bytes → {new_bytes} bytes"}
    
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

        # 单行 meta (与 read 对齐: wrote/encoding/backup, 全部 basename 不含完整路径)
        basename = os.path.basename(file_path)
        parts = [f"wrote: {basename}", f"encoding: {write_encoding}"]
        if encoding_fallback:
            parts.append(f"⚠ fallback: {original_encoding or 'utf-8'} → utf-8")
        if backup and file_exists and backup_path:
            parts.append(f"backup: __history\\{os.path.basename(backup_path)}")
        if is_dfm_binary:
            parts.append("format: binary DFM converted")
        if fmt_msg:
            parts.append("formatted: yes")

        return {"status": "success", "message": ", ".join(parts)}

    except Exception as e:
        logger.error(f"写入文件失败: {e}", exc_info=True)
        return _wrap_error(f"写入文件失败: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as e:
                logger.debug(f"清理临时DFM文件失败: {tmp_path}: {e}")


async def handle_batch_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 batch_write action — 批量写入。  # <-- reads once into memory, applies edits, writes once

    参数:
      file_path: 目标文件路径
      edits: 编辑列表，每个元素为 { start_line, end_line, content, description? }
      force: 可选，默认 false。设为 true 可跳过 AI 偏移量检查（检测到 content 首行与被替换行相同、
             或结果中出现连续重复行时报错），强制写入。
      preview: 可选，默认 false。设为 true 时只计算 diff 预览，不备份、不写盘、不格式化。

    设计:
      - edits 传入顺序不限，内部自动按 start_line 升序排列后从前往后依次替换
      - 先备份文件 → 读入内存 → 依次应用 edit（累计行号偏移） → 一次性写出磁盘
      - 所有 edit 的行号都以「备份文件」（原始内容）为参照系
      - 内部维护累计偏移量，逐 edit 调整 start_line/end_line，确保正确位置
      - AI 偏移量自动检测: 每 edit 检查 content 首行是否与被替换行相同（偏移错误）；
        全部 edit 应用后扫描连续重复行；检测到问题返回错误信息，除非 force=true

    edits 内元素说明（与 write action 的 start_line/end_line 语义完全一致）:
      start_line: 0-indexed inclusive start 行号（以原始文件为参照系）
      end_line:   0-indexed exclusive end 行号（不传则到文件末尾，以原始文件为参照系）
      content:    替换内容（空字符串=删除行）
      description: 可选的文字描述，仅用于返回消息中的标记
    """
    file_path = arguments.get("file_path")
    edits_raw = arguments.get("edits", [])
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    force = arguments.get("force", False)
    preview = arguments.get("preview", False)

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not edits_raw:
        return _wrap_error("请提供 edits 列表")
    if not isinstance(edits_raw, (list, tuple)):
        return _wrap_error("edits 必须是一个列表")

    path_err = _validate_path(file_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    if not os.path.isfile(file_path):
        return _wrap_error(f"文件不存在: {file_path}")

    # ── 检测文件编码 / DFM 状态 ──
    is_dfm_binary = False
    if _is_dfm_file(file_path):
        try:
            fmt = dfm_utils._detect_dfm_format(file_path)
            is_dfm_binary = (fmt == "binary")
        except (FileNotFoundError, PermissionError) as e:
            return _wrap_error(str(e))

    # 总是先检测文件实际编码；按 encoding 参数决定 read/write 编码
    detected_encoding = detect_encoding(file_path)
    if encoding == "auto":
        # 自动模式：保持原编码（read/write 都用 detected）
        read_enc = detected_encoding
        write_enc = detected_encoding
        encoding_transcoded = False
    else:
        # 用户显式指定 encoding：内部自动转码
        #   - read_enc  = detected_encoding (用文件实际编码解码，避免读到乱码)
        #   - write_enc = 用户指定 encoding  (按用户期望的目标编码写出)
        # 此设计同时支持:
        #   1. encoding 与 detected 一致 → 无转码，原样保留
        #   2. encoding 与 detected 不一致 → 内部透明转码 (UTF-8↔UTF-16LE/GBK)
        # 修复: 之前 "AI Agent 报告 UTF-16LE 内容被写入 UTF-8 文件" 的根因之一 —
        # 上游若错误指定 encoding, 旧逻辑会把内容按错误编码写入, 文件被静默改写。
        # 新逻辑下即使指定错误, 也只会触发转码而非乱码, 文件编码符合用户预期。
        read_enc = detected_encoding
        write_enc = encoding
        encoding_transcoded = not _is_encoding_compatible(encoding, detected_encoding)

    # ── 校验每个 edit 的合法性 ──
    validated_edits = []
    for i, edit in enumerate(edits_raw):
        if not isinstance(edit, dict):
            return _wrap_error(f"edits[{i}] 必须是 dict，实际类型 {type(edit).__name__}")
        s = edit.get("start_line")
        e = edit.get("end_line")
        c = edit.get("content")
        desc = edit.get("description", f"edit #{i}")
        if s is None:
            return _wrap_error(f"edits[{i}] ({desc}): 缺少必需的 start_line")
        if c is None:
            return _wrap_error(f"edits[{i}] ({desc}): 缺少必需的 content")
        if not isinstance(s, int):
            return _wrap_error(f"edits[{i}] ({desc}): start_line 必须是整数")
        if e is not None and not isinstance(e, int):
            return _wrap_error(f"edits[{i}] ({desc}): end_line 必须是整数")
        if e is not None and s >= e:
            return _wrap_error(f"edits[{i}] ({desc}): start_line ({s}) >= end_line ({e})，需满足 start_line < end_line")
        if s < 0:
            return _wrap_error(f"edits[{i}] ({desc}): start_line ({s}) 不能小于 0")
        validated_edits.append((s, e, c, desc))

    # ── 按 start_line 升序排列（以备份文件为参照系，从头往尾处理） ──
    validated_edits.sort(key=lambda x: x[0])

    # ── 重叠区间检测 ──
    # 排序后相邻两个 edit，前一个的 end_line 必须 ≤ 后一个的 start_line
    # 否则在原始文件参照系中区间重叠，偏移调整后无法正确映射
    for i in range(len(validated_edits) - 1):
        s1, e1, _, d1 = validated_edits[i]
        s2, _e2, _, d2 = validated_edits[i + 1]
        if e1 is None:
            return _wrap_error(
                f"edits 区间重叠: \"{d1}\" (start={s1}) 覆盖到文件末尾，"
                f"与 \"{d2}\" (start={s2}) 重叠"
            )
        if s2 < e1:
            return _wrap_error(
                f"edits 区间重叠: \"{d1}\" [{s1},{e1}) 与 \"{d2}\" [{s2},...) 重叠"
            )

    # ── 一次完整备份（预览模式跳过） ──
    bak_path = None
    if backup and not preview:
        bak_path = create_backup(file_path)

    # ── 读文件（二进制 DFM 需转文本） ──
    read_path = file_path
    tmp_cleanup = None
    if is_dfm_binary:
        tmp_dir = tempfile.mkdtemp(prefix="filetool_")
        text_path = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
        conv_result = await dfm_utils.convert_dfm(file_path, text_path, to_text=True)
        if not conv_result.get("success"):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return _wrap_error(f"二进制 DFM 转换失败: {conv_result.get('message', '未知错误')}")
        read_path = text_path
        tmp_cleanup = tmp_dir

    try:
        with open(read_path, 'r', encoding=read_enc, newline='', buffering=1048576) as f:
            lines = f.readlines()

        total = len(lines)
        original_lines = lines[:]  # 保存原始行，用于重复检测对比

        # ── 检测换行符风格 ──
        has_crlf = any('\r\n' in line for line in lines)

        # ── 依次应用每个 edit，维护累计偏移量 ──
        # 所有 edit 的行号以备份文件（原始 lines）为参照系
        # cumulative_offset = 当前 lines 相比原始 lines 的净行数变化
        cumulative_offset = 0
        results = []
        all_success = True

        for s, e, c, desc in validated_edits:
            adj_s = s + cumulative_offset
            adj_e = (e + cumulative_offset) if e is not None else len(lines)

            # 边界检查：adj_e 不能超出当前 lines
            if adj_s < 0 or adj_s > len(lines):
                results.append(f"  ❌ {desc}: start_line {s}（调整后 {adj_s}）超出当前范围 [0, {len(lines)}]")
                all_success = False
                continue
            if adj_e > len(lines):
                results.append(f"  ❌ {desc}: end_line {e}（调整后 {adj_e}）超出当前总行数 {len(lines)}")
                all_success = False
                continue
            if adj_s >= adj_e:
                results.append(f"  ❌ {desc}: 调整后范围为空 [{adj_s}, {adj_e})")
                all_success = False
                continue

            removed = adj_e - adj_s
            removed_lines_preview = []  # for diff preview (all branches)

            if c == '':
                # 删除行：直接移除
                if removed > 0 and removed <= 5:
                    removed_lines_preview = [lines[adj_s + i].rstrip('\n\r') for i in range(removed)]
                lines[adj_s:adj_e] = []
                inserted = 0
                c_lines = []
            else:
                # 统一换行符
                if has_crlf:
                    c = c.replace('\r\n', '\n').replace('\n', '\r\n')
                else:
                    c = c.replace('\r\n', '\n')
                if not c.endswith('\n') and not c.endswith('\r\n'):
                    c = c + ('\r\n' if has_crlf else '\n')

                c_lines = c.splitlines(keepends=True)
                inserted = len(c_lines)

                # ── AI 偏移检查（仅警告）: content 首行与被替换行内容相同 ──
                first_new = c_lines[0].rstrip('\n\r')
                first_old = ''
                if removed > 0 and adj_s < len(lines):
                    first_old = lines[adj_s].rstrip('\n\r')
                    if first_old and first_old == first_new:
                        results.append(
                            f"  ⚠️ {desc}: content 首行与将被替换的第 {s} 行内容相同，"
                            f"可能因偏移量错误造成重复（如需强制写入请设 force=true）"
                        )

                # 保存被替换的行用于 diff 预览（截断长行）
                if removed > 0 and removed <= 5:
                    removed_lines_preview = [lines[adj_s + i].rstrip('\n\r') for i in range(removed)]

                lines[adj_s:adj_e] = c_lines

            delta = inserted - removed
            cumulative_offset += delta

            # ── 记录原始参照系的行号 + delta，AI 可逐行核对 ──
            orig_e = e if e is not None else total
            results.append(
                f"  [{s}, {orig_e}) → [{s}, {orig_e + delta})  {desc}"
            )

            # ── Per-edit diff 预览（≤5 行时显示全量，超过则省略） ──
            # 这是早期预警：AI 通过对比 - / + 行可发现错位改写
            if removed_lines_preview:
                for rl in removed_lines_preview:
                    display = rl if len(rl) <= 80 else rl[:77] + "..."
                    results.append(f"    - {display}")
            if c_lines:
                # 同样截断
                max_show = min(len(c_lines), 5)
                for cl in c_lines[:max_show]:
                    display = cl.rstrip('\n\r')
                    display = display if len(display) <= 80 else display[:77] + "..."
                    results.append(f"    + {display}")
                if len(c_lines) > max_show:
                    results.append(f"    + ...（共 {len(c_lines)} 行）")

        # ── 一次性写出 ──
        new_text = ''.join(lines)

        # 记录是否发生过编码回退（与 handle_write 行为对齐：原编码无法编码时静默切到 UTF-8）
        encoding_fallback = False
        fmt_msg = ""

        # ── 累计偏移一致性自检（早期预警错位改写） ──
        # 编辑应用逻辑的不变量: len(lines) == total + cumulative_offset
        # 若不一致说明 batch_write 内部处理出现 bug（不是 AI 的问题），必须报警
        expected_total = total + cumulative_offset
        actual_total = len(lines)
        if actual_total != expected_total:
            results.append(
                f"  ❌ 内部错误: 编辑应用后行数 {actual_total} ≠ "
                f"原始 {total} + 累计偏移 {cumulative_offset} = {expected_total}，"
                f"请上报此问题"
            )
            all_success = False
            # 不中断, 继续尝试写出 (让用户能看到完整结果)

        # ── AI 偏移错误检测: 对比原始文件和结果中的连续重复行 ──
        if not force:
            # 收集原始文件中的连续重复（仅内容行，跳过空白）
            orig_dup_contents = set()
            for i in range(1, len(original_lines)):
                prev = original_lines[i - 1].rstrip('\n\r').strip()
                curr = original_lines[i].rstrip('\n\r').strip()
                if prev and curr and prev == curr:
                    orig_dup_contents.add(prev)

            # 扫描结果中的连续重复，排除原始已存在的重复
            new_dup_lines = []
            for i in range(1, len(lines)):
                prev = lines[i - 1].rstrip('\n\r').strip()
                curr = lines[i].rstrip('\n\r').strip()
                if prev and curr and prev == curr and prev not in orig_dup_contents:
                    new_dup_lines.append((i, prev))

            if new_dup_lines:
                dup_msgs = [f"    第 {i} 行: {txt}" for i, txt in new_dup_lines[:10]]
                if len(new_dup_lines) > 10:
                    dup_msgs.append(f"    ... 还有 {len(new_dup_lines) - 10} 处")
                # 清理临时备份
                if bak_path and os.path.exists(bak_path):
                    if not backup:
                        try:
                            os.remove(bak_path)
                        except OSError:
                            pass
                return _wrap_error(
                    "批量写入中止: 检测到连续重复行，可能因 AI 偏移量错误导致。\n"
                    f"共 {len(new_dup_lines)} 处新增重复：\n" + "\n".join(dup_msgs) + "\n"
                    "如需强制写入请设置 force=true"
                )

        # ── 预览模式：跳过磁盘写入 ──
        if preview:
            # diffs 已经记录在 results 中，直接进入汇总
            pass
        else:
            # DFM 二进制 → 转回二进制
            final_path = file_path
            if is_dfm_binary:
                text_tmp = file_path + ".txt"
                with open(text_tmp, 'w', encoding=write_enc, newline='', buffering=1048576) as f:
                    f.write(new_text)
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
            else:
                try:
                    with open(file_path, 'w', encoding=write_enc, newline='', buffering=1048576) as f:
                        f.write(new_text)
                except UnicodeEncodeError:
                    logger.warning(f"编码 {write_enc} 写出失败，回退到 utf-8")
                    with open(file_path, 'w', encoding="utf-8", newline='', buffering=1048576) as f:
                        f.write(new_text)
                    write_enc = "utf-8"
                    encoding_fallback = True

            # 写入后自动格式化
            fmt_msg = ""
            if auto_format and _is_delphi_file(file_path):
                try:
                    fmt_result = await pasfmt.format_file(file_path=file_path, backup=False)
                    if fmt_result.get("formatted"):
                        fmt_msg = "，写入后已格式化"
                except Exception as ex:
                    logger.warning(f"写入后自动格式化失败: {ex}")

            # 清理备份（如果不需保留）
            if not backup and bak_path and os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except OSError:
                    pass

        # ── 汇总 ──
        # 🧪 实验性功能: 批量写入在 AI 多次连续编辑时偏移量易错, 重复行检测可能误报
        #   已知问题:
        #     1. AI 误用 read 后的新行号 (而非原始文件行号) 触发 "连续重复行" 误报
        #     2. 累计偏移量在 edits 数量 ≥ 3 时计算复杂, 容易累积误差
        #     3. DFM 二进制 + batch_write 组合: 转换 → 文本 → 编辑 → 转回, 字节级可能漂移
        #   推荐: 每次 read → write 一次, 多轮独立操作更稳
        summary = ["🧪 batch_write is experimental, prefer action=write (one read+write per turn)"]
        basename = os.path.basename(file_path)
        action_label = "batch_preview" if preview else "batch_wrote"
        header_parts = [
            f"{action_label}: {len(validated_edits)} edits, {basename}",
            f"encoding: {write_enc}",
        ]
        if preview:
            header_parts.append("preview: true（未写入磁盘）")
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

        # 空行分隔 header 与 per-edit 详情
        summary.append(", ".join(header_parts))
        summary.append("")
        summary.extend(results)

        if all_success:
            return {"status": "success", "message": "\n".join(summary)}
        else:
            summary.insert(0, "部分 edit 执行失败，请检查上述结果")
            return {"status": "failed", "message": "\n".join(summary)}

    finally:
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
                    fmt_enc = detect_encoding(file_path)
                    with open(file_path, 'r', encoding=fmt_enc, newline='',
                              buffering=1048576) as f:
                        before_lines = sum(1 for _ in f)
                except (OSError, UnicodeDecodeError):
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
                    fmt_enc = detect_encoding(file_path)
                    with open(file_path, 'r', encoding=fmt_enc, newline='',
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
                except (OSError, UnicodeDecodeError):
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

    # 读取文件（始终用实际检测编码读取，避免乱码；写出按 encoding 参数决定）
    encoding = arguments.get("encoding", "auto")
    detected_enc = detect_encoding(file_path)
    if encoding == "auto":
        read_enc = detected_enc
        write_enc = detected_enc
    else:
        read_enc = detected_enc
        write_enc = encoding

    with open(file_path, 'r', encoding=read_enc, newline='',
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

    # 写出（用 write_enc 编码，与读取编码可能不同 = 透明转码）
    encoding_fallback = False
    try:
        with open(file_path, 'w', encoding=write_enc, newline='',
                  buffering=1048576) as f:
            f.write(new_text)
    except UnicodeEncodeError:
        logger.warning(f"编码 {write_enc} 写出失败，回退到 utf-8")
        with open(file_path, 'w', encoding="utf-8", newline='',
                  buffering=1048576) as f:
            f.write(new_text)
        write_enc = "utf-8"
        encoding_fallback = True

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

    action_desc = "added" if uses_action == "add" else "removed"
    # 单行 meta (与 read/write 对齐)
    basename = os.path.basename(file_path)
    new_e = e + offset
    parts = [
        f"wrote: {basename}",
        f"action: {action_desc} {unit_name_stripped} in {uses_section}",
        f"uses: {', '.join(new_units)}",
        f"0-based [{s}, {e}) → [{s}, {new_e})",
        f"encoding: {write_enc}",
    ]
    if backup_path:
        parts.append(f"backup: __history\\{os.path.basename(backup_path)}")
    if fmt_msg:
        parts.append("formatted: yes")
    if encoding_fallback:
        parts.append(f"⚠ fallback: {detected_enc} → utf-8")
    if write_enc != detected_enc and not encoding_fallback:
        parts.append(f"ℹ transcoded: {detected_enc} → {write_enc}")
    
    return {"status": "success", "message": ", ".join(parts)}


# ============================================================
# 主入口
# ============================================================

async def handle_file_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    file_tool 主入口。

    根据 action 参数路由到对应的处理函数:
      read        → handle_read
      write       → handle_write
      batch_write → handle_batch_write
      format      → handle_format
      backup      → handle_backup
      uses        → handle_uses
    """
    action = arguments.get("action", "read")

    if action == "read":
        return await handle_read(arguments)
    elif action == "write":
        return await handle_write(arguments)
    elif action == "batch_write":
        return await handle_batch_write(arguments)
    elif action == "format":
        return await handle_format(arguments)
    elif action == "backup":
        return await handle_backup(arguments)
    elif action == "uses":
        return await handle_uses(arguments)
    else:
        return _wrap_error(f"未知 action: {action}。支持的 action: read, write, batch_write, format, backup, uses")
