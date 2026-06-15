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
import threading
from typing import Any, Optional, Dict, List, Set
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


def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
    """校验文件路径安全性，返回 None 表示安全，否则返回错误信息

    Args:
        file_path: 待校验的文件路径
        project_path: 项目路径（.dproj/.dpr），用于 PathValidator 解析允许目录
    """
    # 基础校验
    if '\0' in file_path:
        return "路径包含 null 字节"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "路径解析失败: %s" % str(e)

    # 白名单式路径校验 (PathValidator)
    from src.utils.path_validator import get_path_validator
    validator = get_path_validator()
    validator.resolve(project_path)
    err = validator.validate(file_path)
    if err:
        return err

    # 保留原有系统敏感目录深度防御
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
    start_line: int = 1,
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

    start_line/end_line 为 1-indexed 左闭右闭区间：
      - start_line=1 表示从文件第 1 行开始
      - end_line 不传时等价于「读到 start_line + limit - 1 行为止」

    show_line_numbers: 为 True 时每行前面添加行号前缀（如 "     1: unit Unit1;"），
                       行号为 1-indexed 绝对行号。
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
                target_start = start_line
                target_end = end_line if end_line is not None else (start_line + limit - 1)
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

                # show_line_numbers: 为每行添加 1-indexed 绝对行号前缀
                if show_line_numbers and selected:
                    line_offset = start_line  # 1-indexed start
                    numbered_lines = []
                    for i, line in enumerate(selected):
                        lineno = line_offset + i  # 1-indexed 绝对行号
                        numbered_lines.append(f"{lineno:>6}: {line}")
                    text = ''.join(numbered_lines)

                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                actual_end_line = start_line + lines_shown - 1  # 1-indexed inclusive end

                # 单行 meta: 编码 + 1-indexed 行号范围
                # 所有行号都是 1-indexed，可直接用于 write 的 start_line/edits。
                # 截断时仅追加 (truncated) 标记。
                meta = f"# encoding: {enc}, 1-indexed [{start_line}, {actual_end_line}]"
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
    start_line: int = 1,
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
    start_line = arguments.get("start_line", 1)
    end_line = arguments.get("end_line")
    if end_line is not None:
        limit = min(end_line - start_line + 1, 1000)
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

    path_err = _validate_path(file_path, project_path)
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    # 读取清除脏标记：AI 重新读到了最新行号
    _clear_dirty(file_path)

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
        _release_read_lock(lock_file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)



# ── 文件级写入锁：防止对同一个文件并行写入 ──────────────────────────────
# 同一个文件同时被多个 agent write/batch_write 会导致内容错乱。
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
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            return
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
                "同一个文件的所有修改必须合并为一次 batch_write 完成，"
                "请重新 read 文件后规划全部 edits，用 batch_write 一次性写入。"
            )
        entry["writer"] = True
    return None


def _release_write_lock(file_path: str) -> None:
    """释放文件的写入许可"""
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            return
    with entry["lock"]:
        entry["writer"] = False


# ── 脏写入标记：防止 AI 未重读/预览就再次写入同一文件 ──────────────────
# 文件修改后（write/format/uses）行号变化，AI 必须 re-read 或 preview 确认后才能再次写入。
_dirty_files: Set[str] = set()
_dirty_lock = threading.Lock()


def _mark_dirty(file_path: str) -> None:
    """标记文件已修改，下次写入前需预览或重读。"""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.add(normalized)


def _clear_dirty(file_path: str) -> None:
    """清除脏标记（re-read 或 preview 后标记清除）。"""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.discard(normalized)


def _check_dirty(file_path: str, preview: bool = False) -> None:
    """
    检查文件是否脏（上次修改后未重读/预览）。
    如果 dirty 且不是 preview 模式，抛异常阻止写入。
    """
    if preview:
        _clear_dirty(file_path)
        return
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        if normalized in _dirty_files:
            raise RuntimeError(
                f"文件 {os.path.basename(normalized)} 上次写入后行号可能已变化。"
                "请先调用 read 获取最新行号，或使用 preview=true 预览本次修改。"
                "基于最新行号规划 edits 后重新发起 write。"
            )


