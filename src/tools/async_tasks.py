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
                - "build_document_knowledge_base": 构建文档知识库
            - params: 任务参数 (可选, 根据任务类型不同)
                - build_document_knowledge_base:
                    - urls: 网页URL列表
                    - directory: 扫描目录路径
                    - extensions: 文件扩展名列表
            - show_progress: 是否显示进度 (可选, 默认 true)

    Returns:
        任务启动结果，包含任务ID
    """
    task_type = arguments.get("task_type")
    params = arguments.get("task_params", {})
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
        from src.utils.delphi_env import get_delphi_version

        def build_kb_task(**kwargs):
            version = kwargs.get("version")
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")
            service = DelphiKnowledgeBaseService(progress_callback=progress_callback)
            return service.build_knowledge_base(version=version, force_rebuild=force_rebuild)

        # 确定显示的版本号
        display_version = params.get("version")
        if not display_version:
            display_version = get_delphi_version()
        if not display_version:
            display_version = "最新"
        task_name = f"构建Delphi知识库 (版本: {display_version})"

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
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            project_kb = ProjectKnowledgeBase(project_path, progress_callback)
            # 三方库和项目源码已在 build_project_knowledge_base 中合并构建

            results = {}
            results["project"] = project_kb.build_project_knowledge_base(
                force_rebuild=force_rebuild)

            stats = project_kb.get_statistics()
            results["statistics"] = stats

            return results

        task_name = f"初始化项目知识库 ({params.get('project_path', '未知项目')})"

    elif task_type == "build_embedding":
        from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase

        def build_embedding_task(**kwargs):
            project_path = kwargs.get("project_path")
            progress_callback = kwargs.get("_progress_callback")
            pkb = ProjectKnowledgeBase(project_path, progress_callback)
            pkb.load_knowledge_bases()
            counts = pkb.build_vectors(progress_callback=progress_callback)
            pkb.close()
            return counts

        task_name = f"构建 embedding 向量 ({params.get('project_path', '')})"

    elif task_type == "build_document_knowledge_base":
        from ..services.knowledge_base.scan_generic_documents import GenericDocumentScanner
        from pathlib import Path as FilePath
        
        def build_doc_task(**kwargs):
            urls = kwargs.get("urls", [])
            directory = kwargs.get("directory")
            extensions = kwargs.get("extensions")
            start_url = kwargs.get("start_url")
            max_pages = kwargs.get("max_pages", 100)
            max_depth = kwargs.get("max_depth", 3)
            domain_filter = kwargs.get("domain_filter")
            url_pattern = kwargs.get("url_pattern")
            exclude_dirs = kwargs.get("exclude_dirs")
            force_rebuild = kwargs.get("force_rebuild", False)
            progress_callback = kwargs.get("_progress_callback")
            
            server_root = FilePath(__file__).parent.parent.parent
            kb_dir = str(server_root / "data" / "document-knowledge-base")
            FilePath(kb_dir).mkdir(parents=True, exist_ok=True)
            
            scanner = GenericDocumentScanner(kb_dir, progress_callback=progress_callback)
            
            results = {"success": 0, "failed": 0, "total": 0, "total_size": 0}
            
            # 爬取网站（自动嵌套采集）
            if start_url:
                crawl_result = scanner.crawl_website(
                    start_url=start_url,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    domain_filter=domain_filter,
                    url_pattern=url_pattern
                )
                results.update(crawl_result)
            
            # 添加指定 URL 列表
            if urls:
                for url in urls:
                    result = scanner.add_web_document(url)
                    if result and not (isinstance(result, dict) and 'error' in result):
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                    results["total"] += 1
            
            # 扫描目录
            if directory:
                scan_result = scanner.scan_directory(directory, extensions=extensions, exclude_dirs=exclude_dirs,
                                                     force_rebuild=force_rebuild)
                results["scan"] = scan_result
            
            return results
        
        if params.get("start_url"):
            task_name = f"爬取网站 (最多 {params.get('max_pages', 100)} 页)"
        elif params.get("directory"):
            task_name = f"构建文档知识库 (扫描目录: {params.get('directory')})"
        else:
            urls_count = len(params.get("urls", []))
            task_name = f"构建文档知识库 ({urls_count} 个URL)"

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

        # 计算去重键，防止同类型构建重复提交
        dedup_key = params.pop("dedup_key", None)
        if dedup_key is None:
            if task_type == "init_project_knowledge_base":
                dedup_key = f"project_rebuild:{params.get('project_path', '')}"
            elif task_type == "build_thirdparty_knowledge_base":
                dedup_key = "thirdparty_rebuild"
            elif task_type == "build_knowledge_base":
                dedup_key = "delphi_rebuild"
            elif task_type == "build_document_knowledge_base":
                dedup_key = f"document_rebuild:{params.get('directory', '')}"
            elif task_type == "build_embedding":
                dedup_key = f"embedding:{params.get('project_path', '')}"

        # 提交异步任务
        task_func = (
            build_kb_task if task_type == "build_knowledge_base" else
            build_thirdparty_task if task_type == "build_thirdparty_knowledge_base" else
            init_project_task if task_type == "init_project_knowledge_base" else
            build_embedding_task if task_type == "build_embedding" else
            build_doc_task
        )
        
        task_id = task_manager.submit_task(
            name=task_name,
            func=task_func,
            progress_callback=progress_callback if show_progress else None,
            dedup_key=dedup_key,
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
    获取任务状态（支持长轮询）

    Args:
        arguments: 包含以下参数:
            - task_id: 任务ID (必需)
            - long_poll_seconds: 长轮询等待秒数（可选，默认0即立即返回。MCP请求通道有超时限制，建议≤30秒，超时改用短轮询）

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
    
    # 长轮询：等待进度变化再返回
    long_poll = arguments.get("long_poll_seconds", 0)
    if long_poll > 0:
        task_info = task_manager.wait_for_progress_change(task_id, long_poll)
    else:
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


async def cancel_task(arguments: Any) -> CallToolResult:
    """
    取消任务

    Args:
        arguments: 包含以下参数:
            - task_id: 任务ID (必需)

    Returns:
        操作结果
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供任务ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    success = task_manager.cancel_task(task_id)

    if success:
        return CallToolResult(content=[{"type": "text", "text": f"任务 {task_id} 已取消"}])
    else:
        return CallToolResult(
            content=[{"type": "text", "text": f"无法取消任务 {task_id}（任务不存在或已完成）"}],
            isError=True
        )


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
