"""Lazarus/FPC 插件工具 handlers — 独立于插件实例的纯函数。

遵循 Delphi 插件 handlers.py 模式:
  1. 每个 handler 接受 (arguments: dict) → 返回 Any (dict / CallToolResult)
  2. 导出 LAZARUS_HANDLERS / LAZARUS_TOOL_DESCRIPTIONS / LAZARUS_TOOL_SCHEMAS
  3. handler 内部延迟导入 CompilerService / LpiParser，避免模块级依赖
"""

from typing import Any, List

from src.utils.logger import init_default_logger

logger = init_default_logger()


# ============================================================
# 工具 handler 函数
# ============================================================

async def _handle_lazarus_compile(arguments: dict) -> dict:
    """编译 Lazarus/Free Pascal 项目 (.lpi / .lpr)

    Arguments:
        project_path (str): .lpi 或 .lpr 文件路径 (必需)
        target_platform (str, optional): win32 / win64，默认 win32
        build_configuration (str, optional): Default / Release / Debug
        timeout (int, optional): 超时秒数，默认 600
        run_verify (bool, optional): 编译成功后启动程序 3 秒验证是否崩溃，默认 false
    """
    from src.services.compiler_service import CompilerService
    from src.services.config_manager import ConfigManager
    from src.models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "缺少必需参数: project_path"}

    platform_map = {
        "win32": TargetPlatform.WIN32,
        "win64": TargetPlatform.WIN64,
    }
    target = platform_map.get(
        arguments.get("target_platform", "win32").lower(),
        TargetPlatform.WIN32,
    )
    build_config = arguments.get("build_configuration")
    timeout = int(arguments.get("timeout", 600))
    run_verify = arguments.get("run_verify", False)

    compile_opts = CompileOptions(
        target_platform=target,
        build_configuration=build_config,
        timeout=timeout,
    )
    request = ProjectCompileRequest(
        project_path=project_path,
        options=compile_opts,
    )

    cm = ConfigManager()
    cs = CompilerService(cm)
    try:
        result = await cs.compile_with_lazbuild(request)
        result_dict = result.to_dict()

        # ── 运行验证 ──
        if run_verify and result.status.value == "success":
            verify_info = await _run_lazarus_verify(
                cs, request, project_path, target, build_config
            )
            result_dict["_verify"] = verify_info

        return result_dict
    except Exception as e:
        logger.error(f"lazarus_compile 失败: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": f"编译失败: {e}",
            "project_path": project_path,
        }


# ============================================================
# run_verify 辅助函数
# ============================================================

def _get_verify_tools_dir() -> Path:
    """获取 StackTrace 工具目录"""
    from pathlib import Path
    return Path(__file__).resolve().parents[3] / "tools" / "stacktrace"


