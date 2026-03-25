"""
Delphi 帮助文档知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供帮助文档知识库查询和管理的 MCP 工具
支持分步骤构建：解压 CHM -> 扫描 HTML -> 构建索引
"""

from typing import Any, List, Optional, Callable
from datetime import datetime
from mcp.types import CallToolResult

from ..services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
from ..services.knowledge_base.async_task_manager import get_task_manager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局帮助文档知识库实例
_help_kb = None


def get_help_knowledge_base() -> DelphiHelpKnowledgeBase:
    """获取帮助文档知识库实例"""
    global _help_kb
    if _help_kb is None:
        _help_kb = DelphiHelpKnowledgeBase()
    return _help_kb


def _build_kb_task(help_names: Optional[List[str]] = None,
                   max_files_per_help: Optional[int] = None,
                   save_markdown: bool = False,
                   _progress_callback: Optional[Callable] = None,
                   _task_id: Optional[str] = None) -> bool:
    """
    后台构建知识库任务

    Args:
        help_names: 要构建的帮助文件列表
        max_files_per_help: 每个帮助文件最大处理文档数
        save_markdown: 是否保存为 Markdown 文件（默认False，提升性能）
        _progress_callback: 进度回调函数（由任务管理器注入）
        _task_id: 任务ID（用于取消检查）

    Returns:
        是否成功
    """
    help_kb = get_help_knowledge_base()
    task_manager = get_task_manager()

    # 定义取消检查函数
    def is_cancelled() -> bool:
        if _task_id:
            return task_manager.is_task_cancelled(_task_id)
        return False

    # 定义内部进度回调，将步骤信息传递给任务管理器
    def internal_progress_callback(stage: str, current: int, total: int, message: str):
        # 检查是否被取消
        if is_cancelled():
            raise KeyboardInterrupt("任务已被用户取消")

        if _progress_callback:
            # 映射阶段到步骤信息
            stage_map = {
                'extract': ('解压CHM文件', 1, 4),
                'scan': ('扫描HTML文件', 2, 4),
                'index': ('构建向量索引', 3, 4),
                'cleanup': ('清理临时文件', 4, 4)
            }
            step_name, step_idx, total_steps = stage_map.get(stage, (stage, 1, 4))

            # 计算总体进度
            stage_progress = (current / total * 100) if total > 0 else 0
            overall_progress = ((step_idx - 1) * 25 + stage_progress * 0.25)

            # 调用进度回调
            _progress_callback(
                overall_progress,
                f"[步骤{step_idx}/{total_steps}] {step_name}: {message}"
            )

    try:
        return help_kb.build_knowledge_base(
            help_names=help_names,
            max_files_per_help=max_files_per_help,
            save_markdown=save_markdown,
            progress_callback=internal_progress_callback if _progress_callback else None,
            is_cancelled_check=is_cancelled
        )
    except KeyboardInterrupt:
        logger.info(f"任务 {_task_id} 已被取消")
        return False


