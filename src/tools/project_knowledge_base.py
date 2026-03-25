"""
项目知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供项目知识库查询和管理的 MCP 工具
"""

from typing import Any, Dict, Optional, Callable
from mcp.types import CallToolResult
from pathlib import Path

from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
from ..utils.logger import get_logger
from ..utils.progress_tracker import ProgressInfo

logger = get_logger(__name__)

# 项目知识库实例缓存
_project_kb_cache: Dict[str, ProjectKnowledgeBase] = {}


def get_project_kb(project_path: str, progress_callback: Optional[Callable[[ProgressInfo], None]] = None) -> ProjectKnowledgeBase:
    """
    获取或创建项目知识库实例

    Args:
        project_path: 项目文件路径
        progress_callback: 进度回调函数

    Returns:
        项目知识库实例
    """
    project_path = str(Path(project_path).resolve())

    if project_path not in _project_kb_cache:
        _project_kb_cache[project_path] = ProjectKnowledgeBase(project_path, progress_callback)
        _project_kb_cache[project_path].load_knowledge_bases()

    return _project_kb_cache[project_path]


async def init_project_knowledge_base(arguments: Any) -> CallToolResult:
    """
    初始化项目知识库

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (.dproj 或 .dpr) (必需)
            - build_thirdparty: 是否构建三方库知识库 (可选,默认 true)
            - build_project: 是否构建项目源码知识库 (可选,默认 true)
            - force_rebuild: 是否强制重建 (可选,默认 false)
            - show_progress: 是否显示进度 (可选,默认 true)

    Returns:
        初始化结果
    """
    project_path = arguments.get("project_path")
    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    # 检查项目文件是否存在
    if not Path(project_path).exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"项目文件不存在: {project_path}"}],
            isError=True
        )

    build_thirdparty = arguments.get("build_thirdparty", True)
    build_project = arguments.get("build_project", True)
    force_rebuild = arguments.get("force_rebuild", False)
    show_progress = arguments.get("show_progress", True)

    # 创建进度回调
    progress_messages = []
    def progress_callback(progress: ProgressInfo):
        if show_progress:
            msg = f"进度: {progress.current}/{progress.total} ({progress.percentage:.1f}%) | "
            msg += f"速度: {progress.speed:.1f}项/秒 | "
            msg += f"已用: {progress.elapsed_time:.1f}秒 | "
            msg += f"剩余: {progress.estimated_remaining:.1f}秒 | "
            msg += f"{progress.message}"
            progress_messages.append(msg)
            logger.info(msg)

    try:
        project_kb = get_project_kb(project_path, progress_callback if show_progress else None)

        output = f"项目知识库初始化: {project_kb.project_name}\n\n"

        # 构建三方库知识库
        if build_thirdparty:
            logger.info("构建三方库知识库...")
            if project_kb.build_thirdparty_knowledge_base(force_rebuild=force_rebuild):
                output += "✓ 三方库知识库构建成功\n"
            else:
                output += "⚠ 三方库知识库构建跳过 (未找到三方库路径)\n"

        # 构建项目源码知识库
        if build_project:
            logger.info("构建项目源码知识库...")
            if project_kb.build_project_knowledge_base(force_rebuild=force_rebuild):
                output += "✓ 项目源码知识库构建成功\n"
            else:
                output += "✗ 项目源码知识库构建失败\n"

        # 获取统计信息
        stats = project_kb.get_statistics()
        output += "\n知识库统计:\n"

        if stats["project"]:
            output += f"  项目源码: {stats['project']['files']} 文件, "
            output += f"{stats['project']['classes']} 类, "
            output += f"{stats['project']['functions']} 函数\n"

        if stats["thirdparty"]:
            output += f"  三方库: {stats['thirdparty']['files']} 文件, "
            output += f"{stats['thirdparty']['classes']} 类, "
            output += f"{stats['thirdparty']['functions']} 函数\n"

        output += f"\n知识库位置: {project_kb.kb_dir}"

        # 添加进度信息
        if show_progress and progress_messages:
            output += f"\n\n构建进度 (最近10条):\n"
            for msg in progress_messages[-10:]:
                output += f"  {msg}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"初始化项目知识库失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"初始化项目知识库失败: {str(e)}"}],
            isError=True
        )


async def search_project_class(arguments: Any) -> CallToolResult:
    """
    在项目中搜索类

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (必需)
            - class_name: 类名 (必需)
            - search_in: 搜索范围 "project", "thirdparty", "all" (可选,默认 "all")

    Returns:
        搜索结果
    """
    project_path = arguments.get("project_path")
    class_name = arguments.get("class_name")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    if not class_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供类名"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.search_class(class_name, search_in=search_in)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到类 '{class_name}'"}]
            )

        # 格式化结果
        output = f"找到 {len(results)} 个类 '{class_name}':\n\n"
        for i, result in enumerate(results, 1):
            source = result.get('_source', 'unknown')
            output += f"{i}. [{source}] {result['file']['path']}\n"
            output += f"   类名: {result['class']['name']}\n"
            output += f"   基类: {result['class']['base_class']}\n"
            output += f"   行号: {result['class']['line']}\n"
            output += f"   完整路径: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"搜索类失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索类时出错: {str(e)}"}],
            isError=True
        )