def _inject_lazarus_verify_units(lpi_path: str, lpr_path: str) -> dict:
    """修改 .lpi + .lpr 注入 StackTraceFPC 验证单元，返回备份路径。

    注入内容 (.lpi):
       1. 添加 StackTraceFPC 到 Uses 部分
       2. 添加 tools/stacktrace 到搜索路径
       3. 启用调试信息 (-gl -gw)

    注入内容 (.lpr):
       1. uses 子句追加 StackTraceFPC
       2. begin 块后插入 TStackTraceManagerFPC.Initialize 调用

    Args:
        lpi_path: .lpi 文件路径
        lpr_path: .lpr 文件路径

    Returns:
        dict with backup paths
    """
    import shutil
    import re
    from pathlib import Path

    lpi = Path(lpi_path)
    lpr = Path(lpr_path)
    tools_dir = _get_verify_tools_dir()

    backs = {
        '.lpi': lpi.with_suffix('.lpi.verify_bak'),
        '.lpr': lpr.with_suffix('.lpr.verify_bak'),
    }

    # 备份
    shutil.copy2(str(lpi), str(backs['.lpi']))
    if lpr.exists():
        shutil.copy2(str(lpr), str(backs['.lpr']))

    # ── 修改 .lpi ──
    content = lpi.read_text(encoding="utf-8-sig")

    # 添加 StackTraceFPC 到 Uses
    rel_stacktrace = tools_dir.name + '/Fpc.StackTrace.pas'
    if 'Fpc_StackTrace' not in content:
        # 查找 <Units> 节点并添加
        units_pattern = r'(<Units>)'
        inject_unit = (
            f'    <Unit Filename="{rel_stacktrace}">\n'
            f'      <IsPartOfProject Value="False"/>\n'
            f'    </Unit>'
        )
        if re.search(units_pattern, content):
            content = re.sub(
                units_pattern,
                lambda m: m.group(1) + '\n' + inject_unit,
                content
            )
        else:
            # 如果没有 <Units>，添加到 <CompilerOptions> 前
            content = content.replace(
                '<CompilerOptions>',
                '<Units>\n' + inject_unit + '\n  </Units>\n  <CompilerOptions>'
            )

    # 添加搜索路径
    rel_path = tools_dir.name
    paths_pattern = r'(<OtherUnitFiles[^>]*Value=")(.*?)(")'
    if re.search(paths_pattern, content):
        content = re.sub(
            paths_pattern,
            lambda m: m.group(1) + m.group(2) + (';' if m.group(2).strip() else '') + rel_path + m.group(3),
            content
        )
    else:
        # 添加 OtherUnitFiles
        content = content.replace(
            '</CompilerOptions>',
            '    <OtherUnitFiles Value="' + rel_path + '"/>\n  </CompilerOptions>'
        )

    # 启用调试信息 (-gl -gw)
    if '-gl' not in content:
        content = content.replace(
            '</CompilerOptions>',
            '    <CustomOptions Value="-gl -gw"/>\n  </CompilerOptions>'
        )

    lpi.write_text(content, encoding="utf-8-sig")
    logger.info("已注入 StackTraceFPC 单元到 .lpi: %s", lpi_path)

    # ── 修改 .lpr ──
    if lpr.exists():
        original = lpr.read_text(encoding='utf-8-sig')
        if 'Fpc_StackTrace' not in original:
            # 在 uses 中追加
            uses_pos = original.lower().find('uses')
            if uses_pos >= 0:
                end_uses = original.find(';', uses_pos + 4)
                if end_uses > uses_pos:
                    uses_section = original[uses_pos:end_uses]
                    if 'Fpc_StackTrace' not in uses_section:
                        original = original[:end_uses] + ', Fpc_StackTrace' + original[end_uses:]

            # 在 begin 后添加初始化
            lines = original.split('\n')
            begin_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == 'begin':
                    begin_idx = i
                    break

            if begin_idx >= 0:
                inject_lines = [
                    '{STACKTRACE_INJECT}',
                    '  TStackTraceManagerFPC.Initialize;',
                ]
                for j, line in enumerate(inject_lines):
                    lines.insert(begin_idx + 1 + j, line)

                lpr.write_text('\n'.join(lines), encoding='utf-8-sig')
                logger.info("已注入 Fpc_StackTrace 初始化到 .lpr: %s", lpr_path)

    return backs


def _restore_lazarus_files(lpi_path: str, lpr_path: str, backs: dict):
    """恢复备份的 .lpi 和 .lpr 文件"""
    import shutil
    from pathlib import Path

    lpi = Path(lpi_path)
    lpr = Path(lpr_path)

    if backs.get('.lpi') and backs['.lpi'].exists():
        shutil.copy2(str(backs['.lpi']), str(lpi))
        backs['.lpi'].unlink()
        logger.info("已恢复 .lpi: %s", lpi_path)

    if backs.get('.lpr') and backs['.lpr'].exists():
        shutil.copy2(str(backs['.lpr']), str(lpr))
        backs['.lpr'].unlink()
        logger.info("已恢复 .lpr: %s", lpr_path)