async def handle_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 write action（合并原 write + batch_write）。

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
      - 支持 preview 预览 diff 不写盘

    行号均为 1-indexed 左闭右闭:
      edits=[{start_line:5, end_line:10}]  → 替换第 5~10 行
      edits=[{start_line:5}]               → 从第 5 行替换到文件末尾
      edits=[{end_line:10}]                → 从第 1 行替换到第 10 行

    ⚠️ 脏标记保护:
       每次写入（含 auto_format）后文件行号会变化。
       在重新 read 文件或 preview 确认前，不允许对同一文件再次写入，
       防止 AI 使用过期行号导致错位改写。
       续重行检测已降级为警告，不再阻断写入。
    """
    file_path = arguments.get("file_path")
    edits = arguments.get("edits")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    preview = arguments.get("preview", False)
    force = arguments.get("force", False)

    if not file_path:
        return _wrap_error("请提供 file_path 参数")
    if not edits:
        return _wrap_error("请提供 edits 参数（全量替换: [{start_line:1, content:'...'}]）")

    # ── 脏标记检查 ──
    try:
        _check_dirty(file_path, preview=preview)
    except RuntimeError as e:
        return _wrap_error(str(e))

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("路径安全校验失败: %s" % path_err)

    return await _handle_batch_write_internal(
        file_path=file_path,
        edits=edits,
        backup=backup,
        encoding=encoding,
        auto_format=auto_format,
        preview=preview,
        force=force,
    )


async def _handle_batch_write_internal(
    file_path: str,
    edits: List[Dict],
    backup: bool = True,
    encoding: str = "auto",
    auto_format: bool = False,
    preview: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    批量写入内部实现（edits 数组，以原始文件为参照系）。

    edits 元素:
      start_line: 1-indexed inclusive（替换起始行）
      end_line:   1-indexed inclusive（替换结束行，不传则到文件末尾）
      content:    替换内容（空字符串=删除行）
      description: 描述（可选）

    force: true 时跳过续重行检测（默认 false 时检测到重复仅警告不阻断写入）。
    """
    if not edits:
        return _wrap_error("请提供 edits 列表")
    if not isinstance(edits, (list, tuple)):
        return _wrap_error("edits 必须是一个列表")

    file_exists = os.path.isfile(file_path)
    if not file_exists:
        # 新文件：必须只有 1 个 edit，start_line=1
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
            return {"status": "success", "message":
                f"[preview] would create new file: {os.path.basename(file_path)}, "
                f"{len(content.encode('utf-8'))} bytes"}

        # 写入新文件
        try:
            with open(file_path, 'w', encoding=original_encoding, newline='',
                      buffering=1048576) as f:
                f.write(content)
        except Exception as e:
            return _wrap_error(f"创建文件失败: {e}")

        _mark_dirty(file_path)
        return {"status": "success", "message":
            f"wrote: {os.path.basename(file_path)}, encoding: {original_encoding}"}

    # ── 已有文件：批量编辑 ──
    # ── 检测文件编码 / DFM 状态 ──
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
        write_enc = encoding
        encoding_transcoded = not _is_encoding_compatible(encoding, detected_encoding)

    # ── 校验每个 edit 并转换为内部 0-indexed ──
    validated_edits = []
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return _wrap_error(f"edits[{i}] 必须是 dict")
        s_1 = edit.get("start_line")  # 1-indexed
        e_1 = edit.get("end_line")    # 1-indexed inclusive
        c = edit.get("content")
        desc = edit.get("description", f"edit #{i}")
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

        # 转换为内部 0-indexed
        s_0 = s_1 - 1
        e_0 = e_1  # 1-indexed inclusive = 0-indexed exclusive
        validated_edits.append((s_0, e_0, c, desc, s_1, e_1))

    # ── 按 start_line 升序排列 ──
    validated_edits.sort(key=lambda x: x[0])

    # ── 重叠区间检测（内部 0-indexed） ──
    for i in range(len(validated_edits) - 1):
        s0_1, e0_1, _, _, _, _ = validated_edits[i]
        s1_0, _, _, _, _, _ = validated_edits[i + 1]
        if e0_1 is None:
            return _wrap_error(
                f"edits 区间重叠: \"{validated_edits[i][3]}\" (start={validated_edits[i][4]}) 覆盖到文件末尾，"
                f"与 \"{validated_edits[i+1][3]}\" (start={validated_edits[i+1][4]}) 重叠"
            )
        if s1_0 < e0_1:
            return _wrap_error(
                f"edits 区间重叠: \"{validated_edits[i][3]}\" [{validated_edits[i][4]},{validated_edits[i][5]}] "
                f"与 \"{validated_edits[i+1][3]}\" [{validated_edits[i+1][4]},...) 重叠"
            )

    # ── 备份 ──
    bak_path = None
    if backup and not preview:
        bak_path = create_backup(file_path)

    # ── 加锁 ──
    if preview:
        lock_err = _acquire_read_lock(file_path)
    else:
        lock_err = _acquire_write_lock(file_path)
    if lock_err:
        if bak_path and os.path.exists(bak_path):
            try:
                os.remove(bak_path)
            except OSError:
                pass
        return _wrap_error(lock_err)

    read_path = file_path
    tmp_cleanup = None
    try:
        # ── 读文件 ──
        if is_dfm_binary:
            tmp_dir = tempfile.mkdtemp(prefix="filetool_")
            text_path = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
            conv_result = await dfm_utils.convert_dfm(file_path, text_path, to_text=True)
            if not conv_result.get("success"):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return _wrap_error(f"二进制 DFM 转换失败: {conv_result.get('message', '未知错误')}")
            read_path = text_path
            tmp_cleanup = tmp_dir
        with open(read_path, 'r', encoding=read_enc, newline='', buffering=1048576) as f:
            lines = f.readlines()

        total = len(lines)
        original_lines = lines[:]

        has_crlf = any('\r\n' in line for line in lines)

        cumulative_offset = 0
        results = []
        all_success = True

        for s_0, e_0, c, desc, s_1, e_1 in validated_edits:
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

            removed = adj_e - adj_s
            removed_lines_preview = []

            before_len = len(lines)  # 编辑前行数（含此前 edits 累计）
            if c == '':
                if removed > 0 and removed <= 5:
                    removed_lines_preview = [(s_1 + i, lines[adj_s + i].rstrip('\n\r')) for i in range(removed)]
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

                # AI 偏移检查：s_1 > 1 时检查（非文件头替换）
                if s_1 > 1 and removed > 0 and adj_s < len(lines):
                    first_new = c_lines[0].rstrip('\n\r')
                    first_old = lines[adj_s].rstrip('\n\r')
                    if first_old and first_old == first_new:
                        results.append(
                            f"  ⚠️ {desc}: content 首行与将被替换的第 {s_1} 行内容相同，"
                            f"可能因偏移量错误造成重复（如需强制写入请设 force=true）"
                        )

                if removed > 0 and removed <= 5:
                    removed_lines_preview = [(s_1 + i, lines[adj_s + i].rstrip('\n\r')) for i in range(removed)]

                lines[adj_s:adj_e] = c_lines

            delta = inserted - removed
            cumulative_offset += delta

            orig_e_display = e_1 if e_1 is not None else before_len
            results.append(
                f"  [{s_1}, {orig_e_display}] → [{s_1}, {orig_e_display + delta}] (offset: {delta:+d})  {desc}"
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
                    new_dup_lines.append((i, prev))

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
            if auto_format and _is_delphi_file(file_path):
                try:
                    fmt_result = await pasfmt.format_file(file_path=file_path, backup=False)
                    if fmt_result.get("formatted"):
                        fmt_msg = "，写入后已格式化"
                except Exception as ex:
                    logger.warning(f"写入后自动格式化失败: {ex}")

            # auto_format 可能额外改变行数（展开 uses、调整空行等），重算真实偏移
            fmt_diff = 0
            if auto_format and not preview and os.path.isfile(file_path) and fmt_msg:
                try:
                    with open(file_path, 'r', encoding=write_enc, newline='',
                              buffering=1048576) as f:
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

            # 清理备份
            if not backup and bak_path and os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except OSError:
                    pass

            # 标记脏
            _mark_dirty(file_path)

        # 汇总输出
        summary = []
        basename = os.path.basename(file_path)
        action_label = "preview" if preview else "wrote"
        header_parts = [
            f"{action_label}: {len(validated_edits)} edits, {basename}",
            f"encoding: {write_enc}",
        ]
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
            return {"status": "success", "message": "\n".join(summary)}
        else:
            summary.insert(0, "部分 edit 执行失败，请检查上述结果")
            return {"status": "failed", "message": "\n".join(summary)}

    finally:
        if preview:
            _release_read_lock(file_path)
        else:
            _release_write_lock(file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)


async def handle_batch_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 batch_write action（已弃用，请使用 write action + edits 参数代替）。

    此函数保留以兼容旧调用，内部委托给 handle_write。
    """
    # 转换参数：batch_write 的 edits 和 force 映射到 write
    args = {
        "file_path": arguments.get("file_path"),
        "edits": arguments.get("edits", []),
        "backup": arguments.get("backup", True),
        "encoding": arguments.get("encoding", "auto"),
        "auto_format": arguments.get("auto_format", False),
        "preview": arguments.get("preview", False),
        "force": arguments.get("force", False),
    }
    return await handle_write(args)


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
            lock_err = _acquire_write_lock(file_path)
            if lock_err:
                return _wrap_error(lock_err)
            try:
                result = await pasfmt.format_file(
                    file_path=file_path,
                    config_path=arguments.get("config_path"),
                    backup=backup_flag,
                    in_place=True,
                    uses_style=uses_style,
                )

                # 格式化成功 → 标记脏（行号已变，强制 re-read）
                # ⚠ 不计算偏移量：pasfmt 可能重构代码结构（展开 uses、调整 begin/end 等），
                #   格式化前后的行号无线性对应关系。AI 须通过 dirty flag 触发 re-read。 
                if result.get("status") == "success" and result.get("formatted"):
                    _mark_dirty(file_path)
            finally:
                _release_write_lock(file_path)

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

async def handle_file_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    file_tool 主入口。
    write 和 batch_write 已合并，batch_write 保留为别名。
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
        return _wrap_error(f"未知 action: {action}。支持的 action: read, write(format=批量替换), format, backup, uses")