async def build_help_knowledge_base(arguments: Any) -> CallToolResult:
    """
    构建 Delphi 帮助文档知识库（支持分步骤和异步模式）

    Args:
        arguments: 包含以下参数:
            - force_rebuild: 是否强制重建 (可选,默认 false)
            - async_mode: 是否使用异步模式 (可选,默认 true)
            - help_names: 要构建的帮助文件列表 (可选,如 ['fmx', 'vcl'], 默认全部)
            - max_files_per_help: 每个帮助文件最大处理文档数 (可选,用于测试)
            - incremental: 是否使用增量构建(跳过解压) (可选,默认 false)
            - source_dir: 外部源目录路径 (可选,用于增量构建时指定外部files目录)
            - save_markdown: 是否保存为 Markdown 文件 (可选,默认 false, 提升性能)

    Returns:
        构建结果或任务信息
    """
    force_rebuild = arguments.get("force_rebuild", False)
    async_mode = arguments.get("async_mode", True)
    help_names = arguments.get("help_names")  # 如 ['fmx', 'vcl']
    max_files_per_help = arguments.get("max_files_per_help")
    incremental = arguments.get("incremental", False)
    source_dir = arguments.get("source_dir")
    save_markdown = arguments.get("save_markdown", False)  # 默认不转换Markdown，提升性能

    try:
        help_kb = get_help_knowledge_base()

        # 检查是否已存在
        if not force_rebuild and help_kb.is_kb_exists() and not incremental:
            stats = help_kb.get_statistics()
            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"帮助文档知识库已存在，无需重建。\n\n"
                            f"统计信息:\n"
                            f"- 文档数量: {stats.get('total_documents', 0)}\n"
                            f"- 类定义: {stats.get('total_classes', 0)}\n"
                            f"- 函数定义: {stats.get('total_functions', 0)}\n"
                            f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n\n"
                            f"如需强制重建，请设置 force_rebuild=true\n"
                            f"如需增量构建(跳过解压)，请设置 incremental=true"
                }]
            )

        if async_mode:
            # 异步模式：提交后台任务
            task_manager = get_task_manager()
            
            # 检查是否已有正在运行的构建任务
            existing_tasks = task_manager.get_all_tasks()
            for task_id, task_info in existing_tasks.items():
                if task_info.name == "build_help_kb" and task_info.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    return CallToolResult(
                        content=[{
                            "type": "text",
                            "text": f"帮助文档知识库构建任务已在进行中\n\n"
                                    f"任务ID: {task_info.task_id}\n"
                                    f"状态: {task_info.status.value}\n"
                                    f"进度: {task_info.progress:.1f}%\n"
                                    f"消息: {task_info.message}\n\n"
                                    f"请使用 get_task_status 工具查询进度"
                        }]
                    )
            
            # 提交新任务 - 只传递需要的参数
            task_kwargs = {}
            if help_names:
                task_kwargs["help_names"] = help_names
            if max_files_per_help:
                task_kwargs["max_files_per_help"] = max_files_per_help
            if save_markdown:
                task_kwargs["save_markdown"] = save_markdown

            task_id = task_manager.submit_task(
                "build_help_kb",
                _build_kb_task,
                **task_kwargs
            )

            build_mode = "增量构建" if incremental else "完整构建"
            help_info = f"帮助文件: {', '.join(help_names)}" if help_names else "全部帮助文件"
            limit_info = f"\n每个帮助文件最多处理 {max_files_per_help} 个文档" if max_files_per_help else ""

            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"帮助文档知识库{build_mode}任务已提交到后台\n\n"
                            f"任务ID: {task_id}\n"
                            f"状态: pending\n"
                            f"模式: {build_mode}\n"
                            f"{help_info}{limit_info}\n\n"
                            f"构建帮助文档知识库需要较长时间（可能需要几分钟），任务已在后台运行。\n"
                            f"请使用 get_task_status 工具查询构建进度。\n\n"
                            f"示例:\n"
                            f'  get_task_status({{"task_id": "{task_id}"}})'
                }]
            )
        else:
            # 同步模式：直接构建（可能超时）
            logger.info("同步模式构建帮助文档知识库...")
            
            if incremental:
                success = help_kb.build_knowledge_base_incremental(
                    help_names=help_names,
                    max_files_per_help=max_files_per_help,
                    source_dir=source_dir,
                    save_markdown=save_markdown
                )
            else:
                success = help_kb.build_knowledge_base(
                    help_names=help_names,
                    max_files_per_help=max_files_per_help,
                    save_markdown=save_markdown
                )

            if success:
                stats = help_kb.get_statistics()
                return CallToolResult(
                    content=[{
                        "type": "text",
                        "text": f"帮助文档知识库构建成功!\n\n"
                                f"统计信息:\n"
                                f"- 文档数量: {stats.get('total_documents', 0)}\n"
                                f"- 类定义: {stats.get('total_classes', 0)}\n"
                                f"- 函数定义: {stats.get('total_functions', 0)}\n"
                                f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB"
                    }]
                )
            else:
                return CallToolResult(
                    content=[{"type": "text", "text": "帮助文档知识库构建失败"}],
                    isError=True
                )

    except Exception as e:
        logger.error(f"构建帮助文档知识库失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"构建帮助文档知识库时出错: {str(e)}"}],
            isError=True
        )