async def _run_lazarus_verify(
    cs: 'CompilerService',
    request: 'ProjectCompileRequest',
    project_path: str,
    target_platform: 'TargetPlatform',
    build_configuration: str
) -> dict:
    """运行 Lazarus 项目的运行验证

    1. 注入 StackTraceFPC 单元
    2. 重新编译
    3. 运行 exe 3 秒
    4. 检查 exception.log
    """
    import asyncio
    from pathlib import Path

    TIMEOUT_PROCESS_TERMINATE = 3.5  # 秒

    try:
        lpi_path = Path(project_path)
        lpr_path = lpi_path.with_suffix('.lpr')
        if not lpr_path.exists():
            # 尝试从 .lpi 获取主源文件
            from src.utils.lpi_parser import LpiParser
            parser = LpiParser(str(lpi_path))
            if parser.parse():
                main_src = parser.get_project_info().get('main_source', '')
                if main_src:
                    lpr_path = lpi_path.parent / main_src

        if not lpr_path.exists():
            return {"error": "未找到 .lpr 主源文件"}

        # 1. 注入 StackTraceFPC
        backs = _inject_lazarus_verify_units(str(lpi_path), str(lpr_path))

        try:
            # 2. 重新编译
            verify_result = await cs.compile_with_lazbuild(request)

            if verify_result.status.value != "success":
                err_detail = verify_result.log or verify_result.error_message or "(no log)"
                logger.warning("注入 StackTraceFPC 后编译失败: %s", err_detail[:500])
                return {"error": "injected compile failed", "log": err_detail[:1000]}

            # 3. 查找 exe 路径
            # Lazarus 输出路径通常在 output 目录
            exe_name = lpr_path.stem + '.exe'
            output_dir = lpi_path.parent / 'bin'
            if not output_dir.exists():
                output_dir = lpi_path.parent
            exe_path = output_dir / exe_name

            if not exe_path.exists():
                return {"error": f"未找到输出文件: {exe_path}"}

            # 4. 运行验证
            exe_dir = exe_path.parent
            log_path = exe_dir / 'exception.log'
            if log_path.exists():
                try:
                    log_path.unlink()
                except Exception as e:
                    logger.debug("清理 exception.log 失败: %s", e)

            import subprocess
            proc = subprocess.Popen([str(exe_path)], cwd=str(exe_dir))
            try:
                proc.wait(timeout=TIMEOUT_PROCESS_TERMINATE)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            # 5. 检查 exception.log
            if log_path.exists():
                try:
                    from src.utils.detect_encoding import detect_encoding
                    enc = detect_encoding(str(log_path))
                    log_content = log_path.read_text(encoding=enc, errors='replace')
                    logger.warning("运行时异常: %s", log_content[:200])
                    return {"error": "runtime exception", "log": log_content}
                except Exception as read_err:
                    return {"error": "runtime exception", "read_error": str(read_err)}
            else:
                logger.info("运行验证通过")
                return {"passed": True}

        finally:
            # 恢复原始文件
            _restore_lazarus_files(str(lpi_path), str(lpr_path), backs)

    except Exception as e:
        logger.warning("运行验证异常: %s", e, exc_info=True)
        return {"error": str(e)}


async def _handle_lazarus_project(arguments: dict) -> dict:
    """获取 Lazarus 项目信息

    解析 .lpi 文件，返回项目名称、主源文件、单元列表、编译器选项。

    Arguments:
        project_path (str): .lpi 或 .lpr 文件路径 (必需)
        action (str, optional): info / units / options，默认 info
    """
    from src.utils.lpi_parser import LpiParser

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "缺少必需参数: project_path"}

    # .lpr → 查找同名 .lpi
    from pathlib import Path
    p = Path(project_path)
    lpi_path = project_path
    if p.suffix.lower() == ".lpr":
        candidate = p.with_suffix(".lpi")
        if candidate.exists():
            lpi_path = str(candidate)
        else:
            return {
                "status": "failed",
                "error": f"未找到与 {project_path} 对应的 .lpi 文件",
            }

    parser = LpiParser(lpi_path)
    if not parser.parse():
        return {
            "status": "failed",
            "error": f"解析 .lpi 文件失败: {lpi_path}",
        }

    action = arguments.get("action", "info")

    if action == "units":
        return {
            "status": "success",
            "project_path": lpi_path,
            "units": parser.get_units(),
        }

    if action == "options":
        return {
            "status": "success",
            "project_path": lpi_path,
            "compiler_options": parser.get_compiler_options(),
        }

    # 默认 info
    info = parser.get_project_info()
    return {
        "status": "success",
        "project_path": lpi_path,
        "name": info.get("project_name", ""),
        "main_source": info.get("main_source", ""),
        "unit_count": info.get("unit_count", 0),
        "search_paths": parser.get_unit_search_paths(),
        "compiler_options": parser.get_compiler_options(),
    }


