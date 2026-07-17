"""Delphi 插件工具 handlers — 从 server.py run_server() 闭包中提取。"""
import asyncio
import sys
import winreg
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, TextContent

from src.constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_AUTOMATION_GUI,
)
from src.services.automation_service import (
    execute_automation as _execute_automation,
    detect_exe_subsystem as _detect_exe_subsystem,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
)
from src.utils.logger import init_default_logger

logger = init_default_logger()

# ── 工具模块导入（每个 handler 自给自足）──
from src.tools.project import handle_project as _handle_project
from src.tools import file_tool
from src.tools import pasfmt
from src.tools.config import search_compilers
from src.tools.environment import check_environment
from src.tools.install_package import handle_package
from src.tools.coding_rules import get_coding_rules as _get_coding_rules
from src.tools import knowledge_base as kb_tools
from src.tools import document_kb_tools as doc_tools
from src.tools import async_tasks as async_tools
from src.tools.read_source_file import read_source_file
from src.tools.knowledge_base import _resolve_project_path, _auto_detect_delphi_help_dir
from src.tools.manage_component import manage_component as _manage_component
from src.utils.delphi_env import get_delphi_version as _get_dv
from src.tools.delphi_rtti import handle_delphi_rtti as _handle_delphi_rtti


# ============================================================
# 辅助函数 — 仅被 Delphi handler 使用
# ============================================================

