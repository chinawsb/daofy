"""核心工具 handlers — 从 server.py run_server() 闭包中提取。

不属于任何编译器插件的工具：async_task, code_hosting, tool_help,
experience, daofy_update, generate_copyright, ocr
"""
import asyncio
import sys
from typing import Any

from src.constants import TIMEOUT_EXPERIENCE_TOOL, TIMEOUT_GENERATE_COPYRIGHT
from src.services.copyright_service import generate_copyright as _generate_copyright
from src.services.knowledge_base.async_task_manager import get_task_manager
from src.tools import async_tasks as async_tools
from src.tools.code_hosting import code_hosting
from src.tools.experience import experience as _experience
from src.tools.tool_help import get_tool_help
from src.utils import updater
from src.tool_docs import TOOL_NAMES
from src.utils.logger import init_default_logger

logger = init_default_logger()


def _coerce_bool(val, default: bool = False) -> bool:
    """将任意输入安全转换为 bool。"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(val, (int, float)):
        return val != 0
    return default


async def _handle_async_task(arguments: dict) -> Any:
    action = arguments.get("action", "list")
    handlers = {"start": async_tools.start_async_task, "status": async_tools.get_task_status,
                 "result": async_tools.get_task_result, "list": async_tools.list_tasks,
                 "cancel": async_tools.cancel_task}
    handler = handlers.get(action)
    if handler:
        return await handler(arguments)
    return {"error": f"未知action: {action}"}


async def _handle_code_hosting(arguments: dict) -> Any:
    try:
        if "action" not in arguments:
            return {"status": "failed", "message": "missing required parameter: action"}
        # 使用 asyncio.to_thread 避免同步 HTTP 阻塞事件循环
        return await asyncio.to_thread(code_hosting, **arguments)
    except Exception as e:
        logger.error(f"code_hosting 执行失败: {e}", exc_info=True)
        return {"status": "failed", "message": f"code_hosting failed: {e}"}


async def _handle_tool_help(arguments: dict) -> Any:
    return get_tool_help(
        tool_name=arguments.get("tool_name", ""),
        action=arguments.get("action", ""),
    )


async def _handle_experience(arguments: dict) -> dict:
    """处理 experience 工具调用，带 asyncio 超时保护（30s）。"""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_experience, **arguments),
            timeout=TIMEOUT_EXPERIENCE_TOOL,
        )
        return result
    except asyncio.TimeoutError:
        return {
            "status": "failed",
            "message": "experience 操作超时（30s），可能是 embedding 模型加载/下载耗时过长。"
                " 建议：先调用 delphi_kb(action=build_embedding) 预加载模型，"
                " 再使用 experience 的语义搜索功能。",
        }
    except Exception as e:
        return {"status": "failed", "message": f"experience failed: {e}"}


async def _handle_daofy_update(arguments: dict) -> dict:
    """处理 daofy_update 工具调用（类似 code_hosting 模式：后台异步+定时重试）。"""
    action = arguments.get("action", "check")
    task_manager = get_task_manager()

    # ── version: 同步返回，无需网络 ──
    if action == "version":
        install_type = "git" if updater.is_git_installation() else "pip"
        return {
            "version": updater.get_current_version(),
            "install_type": install_type,
            "python": sys.version,
        }

    # ── check: 先快速尝试（同步），失败后提交后台重试任务 ──
    if action == "check":
        # 1. 优先检查缓存
        cached = updater.get_cached_update_result()
        if cached is not None:
            install_type = "git" if updater.is_git_installation() else "pip"
            cached["install_type"] = install_type
            status_msg = (
                f"发现新版本 v{cached['latest']}！（当前 v{cached['current']}）"
                if cached.get("update_available")
                else f"当前已是最新版本: v{cached['current']}"
            )
            return {**cached, "message": status_msg, "cache_hit": True}

        # 2. 快速同步尝试
        quick = await asyncio.get_running_loop().run_in_executor(
            None, updater.check_for_update
        )
        if quick is not None:
            install_type = "git" if updater.is_git_installation() else "pip"
            quick["install_type"] = install_type
            if quick["update_available"]:
                if install_type == "git":
                    quick["message"] = (
                        f"发现新版本 v{quick['latest']}！"
                        f" 当前版本 v{quick['current']}。"
                        f" 建议: daofy_update(action='update') 执行 git pull 更新。"
                    )
                else:
                    quick["message"] = (
                        f"发现新版本 v{quick['latest']}！"
                        f" 当前版本 v{quick['current']}。"
                        f" 请运行: pip install --upgrade daofy-for-delphi"
                    )
            else:
                quick["message"] = f"当前已是最新版本: v{quick['current']}"
            return quick

        # 3. 快速尝试失败，提交后台自动重试任务（类似 code_hosting git_push_retry）
        logger.info("版本检查快速尝试失败，提交后台自动重试任务...")
        on_complete = arguments.get('_on_complete')
        task_id = task_manager.submit_task(
            name="version_check_retry",
            func=updater.check_for_update_retry,
            on_complete=on_complete,
            dedup_key="version_check_retry",
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "快速检查失败（网络不可达），已提交后台自动重试任务。\n"
                f"  任务ID: {task_id}\n"
                f"  重试间隔: {updater.RETRY_INTERVAL}s | 最多 {updater.MAX_RETRIES} 次\n"
                "  使用 async_task(action=status, task_id=...) 查看进度。"
            ),
        }

    # ── check_retry: 强制提交后台自动重试任务（返回 task_id） ──
    if action == "check_retry":
        on_complete = arguments.get('_on_complete')
        task_id = task_manager.submit_task(
            name="version_check_retry",
            func=updater.check_for_update_retry,
            on_complete=on_complete,
            dedup_key="version_check_retry",
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "后台版本检查任务已提交。\n"
                f"  任务ID: {task_id}\n"
                f"  重试间隔: {updater.RETRY_INTERVAL}s | 最多 {updater.MAX_RETRIES} 次\n"
                "  使用 async_task(action=status, task_id=...) 查看进度。"
            ),
        }

    # ── update / update_retry: 后台 git pull 更新 ──
    if action in ("update", "update_retry"):
        if not updater.is_git_installation():
            return {
                "success": False,
                "message": (
                    "当前为 pip 安装模式，不支持 git pull 更新。\n"
                    "请手动运行: pip install --upgrade daofy-for-delphi"
                ),
            }

        on_complete = arguments.get('_on_complete')
        retry_interval = int(arguments.get("retry_interval", 60))
        max_retries = int(arguments.get("max_retries", 10))

        if action == "update_retry":
            # 自定义 retry 参数
            orig_interval = updater.UPDATE_RETRY_INTERVAL
            orig_max = updater.UPDATE_MAX_RETRIES
            updater.UPDATE_RETRY_INTERVAL = retry_interval
            updater.UPDATE_MAX_RETRIES = max_retries
            try:
                task_id = task_manager.submit_task(
                    name="git_update_retry",
                    func=updater._do_retry_update,
                    on_complete=on_complete,
                    dedup_key="git_update_retry",
                )
            finally:
                updater.UPDATE_RETRY_INTERVAL = orig_interval
                updater.UPDATE_MAX_RETRIES = orig_max
            eta_min = (retry_interval * max_retries) // 60
            return {
                "task_id": task_id,
                "status": "async",
                "message": (
                    "后台自动重试 git pull 更新任务已提交。\n"
                    f"  任务ID: {task_id}\n"
                    f"  重试间隔: {retry_interval}s | 最多 {max_retries} 次 | 预计最长 ~{eta_min}min\n"
                    "  使用 async_task(action=status, task_id=...) 查看进度。"
                ),
            }

        # update（单次）
        task_id = task_manager.submit_task(
            name="git_update",
            func=updater.git_pull_update_sync,
            on_complete=on_complete,
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "后台 git pull 更新任务已提交。\n"
                f"  任务ID: {task_id}\n"
                "  使用 async_task(action=status, task_id=...) 查看进度。"
            ),
        }

    return {"error": f"未知 action: {action}"}


async def _handle_generate_copyright(arguments: dict) -> dict:
    """处理 generate_copyright 工具调用。"""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_generate_copyright, **arguments),
            timeout=TIMEOUT_GENERATE_COPYRIGHT,
        )
        return result
    except asyncio.TimeoutError:
        return {"status": "failed", "message": "generate_copyright 执行超时（300s）"}
    except Exception as e:
        return {"status": "failed", "message": f"generate_copyright failed: {e}"}


async def _handle_ocr(arguments: dict) -> dict:
    """处理 ocr 工具调用（延迟导入，无 OCR 依赖时返回友好错误）。"""
    try:
        from src.tools.ocr import handle_ocr as _ocr_handler
    except ImportError as e:
        return {
            "status": "failed",
            "error": (
                f"缺少 OCR 依赖: {e}。"
                "请安装可选依赖: pip install daofy-for-delphi[ocr]"
            ),
        }
    return await asyncio.to_thread(_ocr_handler, arguments)


CORE_HANDLERS = {
    "async_task": _handle_async_task,
    "code_hosting": _handle_code_hosting,
    "tool_help": _handle_tool_help,
    "experience": _handle_experience,
    "daofy_update": _handle_daofy_update,
    "generate_copyright": _handle_generate_copyright,
    "ocr": _handle_ocr,
}

# ── 工具描述 + inputSchema — list_tools() 从 registry 收取，不再硬编码在 server.py ──

CORE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "async_task": "异步任务管理",
    "code_hosting": "Git 操作和代码托管平台 API。参数随 action 变化；调用前先执行 tool_help(tool_name='code_hosting', action='<action>')。",
    "tool_help": "按工具名和可选 action 获取按需帮助文档、参数说明与示例",
    "experience": "经验记忆管理。参数随 action 变化；调用前先执行 tool_help(tool_name='experience', action='<action>')。",
    "daofy_update": "版本更新检查和 git pull。参数随 action 变化；调用前先执行 tool_help(tool_name='daofy_update', action='<action>')。",
    "generate_copyright": "生成软著文档。参数随 action 变化；调用前先执行 tool_help(tool_name='generate_copyright', action='<action>')。",
    "ocr": "图像分析。参数随 action 变化；调用前先执行 tool_help(tool_name='ocr', action='<action>')。",
}

CORE_TOOL_SCHEMAS: dict[str, dict] = {
    "async_task": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list"},
            "task_id": {"type": "string", "description": "任务 ID"},
            "long_poll_seconds": {
                "type": "integer",
                "description": "长轮询等待秒数（可选，默认0即立即返回。MCP请求通道有超时限制，建议≤30秒）",
                "default": 0,
            },
        }
    },
    "code_hosting": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [
                "create_token", "init_labels", "create_issue", "get_issue", "edit_issue",
                "set_labels", "close_issue", "add_comment", "list_issues",
                "create_pull", "get_pull", "list_pulls", "edit_pull", "merge_pull",
                "close_pull", "reopen_pull",
                "create_release", "get_release", "list_releases", "edit_release", "delete_release",
                "git_clone", "git_add", "git_commit", "git_push", "git_push_retry",
                "git_status", "git_diff", "git_show", "git_log",
                "git_fetch", "git_pull", "git_branch", "git_switch", "git_merge",
                "git_restore", "git_unstage", "git_stash", "git_tag",
            ]},
        },
        "required": ["action"]
    },
    "tool_help": {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "enum": TOOL_NAMES,
            },
            "action": {
                "type": "string",
                "description": "可选；只返回指定工具 action 的参数说明和示例",
            },
        },
        "required": ["tool_name"],
    },
    "experience": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "search", "get", "list", "update", "merge", "prune", "delete", "rebuild_embedding"],
            },
        },
        "required": ["action"],
    },
    "daofy_update": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check", "check_retry", "update", "update_retry", "version"],
                "default": "check",
            },
        },
        "required": ["action"],
    },
    "generate_copyright": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "validate", "update_config", "status", "list", "generate_content", "audit"],
                "default": "generate",
            },
        },
        "required": ["action"],
    },
    "ocr": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["recognize", "detect", "status", "diff", "color", "match"],
                "default": "recognize",
            },
        },
        "required": [],
    },
}