async def _handle_lazarus_kb(arguments: dict) -> dict:
    """Lazarus/FPC 源码知识库

    索引和搜索 Lazarus LCL / FPC RTL 源码。使用独立的 ZVec 知识库
    存储在 data/lazarus-knowledge-base/。

    Actions:
        build:   扫描 Lazarus 安装目录索引源码
        search:  搜索已索引的源码（返回符号定义和用法）
        stats:   知识库统计信息
        read:    读取源码文件内容
    """
    from pathlib import Path

    action = arguments.get("action", "search")

    # 独立 KB 路径
    server_root = Path(__file__).resolve().parents[3]
    kb_dir = str(server_root / "data" / "lazarus-knowledge-base")

    # ── 自动检测 Lazarus 源码目录 ──
    def _detect_source_dirs() -> List[dict]:
        from .detect import find_lazarus_source_dirs
        return find_lazarus_source_dirs()

    # ── build ──
    if action == "build":
        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )

        sources = _detect_source_dirs()
        if not sources:
            return {
                "status": "failed",
                "error": "未检测到 Lazarus/FPC 安装目录。请确认 Lazarus 安装在 C:\\lazarus",
            }

        Path(kb_dir).mkdir(parents=True, exist_ok=True)
        scanner = GenericDocumentScanner(kb_dir)

        results = []
        total_files = 0
        for src in sources:
            try:
                result = scanner.scan_directory(
                    directory=src["path"],
                    extensions=[".pas", ".inc", ".pp", ".lpr", ".lpi"],
                )
                total_files += result.get("total_files", 0)
                results.append({
                    "source": src["label"],
                    "path": src["path"],
                    "files": result.get("total_files", 0),
                    "processed": result.get("processed", 0),
                    "failed": result.get("failed", 0),
                })
            except Exception as e:
                logger.warning(f"扫描 {src['label']} 失败: {e}")
                results.append({
                    "source": src["label"],
                    "path": src["path"],
                    "error": str(e),
                })

        stats = scanner.get_statistics()
        return {
            "status": "success",
            "action": "build",
            "sources": results,
            "total_files_scanned": total_files,
            "indexed_documents": stats.get("total_documents", 0),
            "kb_path": kb_dir,
        }

    # ── search ──
    if action == "search":
        query = arguments.get("query", "")
        if not query:
            return {"status": "failed", "error": "缺少必需参数: query"}

        top_k = min(int(arguments.get("top_k", 20)), 100)
        content_type = arguments.get("content_type")  # optional filter

        kb_path = Path(kb_dir)
        if not kb_path.is_dir() or not any(kb_path.iterdir()):
            return {
                "status": "failed",
                "error": "Lazarus 知识库为空，请先执行 lazarus_kb(action=build)",
            }

        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )
        scanner = GenericDocumentScanner(kb_dir)
        results = scanner.search(query, content_type=content_type, top_k=top_k)

        if not results:
            return {
                "status": "success",
                "action": "search",
                "query": query,
                "count": 0,
                "results": [],
                "message": f"未找到匹配 '{query}' 的文档",
            }

        output = []
        for doc in results:
            entry = {
                "id": doc.get("id"),
                "title": doc.get("title", "N/A"),
                "type": doc.get("content_type", "N/A"),
                "path": doc.get("path", doc.get("url", "")),
                "size": doc.get("size", 0),
            }
            content = doc.get("content", "")
            if content:
                entry["preview"] = content[:300]
            output.append(entry)

        return {
            "status": "success",
            "action": "search",
            "query": query,
            "count": len(output),
            "results": output,
        }

    # ── read ──
    if action == "read":
        file_path = arguments.get("file_path")
        if not file_path:
            return {"status": "failed", "error": "需要 file_path 参数"}

        p = Path(file_path)
        if not p.exists():
            return {"status": "failed", "error": f"文件不存在: {file_path}"}
        try:
            # BOM 自动检测：优先 UTF-8 BOM，fallback UTF-8
            raw = p.read_bytes()
            if raw[:3] == b'\xef\xbb\xbf':
                text = raw[3:].decode('utf-8')
            elif raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                text = raw.decode('utf-16')
            else:
                text = raw.decode('utf-8')
            return {
                "status": "success",
                "action": "read",
                "file_path": file_path,
                "content": text,
                "size": len(text),
                "encoding": "utf-8",
            }
        except UnicodeDecodeError:
            # Fallback: 系统默认编码
            try:
                text = p.read_text(encoding="ansi")
                return {
                    "status": "success",
                    "action": "read",
                    "file_path": file_path,
                    "content": text,
                    "size": len(text),
                    "encoding": "ansi",
                }
            except Exception as e2:
                return {"status": "failed", "error": f"无法解码文件（尝试了 UTF-8/UTF-16/ANSI）: {e2}"}
        except Exception as e:
            return {"status": "failed", "error": f"读取文件失败: {e}"}

    # ── stats ──
    if action == "stats":
        kb_path = Path(kb_dir)
        if not kb_path.is_dir():
            return {
                "status": "success",
                "action": "stats",
                "total_documents": 0,
                "sources_available": _detect_source_dirs(),
                "message": "知识库尚未构建。请执行 lazarus_kb(action=build)",
            }

        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )
        scanner = GenericDocumentScanner(kb_dir)
        stats = scanner.get_statistics()

        return {
            "status": "success",
            "action": "stats",
            "kb_path": kb_dir,
            "total_documents": stats.get("total_documents", 0),
            "by_type": stats.get("by_type", {}),
            "by_language": stats.get("by_language", {}),
            "sources_available": _detect_source_dirs(),
        }

    return {"status": "failed", "error": f"未知 action: {action}"}