def _coerce_bool(val, default: bool = False) -> bool:
    """将任意输入安全转换为 bool。"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(val, (int, float)):
        return val != 0
    return default


def _auto_paths() -> list[str]:
    """返回需要注册到 Delphi 搜索路径的目录列表。"""
    root = Path(__file__).resolve().parents[3]
    return [
        str(root / "tools" / "auto"),
        str(root / "tools" / "stacktrace"),
    ]


def _register_path_for_platform(key, reg_path: str, path: str, platform: str, results: list[dict]):
    """将单个路径注册到指定平台的 Delphi 搜索路径。"""
    try:
        search_path, _ = winreg.QueryValueEx(key, "Search Path")
        paths = search_path.split(";")

        if path in paths:
            results.append({
                "platform": platform, "status": "already_present",
                "path": path,
            })
        else:
            clean_path = search_path.rstrip(";")
            new_path = clean_path + ";" + path if clean_path else path
            winreg.SetValueEx(key, "Search Path", 0, winreg.REG_SZ, new_path)
            results.append({
                "platform": platform, "status": "added",
                "path": path,
            })
    except Exception as e:
        results.append({
            "platform": platform, "status": "error",
            "path": path,
            "message": f"写入搜索路径失败: {e}",
        })


def _register_daofy_auto(version: str, platforms: list[str] | None = None) -> list[dict]:
    """将 DaofyAutomation + StackTrace 路径写入 Delphi 全局搜索路径（注册表）。"""
    if platforms is None:
        platforms = ["Win32", "Win64"]

    reg_paths = _auto_paths()
    results: list[dict] = []

    for platform in platforms:
        reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Library\\{platform}"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                reg_path,
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
        except FileNotFoundError:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "skipped",
                    "path": p,
                    "message": f"注册表路径不存在: HKCU\\{reg_path}",
                })
            continue
        except PermissionError:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "error",
                    "path": p,
                    "message": "权限不足，无法写入注册表",
                })
            continue
        except Exception as e:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "error",
                    "path": p,
                    "message": f"打开注册表失败: {e}",
                })
            continue

        try:
            for p in reg_paths:
                _register_path_for_platform(key, reg_path, p, platform, results)
        finally:
            try:
                winreg.CloseKey(key)
            except Exception:
                pass

    return results


# ============================================================
# 工具 handler 函数
# ============================================================

async def _handle_project_tool(arguments: dict) -> Any:
    return await _handle_project(**arguments)


async def _handle_delphi_kb(arguments: dict) -> Any:
    default_action = "web" if arguments.get("url") else "search"
    action = arguments.get("action", default_action)
    kb_type = arguments.get("kb_type", "all")
    if action == "search":
        return await doc_tools.search_documents(arguments) if kb_type == "document" else await kb_tools.search_knowledge(arguments)
    elif action == "stats":
        return await doc_tools.get_document_statistics(arguments) if kb_type == "document" else await kb_tools.get_unified_knowledge_stats(arguments)
    elif action == "build":
        async_mode = _coerce_bool(arguments.get("async_mode"), True)
        if not async_mode:
            return await kb_tools.build_unified_knowledge_base(arguments)
        version = arguments.get("version")
        rebuild = _coerce_bool(arguments.get("rebuild"), False)
        kb_type_map = {"all": "build_knowledge_base", "delphi": "build_knowledge_base",
                       "thirdparty": "build_thirdparty_knowledge_base", "project": "init_project_knowledge_base",
                       "document": "build_document_knowledge_base"}
        task_type = kb_type_map.get(kb_type, "build_knowledge_base")
        incremental = arguments.get("incremental", False)
        if task_type == "build_document_knowledge_base":
            directory = arguments.get("directory")
            start_url = arguments.get("start_url")
            urls = arguments.get("urls", [])
            # 只有当没有指定 start_url 和 urls（纯目录扫描）时才自动检测帮助目录
            if not directory and not start_url and not urls:
                detected = _auto_detect_delphi_help_dir()
                if detected:
                    directory = detected
                    logger.info(f"自动检测到 Delphi 帮助目录: {directory}")
                else:
                    logger.warning("未提供 directory 且未检测到 Delphi 帮助目录")

            # 文档知识库重建确认：force_rebuild 会清除现有所有文档
            if rebuild:
                try:
                    _scanner = doc_tools._get_scanner()
                    _stats = _scanner.get_statistics()
                    _total = _stats.get('total_documents', 0)
                    if _total > 0:
                        _confirm = _coerce_bool(arguments.get("confirm"), False)
                        if not _confirm:
                            _msg = [f"⚠️ **确认重建文档知识库**\n\n当前知识库包含 **{_total}** 篇文档：\n"]
                            _by_type = _stats.get('by_type', {})
                            if _by_type:
                                _msg.append("按类型：\n")
                                for _t, _c in sorted(_by_type.items(), key=lambda x: x[1], reverse=True):
                                    _msg.append(f"  - {_t}: {_c}\n")
                            _by_ext = _stats.get('by_extension', {})
                            if _by_ext:
                                _msg.append("按扩展名：\n")
                                for _e, _c in sorted(_by_ext.items(), key=lambda x: x[1], reverse=True):
                                    _msg.append(f"  - {_e}: {_c}\n")
                            _msg.append(
                                "\n`rebuild=True` 将 **清除以上所有文档** 后重新构建，原有内容不可恢复。\n\n"
                                "如需保留旧内容，请：\n"
                                "  1. 在本次构建参数中同时包含旧的文档源（如多个 URL 或目录），或\n"
                                "  2. 移除 `rebuild=True` 改用增量添加\n\n"
                                "**确认继续请添加参数 `confirm=True`**"
                            )
                            return CallToolResult(content=[TextContent(type="text", text="".join(_msg))])
                except Exception as _e:
                    logger.warning(f"检查文档知识库状态失败，跳过确认: {_e}")

            task_params = {"urls": arguments.get("urls", []), "directory": directory,
                           "extensions": arguments.get("extensions", [".chm"]),
                           "start_url": arguments.get("start_url"), "max_pages": arguments.get("max_pages", 100),
                           "max_depth": arguments.get("max_depth", 3), "domain_filter": arguments.get("domain_filter"),
                           "url_pattern": arguments.get("url_pattern"), "exclude": arguments.get("exclude"),
                           "rebuild": rebuild}
        elif task_type == "init_project_knowledge_base":
            resolved_path = _resolve_project_path(arguments.get("project_path"))
            task_params = {"project_path": resolved_path, "version": version,
                           "rebuild": rebuild, "build_thirdparty": arguments.get("build_thirdparty", True),
                           "build_project": arguments.get("build_project", True)}
        else:
            task_params = {"version": version, "rebuild": rebuild, "incremental": incremental}
        return await async_tools.start_async_task({"task_type": task_type, "task_params": task_params,
                                                      "show_progress": arguments.get("show_progress", True),
                                                      "_on_complete": arguments.get("_on_complete")})
    elif action == "build_embedding":
        pp = _resolve_project_path(arguments.get("project_path"))
        if not pp:
            return {"error": "未检测到项目路径"}
        return await async_tools.start_async_task({"task_type": "build_embedding", "task_params": {"project_path": pp},
                                                     "show_progress": True,
                                                     "_on_complete": arguments.get("_on_complete")})
    elif action == "scan":
        return await doc_tools.scan_documents(arguments) if kb_type == "document" else {"error": "action=scan 仅支持 kb_type=document"}
    elif action == "web":
        return await doc_tools.add_web_document(arguments) if kb_type == "document" else {"error": "action=web 仅支持 kb_type=document"}
    elif action == "read":
        if arguments.get("url") or arguments.get("doc_id"):
            return await doc_tools.read_document(arguments)
        elif arguments.get("file_path"):
            return await read_source_file(arguments)
        return {"error": "action=read 需要 url/doc_id 或 file_path 参数"}
    return {"error": f"未知action: {action}"}


async def _handle_file_tool(arguments: dict) -> Any:
    return await file_tool.handle_file_tool(arguments)


async def _handle_manage_component(arguments: dict) -> Any:
    # manage_component 是 async 函数，直接调用
    return await _manage_component(
        action=arguments.get("action", "create"),
        target_dfm=arguments.get("target_dfm"),
        target_pas=arguments.get("target_pas"),
        component_name=arguments.get("component_name"),
        parent_name=arguments.get("parent_name"),
        new_component_class=arguments.get("new_component_class"),
        new_component_name=arguments.get("new_component_name"),
        properties=arguments.get("properties"),
        dfm_text=arguments.get("dfm_text"),
        code=arguments.get("code", ""),
        uses=arguments.get("uses"),
        type_decl=arguments.get("type_decl", ""),
        init_code=arguments.get("init_code", ""),
        compile_timeout=arguments.get("compile_timeout", 60),
        exec_timeout=arguments.get("exec_timeout", 15),
    )


async def _handle_check_environment(arguments: dict) -> Any:
    action = arguments.get("action", "check")
    if action == "detect":
        return await search_compilers(search_path=arguments.get("search_path"))
    elif action == "check":
        return await check_environment()
    elif action == "install":
        return await pasfmt.download_and_install_pasfmt(install_dir=arguments.get("install_dir"))
    elif action == "format_install":
        return await pasfmt.download_and_install_pasfmt_rad(delphi_version=arguments.get("delphi_version", "11"), install_dir=arguments.get("install_dir"))
    return {"error": f"未知action: {action}"}


async def _handle_package(arguments: dict) -> Any:
    return await handle_package(**arguments)


async def _handle_get_coding_rules(arguments: dict) -> Any:
    return await _get_coding_rules(project_path=arguments.get("project_path"), section=arguments.get("section"), examples=arguments.get("examples"))


async def _handle_automate_delphi(arguments: dict) -> dict:
    """处理 automate_delphi 工具调用（自动检测或按 action 路由）。"""
    requested_action = arguments.get("action", "auto")
    action = requested_action

    # ── prepare：注册 DaofyAutomation 到 Delphi 全局搜索路径 ──
    if action == "prepare":
        try:
            version = _get_dv()
        except ImportError:
            version = None

        if not version:
            return {
                "action": "prepare", "status": "error",
                "message": "未检测到已安装的 Delphi 编译器",
            }

        results = _register_daofy_auto(version)
        added = sum(1 for r in results if r["status"] == "added")
        already = sum(1 for r in results if r["status"] == "already_present")
        errors = sum(1 for r in results if r["status"] == "error")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        return {
            "action": "prepare",
            "delphi_version": version,
            "daofy_auto_paths": _auto_paths(),
            "results": results,
            "status": "success" if errors == 0 else "partial",
            "message": (
                f"Delphi {version}: 新增 {added} 个平台, "
                f"已存在 {already} 个平台"
                + (f", {skipped} 个跳过" if skipped else "")
                + (f", {errors} 个失败" if errors else "")
            ),
        }

    app_path = arguments.get("app_path", "")
    keep_alive = _coerce_bool(arguments.get("keep_alive", False))
    stop_on_failure = _coerce_bool(arguments.get("stop_on_failure", True))
    env = arguments.get("env", None)
    subsystem = None

    if not app_path:
        return {"status": "error", "message": "缺少必需参数: app_path"}

    # auto 检测：读 PE 头 Subsystem
    if action == "auto":
        subsystem = _detect_exe_subsystem(app_path)
        if subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI:
            action = "console"
        elif subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI:
            action = "gui"
        else:
            # 无法检测时默认 gui（保持兼容）
            action = "gui"

    if action == "gui":
        script = arguments.get("script", "")
        snapshots_dir = arguments.get("snapshots_dir", "")
        wait_timeout = arguments.get("wait_timeout", 10)

        if not script:
            return {"status": "error", "message": "gui 模式缺少必需参数: script"}

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute_automation,
                                  action="gui",
                                  app_path=app_path,
                                  script=script,
                                  snapshots_dir=snapshots_dir,
                                  wait_for_pipe=wait_timeout,
                                  keep_alive=keep_alive,
                                  stop_on_failure=stop_on_failure,
                                  env=env),
                timeout=TIMEOUT_AUTOMATION_GUI,
            )
            result.setdefault("requested_action", requested_action)
            result.setdefault("resolved_action", action)
            result.setdefault("detected_subsystem", subsystem)
            return result
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": "automate_delphi(gui) 执行超时（300s）",
            }
        except Exception as e:
            return {"status": "failed", "message": f"automate_delphi(gui) failed: {e}"}

    elif action == "console":
        input_text = arguments.get("input", "")
        expect = arguments.get("expect", "")
        timeout = arguments.get("timeout", 30)
        args = arguments.get("args", None)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute_automation,
                                  action="console",
                                  app_path=app_path,
                                  input_text=input_text,
                                  expect=expect,
                                  timeout=timeout,
                                  keep_alive=keep_alive,
                                  args=args,
                                  env=env),
                timeout=max(timeout + 10, 120),
            )
            result.setdefault("requested_action", requested_action)
            result.setdefault("resolved_action", action)
            result.setdefault("detected_subsystem", subsystem)
            return result
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": "automate_delphi(console) 执行超时",
                "action": "console",
            }
        except Exception as e:
            return {"status": "failed", "message": f"automate_delphi(console) failed: {e}"}

    else:
        return {"status": "error", "message": f"未知 action: {action}"}


async def _handle_delphi_rtti(arguments: dict) -> dict:
    """处理 delphi_rtti 工具调用（RTTI 发现/调用）。"""
    return await _handle_delphi_rtti(arguments)


# ============================================================
# 导出：工具名 → handler 映射
# ============================================================
DELPHI_HANDLERS = {
    "delphi_project": _handle_project_tool,
    "delphi_kb": _handle_delphi_kb,
    "delphi_file": _handle_file_tool,
    "file_tool": _handle_file_tool,  # 旧名兼容别名
    "manage_component": _handle_manage_component,
    "check_environment": _handle_check_environment,
    "package": _handle_package,
    "get_coding_rules": _handle_get_coding_rules,
    "automate_delphi": _handle_automate_delphi,
    "delphi_rtti": _handle_delphi_rtti,
}

# ── 工具描述 + inputSchema — list_tools() 从 registry 收取，不再硬编码在 server.py ──

DELPHI_TOOL_DESCRIPTIONS: dict[str, str] = {
    "delphi_project": "编译/配置/审计/部署",
    "delphi_kb": "知识库搜索/管理",
    "delphi_file": "Delphi 文件专用读写/搜索/替换/备份工具 — 即使只是读取 .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx 也必须用此工具，禁止用内置 Read/Edit/Write/grep",
    "manage_component": "DFM组件增/删/改/生成",
    "check_environment": "环境检查/编译器检测/安装",
    "package": "组件包编译安装/列出",
    "get_coding_rules": "编码必用编码规则获取工具",
    "automate_delphi": "Delphi 自动化测试",
    "delphi_rtti": "RTTI 发现/调用",
}

DELPHI_TOOL_SCHEMAS: dict[str, dict] = {
    "delphi_project": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["compile", "compile_file", "dry_run", "info", "create",
                         "set", "add_config", "remove_config", "add_source",
                         "remove_source", "audit", "ast", "runtime", "layout",
                         "devices", "deploy"],
            },
            "project_path": {"type": "string", "description": "项目文件路径 (.dproj/.dpr/.dpk)"},
            "extra_args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "附加编译参数（如 [\"/p:DCC_DebugInfoInTds=true\"]）",
            },
        },
        "required": ["action"]
    },
    "delphi_kb": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "stats", "build", "scan", "web", "read", "build_embedding"]},
        }
    },
    "delphi_file": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "replace", "insert", "delete", "format", "backup", "encode", "uses", "fix_garbled", "grep"],
                "default": "read",
            },
            "file_path": {"type": "string", "description": "文件路径"},
            "edits": {
                "type": "array",
                "description": "批量编辑操作（write/replace/insert/delete）",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {"type": "integer", "description": "起始行号（1-indexed 闭区间）"},
                        "end_line": {"type": "integer", "description": "结束行号（1-indexed 闭区间）"},
                        "content": {"type": "string", "description": "新内容"},
                        "old_content": {"type": "string", "description": "原内容（非空时作为写入前校验，防止覆盖非预期改动）"},
                        "position": {"type": "integer", "description": "insert 操作的插入位置（1-indexed 行号）"},
                    },
                    "required": ["start_line"],
                },
            },
            "force": {
                "type": "boolean",
                "description": "跳过连续重复行检测",
                "default": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "预览变更，不实际写入",
                "default": False,
            },
            "encoding": {"type": "string", "description": "文件编码（自动检测 BOM）"},
            "search_pattern": {"type": "string", "description": "搜索正则表达式（action=grep 时使用）"},
            "line_number": {"type": "integer", "description": "起始行号"},
            "count": {"type": "integer", "description": "搜索结果数量限制"},
        },
        "required": ["action"]
    },
    "manage_component": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "add", "remove", "modify"], "default": "create"},
        },
        "required": ["action"]
    },
    "check_environment": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check"},
        }
    },
    "package": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["install", "list"], "default": "install"},
        },
        "required": ["action"]
    },
    "get_coding_rules": {
        "type": "object",
        "properties": {
            "section": {"type": "string"},
            "examples": {"type": "string", "description": "示例名称，如 naming/format/debug-log。按名称加载 coding-rules/examples/ 下的示例文件"},
        }
    },
    "automate_delphi": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["auto", "gui", "console", "prepare"],
                "default": "auto",
            },
        },
        "required": [],
    },
    "delphi_rtti": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["guide", "discover", "call"],
            },
        },
        "required": ["action"],
    },
}