async def search_project_function(arguments: Any) -> CallToolResult:
    """
    在项目中搜索函数

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (必需)
            - function_name: 函数名 (必需)
            - search_in: 搜索范围 "project", "thirdparty", "all" (可选,默认 "all")

    Returns:
        搜索结果
    """
    project_path = arguments.get("project_path")
    function_name = arguments.get("function_name")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    if not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供函数名"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.search_function(function_name, search_in=search_in)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到函数 '{function_name}'"}]
            )

        # 格式化结果
        output = f"找到 {len(results)} 个函数 '{function_name}':\n\n"
        for i, result in enumerate(results, 1):
            source = result.get('_source', 'unknown')
            output += f"{i}. [{source}] {result['file']['path']}\n"
            output += f"   函数名: {result['function']['name']}\n"
            output += f"   类型: {result['function']['type']}\n"
            output += f"   行号: {result['function']['line']}\n"
            output += f"   完整路径: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"搜索函数失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索函数时出错: {str(e)}"}],
            isError=True
        )


async def semantic_search_project(arguments: Any) -> CallToolResult:
    """
    在项目中进行语义搜索

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (必需)
            - query: 搜索查询 (必需)
            - top_k: 返回结果数量 (可选,默认 10)
            - search_in: 搜索范围 "project", "thirdparty", "all" (可选,默认 "all")

    Returns:
        搜索结果
    """
    project_path = arguments.get("project_path")
    query = arguments.get("query")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供搜索查询"}],
            isError=True
        )

    top_k = arguments.get("top_k", 10)
    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.semantic_search(query, top_k=top_k, search_in=search_in)

        if not results["classes"] and not results["functions"]:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到与 '{query}' 相关的内容"}]
            )

        # 格式化结果
        output = f"语义搜索 '{query}' 的结果:\n\n"

        if results["classes"]:
            output += f"相关的类 (Top {len(results['classes'])}):\n"
            for item in results["classes"][:5]:
                result = item["data"]
                output += f"  - [{item['source']}] {result['class']['name']} (相似度: {item['score']:.3f})\n"
                output += f"    位置: {result['file']['path']}\n"
                output += f"    基类: {result['class']['base_class']}\n"
                output += f"    行号: {result['class']['line']}\n\n"

        if results["functions"]:
            output += f"相关的函数 (Top {len(results['functions'])}):\n"
            for item in results["functions"][:5]:
                result = item["data"]
                output += f"  - [{item['source']}] {result['function']['name']} (相似度: {item['score']:.3f})\n"
                output += f"    位置: {result['file']['path']}\n"
                output += f"    类型: {result['function']['type']}\n"
                output += f"    行号: {result['function']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"语义搜索失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"语义搜索时出错: {str(e)}"}],
            isError=True
        )


async def get_project_kb_stats(arguments: Any) -> CallToolResult:
    """
    获取项目知识库统计信息

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (必需)

    Returns:
        统计信息
    """
    project_path = arguments.get("project_path")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    try:
        project_kb = get_project_kb(project_path)
        stats = project_kb.get_statistics()

        output = f"项目知识库统计信息: {project_kb.project_name}\n\n"

        if stats["project"]:
            output += "项目源码:\n"
            output += f"  - 文件数: {stats['project']['files']}\n"
            output += f"  - 类数量: {stats['project']['classes']}\n"
            output += f"  - 函数数量: {stats['project']['functions']}\n"
            output += f"  - 数据库大小: {stats['project']['database_size_mb']:.2f} MB\n\n"
        else:
            output += "项目源码: 未构建\n\n"

        if stats["thirdparty"]:
            output += "三方库:\n"
            output += f"  - 文件数: {stats['thirdparty']['files']}\n"
            output += f"  - 类数量: {stats['thirdparty']['classes']}\n"
            output += f"  - 函数数量: {stats['thirdparty']['functions']}\n"
            output += f"  - 数据库大小: {stats['thirdparty']['database_size_mb']:.2f} MB\n\n"
        else:
            output += "三方库: 未构建\n\n"

        # 显示三方库路径
        if project_kb.metadata.get("thirdparty_paths"):
            output += "三方库路径:\n"
            for path in project_kb.metadata["thirdparty_paths"]:
                output += f"  - {path}\n"

        output += f"\n知识库位置: {project_kb.kb_dir}"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"获取统计信息时出错: {str(e)}"}],
            isError=True
        )


async def get_thirdparty_paths(arguments: Any) -> CallToolResult:
    """
    获取项目的三方库路径

    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (必需)

    Returns:
        三方库路径列表
    """
    project_path = arguments.get("project_path")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )

    try:
        project_kb = get_project_kb(project_path)
        paths = project_kb.get_thirdparty_paths_from_dproj()

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "未找到三方库路径"}]
            )

        output = f"项目的三方库路径 ({len(paths)} 个):\n\n"
        for i, path in enumerate(paths, 1):
            output += f"{i}. {path}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"获取三方库路径失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"获取三方库路径时出错: {str(e)}"}],
            isError=True
        )
