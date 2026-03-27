"""
异步任务管理 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供异步任务的启动、查询和管理功能
"""

from typing import Any, Optional
from mcp.types import CallToolResult

from ..services.knowledge_base.async_task_manager import get_task_manager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def start_async_task(arguments: Any) -> CallToolResult:
    """
    启动异步任务

    Args:
        arguments: 包含以下参数:
            - task_type: 任务类型 (必需)
                - "build_knowledge_base": 构建Delphi知识库
                - "build_thirdparty_knowledge_base": 构建第三方库知识库
                - "init_project_knowledge_base": 初始化项目知识库
            - params: 任务参数 (可选, 根据任务类型不同)
            - show_progress: 是否显示进度 (可选, 默认 true)

    Returns:
        任务启动结果，包含任务ID
    """
    task_type = arguments.get("task_type")
    params = arguments.get("params", {})
    show_progress = arguments.get("show_progress", True)

    if not task_type:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供任务类型"}],
            isError=True
        )

    task_manager = get_task_manager()

    # 根据任务类型创建任务函数
    if task_type == "build_knowledge_base":
        from ..services.knowledge_base.service import DelphiKnowledgeBaseService

        def build_kb_task(**kwargs):
            version = kwargs.get("version")
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            service = DelphiKnowledgeBaseService(progress_callback=progress_callback)
            return service.build_knowledge_base(version=version, force_rebuild=force_rebuild)

        task_name = f"构建Delphi知识库 (版本: {params.get('version', '最新')})"

    elif task_type == "build_thirdparty_knowledge_base":
        from ..services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase

        def build_thirdparty_task(**kwargs):
            version = kwargs.get("version")
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            service = ThirdPartyKnowledgeBase(progress_callback=progress_callback)
            return service.build_thirdparty_knowledge_base(version=version, force_rebuild=force_rebuild)

        task_name = "构建第三方库知识库"

    elif task_type == "init_project_knowledge_base":
        from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase

        def init_project_task(**kwargs):
            project_path = kwargs.get("project_path")
            build_thirdparty = kwargs.get("build_thirdparty", True)
            build_project = kwargs.get("build_project", True)
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            project_kb = ProjectKnowledgeBase(project_path, progress_callback)

            results = {}
            if build_thirdparty:
                results["thirdparty"] = project_kb.build_thirdparty_knowledge_base(force_rebuild=force_rebuild)
            if build_project:
                results["project"] = project_kb.build_project_knowledge_base(force_rebuild=force_rebuild)

            stats = project_kb.get_statistics()
            results["statistics"] = stats

            return results

        task_name = f"初始化项目知识库 ({params.get('project_path', '未知项目')})"

    else:
        return CallToolResult(
            content=[{"type": "text", "text": f"未知的任务类型: {task_type}"}],
            isError=True
        )

    try:
        # 创建进度回调
        def progress_callback(progress, message):
            if show_progress:
                logger.info(f"任务进度: {progress:.1f}% - {message}")

        # 提交异步任务
        task_id = task_manager.submit_task(
            name=task_name,
            func=build_kb_task if task_type == "build_knowledge_base" else
                  build_thirdparty_task if task_type == "build_thirdparty_knowledge_base" else
                  init_project_task,
            progress_callback=progress_callback if show_progress else None,
            **params
        )

        result_text = f"✓ 异步任务已启动\n\n"
        result_text += f"任务ID: {task_id}\n"
        result_text += f"任务名称: {task_name}\n"
        result_text += f"状态: 已提交到后台执行\n\n"
        result_text += f"使用以下命令查询任务状态:\n"
        result_text += f"  - get_task_status: 查询任务状态\n"
        result_text += f"  - get_task_result: 获取任务结果\n"
        result_text += f"  - list_tasks: 列出所有任务"

        return CallToolResult(content=[{"type": "text", "text": result_text}])

    except Exception as e:
        logger.error(f"启动异步任务失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"启动异步任务失败: {str(e)}"}],
            isError=True
        )


async def get_task_status(arguments: Any) -> CallToolResult:
    """
    获取任务状态

    Args:
        arguments: 包含以下参数:
            - task_id: 任务ID (必需)

    Returns:
        任务状态信息
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供任务ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    task_info = task_manager.get_task_info(task_id)

    if not task_info:
        return CallToolResult(
            content=[{"type": "text", "text": f"未找到任务: {task_id}"}],
            isError=True
        )

    result_text = f"任务状态: {task_id}\n\n"
    result_text += f"任务名称: {task_info.name}\n"
    result_text += f"状态: {task_info.status.value}\n"
    result_text += f"进度: {task_info.progress:.1f}%\n"
    result_text += f"消息: {task_info.message}\n"
    result_text += f"创建时间: {task_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.started_at:
        result_text += f"开始时间: {task_info.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.completed_at:
        result_text += f"完成时间: {task_info.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.error:
        result_text += f"错误: {task_info.error}\n"

    return CallToolResult(content=[{"type": "text", "text": result_text}])


async def get_task_result(arguments: Any) -> CallToolResult:
    """
    获取任务结果

    Args:
        arguments: 包含以下参数:
            - task_id: 任务ID (必需)

    Returns:
        任务结果
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供任务ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    task_info = task_manager.get_task_info(task_id)

    if not task_info:
        return CallToolResult(
            content=[{"type": "text", "text": f"未找到任务: {task_id}"}],
            isError=True
        )

    if task_info.status != TaskStatus.COMPLETED:
        result_text = f"任务尚未完成\n\n"
        result_text += f"任务ID: {task_id}\n"
        result_text += f"当前状态: {task_info.status.value}\n"
        result_text += f"进度: {task_info.progress:.1f}%\n"
        result_text += f"消息: {task_info.message}\n"

        return CallToolResult(content=[{"type": "text", "text": result_text}])

    if task_info.error:
        return CallToolResult(
            content=[{"type": "text", "text": f"任务执行失败: {task_info.error}"}],
            isError=True
        )

    # 格式化结果
    result_text = f"任务执行成功!\n\n"
    if isinstance(task_info.result, dict):
        for key, value in task_info.result.items():
            result_text += f"{key}: {value}\n"
    else:
        result_text += f"结果: {task_info.result}\n"

    return CallToolResult(content=[{"type": "text", "text": result_text}])


async def list_tasks(arguments: Any) -> CallToolResult:
    """
    列出所有任务

    Args:
        arguments: 空参数

    Returns:
        所有任务列表
    """
    task_manager = get_task_manager()
    tasks = task_manager.get_all_tasks()

    if not tasks:
        return CallToolResult(content=[{"type": "text", "text": "当前没有任务"}])

    result_text = f"任务列表 (共 {len(tasks)} 个):\n\n"

    for task_id, task_info in tasks.items():
        result_text += f"任务ID: {task_id}\n"
        result_text += f"  名称: {task_info.name}\n"
        result_text += f"  状态: {task_info.status.value}\n"
        result_text += f"  进度: {task_info.progress:.1f}%\n"
        result_text += f"  消息: {task_info.message}\n"
        result_text += f"  创建时间: {task_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result_text += "\n"

    return CallToolResult(content=[{"type": "text", "text": result_text}])