async def extract_help_chm(arguments: Any) -> CallToolResult:
    """
    解压 Delphi 帮助文档 CHM 文件（分步骤构建第1步）

    Args:
        arguments: 包含以下参数:
            - help_names: 要解压的帮助文件列表 (可选,如 ['fmx', 'vcl'], 默认全部)

    Returns:
        解压结果
    """
    help_names = arguments.get("help_names")

    try:
        help_kb = get_help_knowledge_base()

        if not help_kb.delphi_help_dir:
            return CallToolResult(
                content=[{"type": "text", "text": "未找到 Delphi 帮助目录"}],
                isError=True
            )

        logger.info(f"开始解压 CHM 文件: {help_names or '全部'}")
        
        results = help_kb.extract_all_chm(help_names=help_names)

        # 格式化结果
        output = "CHM 文件解压结果:\n"
        output += "=" * 50 + "\n\n"
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        for name, success in results.items():
            desc = help_kb.HELP_FILES.get(name, name)
            status = "✅ 成功" if success else "❌ 失败"
            output += f"{name}: {status} ({desc})\n"
        
        output += f"\n总计: {success_count}/{total_count} 个文件解压成功"
        
        if success_count > 0:
            output += "\n\n解压后的文件位于: " + str(help_kb.kb_dir / "files")
            output += "\n\n下一步可以使用 scan_help_html 扫描HTML文件"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"解压 CHM 文件失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"解压 CHM 文件时出错: {str(e)}"}],
            isError=True
        )


async def scan_help_html(arguments: Any) -> CallToolResult:
    """
    扫描已解压的 HTML 文件（分步骤构建第2步）

    Args:
        arguments: 包含以下参数:
            - help_names: 要扫描的帮助文件列表 (可选,如 ['fmx', 'vcl'], 默认全部)
            - max_files_per_help: 每个帮助文件最大处理文档数 (可选,用于测试)
            - source_dir: 外部源目录路径 (可选,默认使用 kb_dir/files)
            - save_markdown: 是否保存为 Markdown 文件 (可选,默认 false, 提升性能)

    Returns:
        扫描结果
    """
    help_names = arguments.get("help_names")
    max_files_per_help = arguments.get("max_files_per_help")
    source_dir = arguments.get("source_dir")
    save_markdown = arguments.get("save_markdown", False)  # 默认不转换Markdown，提升性能

    try:
        help_kb = get_help_knowledge_base()

        # 确定源目录
        if source_dir:
            extracted_dir = source_dir
        else:
            extracted_dir = str(help_kb.kb_dir / "files")

        if not help_names:
            # 自动发现已解压的目录
            help_names = []
            extracted_path = help_kb.kb_dir / "files"
            if extracted_path.exists():
                for item in extracted_path.iterdir():
                    if item.is_dir() and item.name in help_kb.HELP_FILES:
                        help_names.append(item.name)
            
            if not help_names:
                return CallToolResult(
                    content=[{
                        "type": "text", 
                        "text": "未找到已解压的帮助文档目录。\n\n"
                                "请先使用 extract_help_chm 工具解压 CHM 文件。"
                    }],
                    isError=True
                )

        all_documents = []
        output = "HTML 文件扫描结果:\n"
        output += "=" * 50 + "\n\n"

        for help_name in help_names:
            desc = help_kb.HELP_FILES.get(help_name, help_name)
            output += f"扫描 {desc} ({help_name})...\n"
            
            documents = help_kb.scan_extracted_directory(
                help_name=help_name,
                max_files=max_files_per_help,
                source_dir=extracted_dir,
                save_markdown=save_markdown
            )
            
            all_documents.extend(documents)
            output += f"  提取到 {len(documents)} 个文档\n"

            if documents:
                classes_count = sum(len(d.get('classes', [])) for d in documents)
                functions_count = sum(len(d.get('functions', [])) for d in documents)
                properties_count = sum(len(d.get('properties', [])) for d in documents)
                events_count = sum(len(d.get('events', [])) for d in documents)
                interfaces_count = sum(len(d.get('interfaces', [])) for d in documents)
                types_count = sum(len(d.get('types', [])) for d in documents)
                code_examples_count = sum(len(d.get('code_examples', [])) for d in documents)
                output += f"  - 类定义: {classes_count}\n"
                output += f"  - 接口定义: {interfaces_count}\n"
                output += f"  - 类型定义: {types_count}\n"
                output += f"  - 函数定义: {functions_count}\n"
                output += f"  - 属性定义: {properties_count}\n"
                output += f"  - 事件定义: {events_count}\n"
                output += f"  - 代码示例: {code_examples_count}\n"
            output += "\n"

        total_classes = sum(len(d.get('classes', [])) for d in all_documents)
        total_functions = sum(len(d.get('functions', [])) for d in all_documents)
        total_properties = sum(len(d.get('properties', [])) for d in all_documents)
        total_events = sum(len(d.get('events', [])) for d in all_documents)
        total_interfaces = sum(len(d.get('interfaces', [])) for d in all_documents)
        total_types = sum(len(d.get('types', [])) for d in all_documents)
        total_code_examples = sum(len(d.get('code_examples', [])) for d in all_documents)

        output += f"总计: {len(all_documents)} 个文档\n"
        output += f"  - 类定义: {total_classes}\n"
        output += f"  - 接口定义: {total_interfaces}\n"
        output += f"  - 类型定义: {total_types}\n"
        output += f"  - 函数定义: {total_functions}\n"
        output += f"  - 属性定义: {total_properties}\n"
        output += f"  - 事件定义: {total_events}\n"
        output += f"  - 代码示例: {total_code_examples}\n"
        output += "\n下一步可以使用 build_help_kb_index 构建向量索引"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"扫描 HTML 文件失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"扫描 HTML 文件时出错: {str(e)}"}],
            isError=True
        )