async def _handle_lazarus_file(arguments: dict) -> dict:
    """Lazarus/FPC 文件读写工具（只读/写/备份，复用共享文件内核）

    Actions:
        read:    读取文件（BOM 自动检测）
        write:   写入文件（edits=[...] 批量修改，自动备份到 __history）
        backup:  手动创建备份到 __history

    限制 action 范围，禁止 delphi_file 特有的 DFM/pasfmt/uses/grep 等操作。
    """
    from src.tools.file_tool import handle_file_tool

    allowed = {"read", "write", "backup"}
    action = arguments.get("action", "read")
    if action not in allowed:
        return {
            "status": "failed",
            "error": f"lazarus_file 不支持 action='{action}'。支持: {', '.join(sorted(allowed))}",
        }

    return await handle_file_tool(arguments)


# ============================================================
# 导出：工具名 → handler 映射
# ============================================================

LAZARUS_HANDLERS: dict[str, Any] = {
    "lazarus_compile": _handle_lazarus_compile,
    "lazarus_project": _handle_lazarus_project,
    "lazarus_kb": _handle_lazarus_kb,
    "lazarus_file": _handle_lazarus_file,
}

LAZARUS_TOOL_DESCRIPTIONS: dict[str, str] = {
    "lazarus_compile": "Lazarus/Free Pascal 项目编译 (lazbuild)",
    "lazarus_project": "Lazarus 项目信息查询 — 解析 .lpi 文件，获取项目名称/主源文件/单元列表/编译器选项",
    "lazarus_kb": "Lazarus/FPC 源码知识库 — 索引和搜索 LCL/FPC RTL 源码。build(构建)/search(搜索)/stats(统计)/read(读取源码)",
    "lazarus_file": "Lazarus/FPC 文件读写 — read(读)/write(edits批量修改，自动备份)/backup(手动备份)",
}

LAZARUS_TOOL_SCHEMAS: dict[str, dict] = {
    "lazarus_compile": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi 或 .lpr 文件路径",
            },
            "target_platform": {
                "type": "string",
                "enum": ["win32", "win64"],
                "default": "win32",
            },
            "build_configuration": {
                "type": "string",
                "description": "Default / Release / Debug",
            },
            "timeout": {
                "type": "integer",
                "default": 600,
            },
            "run_verify": {
                "type": "boolean",
                "default": False,
                "description": "编译成功后启动程序 3 秒验证是否崩溃",
            },
        },
        "required": ["project_path"],
    },
    "lazarus_project": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi 或 .lpr 文件路径",
            },
            "action": {
                "type": "string",
                "enum": ["info", "units", "options"],
                "default": "info",
                "description": "info=项目概要, units=单元列表, options=编译器选项",
            },
        },
        "required": ["project_path"],
    },
    "lazarus_kb": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["build", "search", "stats", "read"],
                "default": "search",
                "description": "build=构建知识库, search=搜索, stats=统计, read=读取源码",
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（action=search 时必需）",
            },
            "top_k": {
                "type": "integer",
                "default": 20,
                "description": "返回结果数上限（默认20，最大100）",
            },
            "file_path": {
                "type": "string",
                "description": "源码文件路径（action=read 时必需）",
            },
            "content_type": {
                "type": "string",
                "description": "按文件类型过滤（如 pas/inc/pp）",
            },
        },
    },
    "lazarus_file": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "backup"],
                "default": "read",
                "description": "read=读取, write=写入(edits), backup=备份",
            },
            "file_path": {
                "type": "string",
                "description": "文件路径",
            },
            "edits": {
                "type": "array",
                "description": "批量编辑操作（write 时必需）",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {"type": "integer", "description": "起始行号（1-indexed 闭区间）"},
                        "end_line": {"type": "integer", "description": "结束行号（1-indexed 闭区间）"},
                        "content": {"type": "string", "description": "新内容"},
                    },
                    "required": ["start_line"],
                },
            },
            "encoding": {
                "type": "string",
                "description": "文件编码（不传则自动检测 BOM）",
            },
        },
        "required": ["action"],
    },
}