async def build_help_kb_index(arguments: Any) -> CallToolResult:
    """
    构建帮助文档向量索引（分步骤构建第3步）

    Args:
        arguments: 包含以下参数:
            - help_names: 要构建的帮助文件列表 (可选,如 ['fmx', 'vcl'], 默认全部)
            - max_files_per_help: 每个帮助文件最大处理文档数 (可选,用于测试)
            - source_dir: 外部源目录路径 (可选,默认使用 kb_dir/files)
            - async_mode: 是否使用异步模式 (可选,默认 true)
            - save_markdown: 是否保存为 Markdown 文件 (可选,默认 false, 提升性能)

    Returns:
        构建结果
    """
    help_names = arguments.get("help_names")
    max_files_per_help = arguments.get("max_files_per_help")
    source_dir = arguments.get("source_dir")
    async_mode = arguments.get("async_mode", True)
    save_markdown = arguments.get("save_markdown", False)  # 默认不转换Markdown，提升性能

    try:
        help_kb = get_help_knowledge_base()

        if async_mode:
            # 异步模式
            task_manager = get_task_manager()
            
            task_id = task_manager.submit_task(
                "build_help_kb_index",
                lambda: help_kb.build_knowledge_base_incremental(
                    help_names=help_names,
                    max_files_per_help=max_files_per_help,
                    source_dir=source_dir,
                    save_markdown=save_markdown
                )
            )

            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"帮助文档向量索引构建任务已提交到后台\n\n"
                            f"任务ID: {task_id}\n"
                            f"状态: pending\n\n"
                            f"请使用 get_task_status 工具查询构建进度。\n\n"
                            f"示例:\n"
                            f'  get_task_status({{"task_id": "{task_id}"}})'
                }]
            )
        else:
            # 同步模式
            success = help_kb.build_knowledge_base_incremental(
                help_names=help_names,
                max_files_per_help=max_files_per_help,
                source_dir=source_dir,
                save_markdown=save_markdown
            )

            if success:
                stats = help_kb.get_statistics()
                return CallToolResult(
                    content=[{
                        "type": "text",
                        "text": f"帮助文档向量索引构建成功!\n\n"
                                f"统计信息:\n"
                                f"- 文档数量: {stats.get('total_documents', 0)}\n"
                                f"- 类定义: {stats.get('total_classes', 0)}\n"
                                f"- 函数定义: {stats.get('total_functions', 0)}\n"
                                f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n\n"
                                f"现在可以使用 search_help 工具搜索帮助文档了。"
                    }]
                )
            else:
                return CallToolResult(
                    content=[{"type": "text", "text": "帮助文档向量索引构建失败"}],
                    isError=True
                )

    except Exception as e:
        logger.error(f"构建向量索引失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"构建向量索引时出错: {str(e)}"}],
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

    try:
        task_manager = get_task_manager()
        task_info = task_manager.get_task_info(task_id)

        if not task_info:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到任务: {task_id}"}],
                isError=True
            )

        # 格式化状态信息
        status_text = f"任务状态: {task_info.task_id}\n"
        status_text += f"=" * 50 + "\n\n"
        status_text += f"名称: {task_info.name}\n"
        status_text += f"状态: {task_info.status.value}\n"
        status_text += f"进度: {task_info.progress:.1f}%\n"

        # 显示步骤信息
        if task_info.current_step:
            step_info = f"当前步骤: {task_info.current_step}"
            if task_info.total_steps > 0:
                step_info = f"当前步骤: [{task_info.step_index}/{task_info.total_steps}] {task_info.current_step}"
            status_text += f"{step_info}\n"

        status_text += f"消息: {task_info.message}\n\n"

        if task_info.started_at:
            status_text += f"开始时间: {task_info.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

            # 计算已运行时间和预计剩余时间
            if task_info.status == TaskStatus.RUNNING:
                elapsed = (datetime.now() - task_info.started_at).total_seconds()
                status_text += f"已运行: {elapsed:.1f} 秒\n"

                # 预计剩余时间
                if task_info.progress > 0:
                    total_estimated = elapsed / (task_info.progress / 100)
                    remaining = total_estimated - elapsed
                    if remaining > 0:
                        if remaining > 60:
                            status_text += f"预计剩余: {remaining/60:.1f} 分钟\n"
                        else:
                            status_text += f"预计剩余: {remaining:.1f} 秒\n"

        if task_info.completed_at:
            status_text += f"完成时间: {task_info.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            duration = (task_info.completed_at - task_info.started_at).total_seconds() if task_info.started_at else 0
            status_text += f"耗时: {duration:.1f} 秒\n"

        if task_info.error:
            status_text += f"\n错误: {task_info.error}\n"

        if task_info.status == TaskStatus.COMPLETED:
            status_text += f"\n✅ 任务已完成！\n"
            if task_info.name in ["build_help_kb", "build_help_kb_index"]:
                status_text += f"现在可以使用 search_help 工具搜索帮助文档了。\n"
        elif task_info.status == TaskStatus.FAILED:
            status_text += f"\n❌ 任务失败\n"
        elif task_info.status == TaskStatus.RUNNING:
            status_text += f"\n⏳ 任务正在运行中，请稍后再次查询...\n"
        elif task_info.status == TaskStatus.PENDING:
            status_text += f"\n⏳ 任务等待中...\n"

        return CallToolResult(content=[{"type": "text", "text": status_text}])

    except Exception as e:
        logger.error(f"获取任务状态失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"获取任务状态时出错: {str(e)}"}],
            isError=True
        )


async def list_tasks(arguments: Any) -> CallToolResult:
    """
    列出所有任务

    Args:
        arguments: 无参数

    Returns:
        任务列表
    """
    try:
        task_manager = get_task_manager()
        tasks = task_manager.get_all_tasks()

        if not tasks:
            return CallToolResult(
                content=[{"type": "text", "text": "当前没有任务"}]
            )

        # 格式化任务列表
        output = "任务列表:\n"
        output += "=" * 60 + "\n\n"

        for task_info in sorted(tasks.values(), key=lambda x: x.created_at, reverse=True):
            output += f"ID: {task_info.task_id}\n"
            output += f"  名称: {task_info.name}\n"
            output += f"  状态: {task_info.status.value}\n"
            output += f"  进度: {task_info.progress:.1f}%\n"
            output += f"  创建时间: {task_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            if task_info.message:
                output += f"  消息: {task_info.message}\n"
            output += "\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"列出任务失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"列出任务时出错: {str(e)}"}],
            isError=True
        )


async def cancel_task(arguments: Any) -> CallToolResult:
    """
    取消任务

    Args:
        arguments: 包含以下参数:
            - task_id: 任务ID (必需)

    Returns:
        取消结果
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供任务ID"}],
            isError=True
        )

    try:
        task_manager = get_task_manager()
        success = task_manager.cancel_task(task_id)

        if success:
            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"任务 {task_id} 已标记为取消。\n\n"
                            f"注意：正在执行的操作可能需要一些时间才能停止。\n"
                            f"请使用 get_task_status 查询最终状态。"
                }]
            )
        else:
            task_info = task_manager.get_task_info(task_id)
            if not task_info:
                return CallToolResult(
                    content=[{"type": "text", "text": f"未找到任务: {task_id}"}],
                    isError=True
                )
            else:
                return CallToolResult(
                    content=[{
                        "type": "text",
                        "text": f"无法取消任务 {task_id}\n\n"
                                f"当前状态: {task_info.status.value}\n"
                                f"只有等待中或运行中的任务才能取消。"
                    }],
                    isError=True
                )

    except Exception as e:
        logger.error(f"取消任务失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"取消任务时出错: {str(e)}"}],
            isError=True
        )


async def search_help(arguments: Any) -> CallToolResult:
    """
    搜索 Delphi 帮助文档

    Args:
        arguments: 包含以下参数:
            - query: 搜索查询 (必需)
            - top_k: 返回结果数量 (可选,默认 10)

    Returns:
        搜索结果
    """
    query = arguments.get("query")
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供搜索查询"}],
            isError=True
        )

    top_k = arguments.get("top_k", 10)

    try:
        help_kb = get_help_knowledge_base()
        
        # 检查知识库是否存在
        if not help_kb.is_kb_exists():
            return CallToolResult(
                content=[{
                    "type": "text", 
                    "text": "帮助文档知识库尚未构建。\n\n"
                            "请先使用以下工具之一构建知识库:\n"
                            "1. build_help_knowledge_base - 完整构建（解压+扫描+索引）\n"
                            "2. extract_help_chm -> scan_help_html -> build_help_kb_index - 分步骤构建\n\n"
                            "注意：构建过程需要几分钟时间，建议使用异步模式。"
                }],
                isError=True
            )
        
        results = help_kb.search(query, top_k=top_k)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到与 '{query}' 相关的帮助文档"}]
            )

        # 格式化结果
        output = f"帮助文档搜索 '{query}' 的结果:\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. [{result['type'].upper()}] {result['name']}"
            if 'score' in result:
                output += f" (相似度: {result['score']:.3f})"
            output += "\n"
            
            if 'description' in result and result['description']:
                desc = result['description']
                if len(desc) > 150:
                    desc = desc[:150] + "..."
                output += f"   描述: {desc}\n"
            
            if 'file_path' in result:
                output += f"   文件: {result['file_path']}\n"
            
            output += "\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"搜索帮助文档失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索帮助文档时出错: {str(e)}"}],
            isError=True
        )


async def get_help_kb_stats(arguments: Any) -> CallToolResult:
    """
    获取帮助文档知识库统计信息

    Args:
        arguments: 无参数

    Returns:
        统计信息
    """
    try:
        help_kb = get_help_knowledge_base()
        
        if not help_kb.is_kb_exists():
            return CallToolResult(
                content=[{
                    "type": "text", 
                    "text": "帮助文档知识库尚未构建。\n\n"
                            "请先使用 build_help_knowledge_base 工具构建知识库。"
                }]
            )
        
        stats = help_kb.get_statistics()

        output = "Delphi 帮助文档知识库统计信息:\n\n"
        output += f"- 文档数量: {stats.get('total_documents', 0)}\n"
        output += f"- 类定义: {stats.get('total_classes', 0)}\n"
        output += f"- 接口定义: {stats.get('total_interfaces', 0)}\n"
        output += f"- 类型定义: {stats.get('total_types', 0)}\n"
        output += f"- 函数定义: {stats.get('total_functions', 0)}\n"
        output += f"- 属性定义: {stats.get('total_properties', 0)}\n"
        output += f"- 事件定义: {stats.get('total_events', 0)}\n"
        output += f"- 代码示例: {stats.get('total_code_examples', 0)}\n"
        output += f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n"
        output += f"\n知识库位置: {help_kb.kb_dir}"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"获取统计信息时出错: {str(e)}"}],
            isError=True
        )
