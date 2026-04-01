"""
Delphi 知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供知识库查询和管理的 MCP 工具
"""

from typing import Any, Optional, Callable
from mcp.types import CallToolResult

# 全局知识库服务实例
kb_service = None


def set_knowledge_base_service(service):
    """设置知识库服务实例"""
    global kb_service
    kb_service = service


async def build_knowledge_base(arguments: Any) -> CallToolResult:
    """
    构建 Delphi 知识库

    Args:
        arguments: 包含以下参数:
            - version: Delphi 版本 (可选)
            - force_rebuild: 是否强制重建 (可选,默认 false)
            - show_progress: 是否显示进度 (可选,默认 true)

    Returns:
        构建结果
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    version = arguments.get("version")
    force_rebuild = arguments.get("force_rebuild", False)
    show_progress = arguments.get("show_progress", True)

    # 创建进度回调
    progress_messages = []
    def progress_callback(progress):
        if show_progress:
            from ..utils.progress_tracker import ProgressCallback
            callback = ProgressCallback(prefix="Delphi知识库")
            msg = callback.tracker.get_progress_text(progress)
            progress_messages.append(msg)

    try:
        # 更新服务的进度回调
        kb_service.progress_callback = progress_callback if show_progress else None
        success = kb_service.build_knowledge_base(version=version, force_rebuild=force_rebuild)

        if success:
            stats = kb_service.get_statistics()
            result_text = f"知识库构建成功!\n\n统计信息:\n"
            result_text += f"- 类数量: {stats.get('classes', 0)}\n"
            result_text += f"- 函数数量: {stats.get('functions', 0)}\n"
            result_text += f"- 文件数量: {stats.get('files', 0)}\n"
            result_text += f"- 词汇表大小: {stats.get('vocabulary_size', 0)}\n"
            result_text += f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB"

            # 添加进度信息
            if show_progress and progress_messages:
                result_text += f"\n\n构建进度 (最近10条):\n"
                for msg in progress_messages[-10:]:
                    result_text += f"  {msg}\n"

            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": result_text
                }]
            )
        else:
            return CallToolResult(
                content=[{"type": "text", "text": "知识库构建失败"}],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"构建知识库时出错: {str(e)}"}],
            isError=True
        )


async def search_class(arguments: Any) -> CallToolResult:
    """
    搜索 Delphi 类

    Args:
        arguments: 包含以下参数:
            - class_name: 类名 (必需)

    Returns:
        搜索结果
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    class_name = arguments.get("class_name")
    if not class_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供类名"}],
            isError=True
        )

    try:
        results = kb_service.search_by_class_name(class_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到类 '{class_name}'"}]
            )

        # 格式化结果
        output = f"找到 {len(results)} 个类 '{class_name}':\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. 文件: {result['file']['path']}\n"
            output += f"   类名: {result['class']['name']}\n"
            output += f"   基类: {result['class']['base_class']}\n"
            output += f"   行号: {result['class']['line']}\n"
            output += f"   完整路径: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索类时出错: {str(e)}"}],
            isError=True
        )


async def search_function(arguments: Any) -> CallToolResult:
    """
    搜索 Delphi 函数

    Args:
        arguments: 包含以下参数:
            - function_name: 函数名 (必需)

    Returns:
        搜索结果
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    function_name = arguments.get("function_name")
    if not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供函数名"}],
            isError=True
        )

    try:
        results = kb_service.search_by_function_name(function_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到函数 '{function_name}'"}]
            )

        # 格式化结果
        output = f"找到 {len(results)} 个函数 '{function_name}':\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. 文件: {result['file']['path']}\n"
            output += f"   函数名: {result['function']['name']}\n"
            output += f"   类型: {result['function']['type']}\n"
            output += f"   行号: {result['function']['line']}\n"
            output += f"   完整路径: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索函数时出错: {str(e)}"}],
            isError=True
        )


async def semantic_search(arguments: Any) -> CallToolResult:
    """
    语义搜索 Delphi 代码

    Args:
        arguments: 包含以下参数:
            - query: 搜索查询 (必需)
            - top_k: 返回结果数量 (可选,默认 10)

    Returns:
        搜索结果
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    query = arguments.get("query")
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供搜索查询"}],
            isError=True
        )

    top_k = arguments.get("top_k", 10)

    try:
        # 搜索类和函数
        class_results = kb_service.semantic_search_classes(query, top_k=top_k)
        function_results = kb_service.semantic_search_functions(query, top_k=top_k)

        if not class_results and not function_results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到与 '{query}' 相关的内容"}]
            )

        # 格式化结果
        output = f"语义搜索 '{query}' 的结果:\n\n"

        if class_results:
            output += f"相关的类 (Top {len(class_results)}):\n"
            for class_name, score in class_results[:5]:
                # 获取详细信息
                exact_results = kb_service.search_by_class_name(class_name)
                if exact_results:
                    result = exact_results[0]
                    output += f"  - {result['class']['name']} (相似度: {score:.3f})\n"
                    output += f"    位置: {result['file']['path']}\n"
                    output += f"    基类: {result['class']['base_class']}\n"
                    output += f"    行号: {result['class']['line']}\n\n"

        if function_results:
            output += f"相关的函数 (Top {len(function_results)}):\n"
            for func_name, score in function_results[:5]:
                # 获取详细信息
                exact_results = kb_service.search_by_function_name(func_name)
                if exact_results:
                    result = exact_results[0]
                    output += f"  - {result['function']['name']} (相似度: {score:.3f})\n"
                    output += f"    位置: {result['file']['path']}\n"
                    output += f"    类型: {result['function']['type']}\n"
                    output += f"    行号: {result['function']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"语义搜索时出错: {str(e)}"}],
            isError=True
        )


async def get_knowledge_base_stats(arguments: Any) -> CallToolResult:
    """
    获取知识库统计信息

    Args:
        arguments: 无参数

    Returns:
        统计信息
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    try:
        stats = kb_service.get_statistics()

        if not stats:
            return CallToolResult(
                content=[{"type": "text", "text": "知识库未构建,请先使用 build_knowledge_base 工具构建知识库"}]
            )

        # 格式化结果
        output = "知识库统计信息:\n\n"
        output += f"- 类数量: {stats.get('classes', 0)}\n"
        output += f"- 函数数量: {stats.get('functions', 0)}\n"
        output += f"- 文件数量: {stats.get('files', 0)}\n"
        output += f"- 词汇表大小: {stats.get('vocabulary_size', 0)}\n"
        output += f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n"

        # 获取 Delphi 版本信息
        if kb_service.delphi_versions:
            output += f"\n已检测到的 Delphi 版本:\n"
            for version in kb_service.delphi_versions:
                output += f"- {version['name']} ({version['version']})\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"获取统计信息时出错: {str(e)}"}],
            isError=True
        )


async def list_delphi_versions(arguments: Any) -> CallToolResult:
    """
    列出已安装的 Delphi 版本

    Args:
        arguments: 无参数

    Returns:
        Delphi 版本列表
    """
    global kb_service

    if kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "知识库服务未初始化"}],
            isError=True
        )

    try:
        versions = kb_service.delphi_versions

        if not versions:
            return CallToolResult(
                content=[{"type": "text", "text": "未检测到已安装的 Delphi 版本"}]
            )

        # 格式化结果
        output = "已检测到的 Delphi 版本:\n\n"
        for i, version in enumerate(versions, 1):
            output += f"{i}. {version['name']} ({version['version']})\n"
            output += f"   安装路径: {version['root_dir']}\n"
            output += f"   源码目录: {version['source_dir']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"获取 Delphi 版本时出错: {str(e)}"}],
            isError=True
        )


# 统一的知识库服务实例
_delphi_kb_service = None
_project_kb_service = None
_thirdparty_kb_service = None
_help_kb_service = None


def set_delphi_kb_service(service):
    """设置 Delphi 知识库服务实例"""
    global _delphi_kb_service
    _delphi_kb_service = service


def set_project_kb_service(service):
    """设置项目知识库服务实例"""
    global _project_kb_service
    _project_kb_service = service


def set_thirdparty_kb_service(service):
    """设置第三方库知识库服务实例"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


def set_help_kb_service(service):
    """设置帮助知识库服务实例"""
    global _help_kb_service
    _help_kb_service = service


async def search_knowledge(arguments: Any) -> CallToolResult:
    """
    统一搜索知识库
    
    参数:
    - kb_type: "all"|"delphi"|"project"|"thirdparty"|"help" 知识库类型
    - search_type: "class"|"function"|"semantic"|"record"|"filename" 搜索类型
    - query: 搜索关键词
    - project_path: 项目路径 (仅project类型需要)
    - top_k: 返回数量
    """
    kb_type = arguments.get("kb_type", "all")
    search_type = arguments.get("search_type", "semantic")
    query = arguments.get("query", "")
    project_path = arguments.get("project_path")
    top_k = arguments.get("top_k", 10)
    
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供搜索关键词 query"}],
            isError=True
        )
    
    results = {}
    
    # 确定要搜索的知识库
    kb_types = []
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty", "help"]
    else:
        kb_types = [kb_type]
    
    # 搜索各知识库
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                if search_type in ["class", "all"]:
                    results["delphi_classes"] = _delphi_kb_service.search_by_class_name(query)[:top_k]
                if search_type in ["function", "all"]:
                    results["delphi_functions"] = _delphi_kb_service.search_by_function_name(query)[:top_k]
                if search_type in ["semantic", "all"]:
                    results["delphi_semantic_classes"] = _delphi_kb_service.semantic_search_classes(query, top_k=top_k)
                    results["delphi_semantic_functions"] = _delphi_kb_service.semantic_search_functions(query, top_k=top_k)
                if search_type in ["fuzzy", "all"]:
                    keywords = query.lower().split()
                    if keywords:
                        results["delphi_fuzzy"] = _delphi_kb_service.search_by_keywords(keywords, kind_filter=['TC', 'TR', 'TI', 'FF', 'FP', 'TH'])[:top_k]
                    
            elif kb == "project" and _project_kb_service:
                if search_type in ["class", "all"]:
                    results["project_classes"] = _project_kb_service.search_by_class_name(query)[:top_k]
                if search_type in ["function", "all"]:
                    results["project_functions"] = _project_kb_service.search_by_function_name(query)[:top_k]
                if search_type in ["semantic", "all"]:
                    results["project_semantic"] = _project_kb_service.semantic_search(query, top_k=top_k)
                if search_type in ["fuzzy", "all"]:
                    keywords = query.lower().split()
                    if keywords:
                        results["project_fuzzy"] = _project_kb_service.search_by_keywords(keywords, kind_filter=['TC', 'TR', 'TI', 'FF', 'FP', 'TH'])[:top_k]
                    
            elif kb == "thirdparty" and _thirdparty_kb_service:
                if search_type in ["class", "all"]:
                    results["thirdparty_classes"] = _thirdparty_kb_service.search_by_class_name(query)[:top_k]
                if search_type in ["function", "all"]:
                    results["thirdparty_functions"] = _thirdparty_kb_service.search_by_function_name(query)[:top_k]
                if search_type in ["semantic", "all"]:
                    results["thirdparty_semantic"] = _thirdparty_kb_service.semantic_search(query, top_k=top_k)
                if search_type in ["fuzzy", "all"]:
                    keywords = query.lower().split()
                    if keywords:
                        results["thirdparty_fuzzy"] = _thirdparty_kb_service.search_by_keywords(keywords, kind_filter=['TC', 'TR', 'TI', 'FF', 'FP', 'TH'])[:top_k]
                    
            elif kb == "help" and _help_kb_service:
                if search_type in ["semantic", "all"]:
                    results["help_results"] = _help_kb_service.search_by_keyword(query)[:top_k]
        except Exception as e:
            results[f"{kb}_error"] = str(e)
    
    # 格式化输出
    output = f"搜索 '{query}' (类型: {search_type}, 知识库: {kb_type}):\n\n"
    
    has_results = False
    
    if "delphi_classes" in results and results["delphi_classes"]:
        output += f"Delphi 类 ({len(results['delphi_classes'])}):\n"
        for r in results["delphi_classes"][:top_k]:
            name = r.get('name', 'N/A')
            parent = r.get('parent')
            path = r.get('file', {}).get('path', 'N/A')
            line = r.get('line', '')
            if parent:
                output += f"  - {name} ({parent}) @ {path}:{line}\n"
            else:
                output += f"  - {name} @ {path}:{line}\n"
        output += "\n"
        has_results = True
        
    if "delphi_functions" in results and results["delphi_functions"]:
        output += f"Delphi 函数/方法 ({len(results['delphi_functions'])}):\n"
        for r in results["delphi_functions"][:top_k]:
            name = r.get('name', 'N/A')
            parent = r.get('parent')
            path = r.get('file', {}).get('path', 'N/A')
            line = r.get('line', '')
            if parent:
                output += f"  - {name} (in {parent}) @ {path}:{line}\n"
            else:
                output += f"  - {name} @ {path}:{line}\n"
        output += "\n"
        has_results = True
        
    if "project_classes" in results and results["project_classes"]:
        output += f"项目类 ({len(results['project_classes'])}):\n"
        for r in results["project_classes"][:top_k]:
            name = r.get('name', 'N/A')
            parent = r.get('parent')
            path = r.get('file', {}).get('path', 'N/A')
            line = r.get('line', '')
            if parent:
                output += f"  - {name} ({parent}) @ {path}:{line}\n"
            else:
                output += f"  - {name} @ {path}:{line}\n"
        output += "\n"
        has_results = True
        
    if "thirdparty_classes" in results and results["thirdparty_classes"]:
        output += f"第三方库类 ({len(results['thirdparty_classes'])}):\n"
        for r in results["thirdparty_classes"][:top_k]:
            name = r.get('name', 'N/A')
            parent = r.get('parent')
            path = r.get('file', {}).get('path', 'N/A')
            line = r.get('line', '')
            if parent:
                output += f"  - {name} ({parent}) @ {path}:{line}\n"
            else:
                output += f"  - {name} @ {path}:{line}\n"
        output += "\n"
        has_results = True

    if "delphi_fuzzy" in results and results["delphi_fuzzy"]:
        output += f"模糊匹配 ({len(results['delphi_fuzzy'])}):\n"
        for r in results["delphi_fuzzy"][:top_k]:
            name = r.get('name', 'N/A')
            kind = r.get('kind', '')
            path = r.get('file', {}).get('path', 'N/A')
            line = r.get('line', '')
            output += f"  - {name} ({kind}) @ {path}:{line}\n"
        output += "\n"
        has_results = True
        
    if "help_results" in results and results["help_results"]:
        output += f"帮助文档 ({len(results['help_results'])}):\n"
        for r in results["help_results"][:top_k]:
            output += f"  - {r.get('title', 'N/A')[:50]}\n"
        output += "\n"
        has_results = True
    
    if not has_results:
        output += "未找到相关内容\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def build_unified_knowledge_base(arguments: Any) -> CallToolResult:
    """
    统一构建知识库
    
    参数:
    - kb_type: "delphi"|"project"|"thirdparty"|"help"|"all" 知识库类型，支持组合(如"delphi,project")
    - project_path: 项目路径 (仅project类型需要)
    - version: Delphi版本 (仅delphi/thirdparty需要)
    - async_mode: 是否异步
    - force_rebuild: 是否强制重建
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = arguments.get("project_path")
    version = arguments.get("version")
    async_mode = arguments.get("async_mode", True)
    force_rebuild = arguments.get("force_rebuild", False)
    
    # 解析知识库类型
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty", "help"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                success = _delphi_kb_service.build_knowledge_base(version=version, force_rebuild=force_rebuild)
                results["delphi"] = "成功" if success else "失败"
            elif kb == "project" and _project_kb_service and project_path:
                success = _project_kb_service.build_project_knowledge_base(force_rebuild=force_rebuild)
                results["project"] = "成功" if success else "失败"
            elif kb == "thirdparty" and _thirdparty_kb_service:
                success = _thirdparty_kb_service.build_thirdparty_knowledge_base(version=version, force_rebuild=force_rebuild)
                results["thirdparty"] = "成功" if success else "失败"
            elif kb == "help" and _help_kb_service:
                success = _help_kb_service.build_knowledge_base(force_rebuild=force_rebuild)
                results["help"] = "成功" if success else "失败"
        except Exception as e:
            results[kb] = f"错误: {str(e)}"
    
    # 格式化输出
    output = f"构建知识库 ({kb_type}):\n\n"
    for kb, status in results.items():
        output += f"- {kb}: {status}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def get_unified_knowledge_stats(arguments: Any) -> CallToolResult:
    """
    统一获取知识库统计信息
    
    参数:
    - kb_type: "delphi"|"project"|"thirdparty"|"help"|"all"
    - project_path: 项目路径 (仅project需要)
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = arguments.get("project_path")
    
    # 解析知识库类型
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty", "help"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                stats = _delphi_kb_service.get_statistics()
                results["delphi"] = stats
            elif kb == "project" and _project_kb_service:
                stats = _project_kb_service.get_statistics()
                results["project"] = stats
            elif kb == "thirdparty" and _thirdparty_kb_service:
                stats = _thirdparty_kb_service.get_statistics()
                results["thirdparty"] = stats
            elif kb == "help" and _help_kb_service:
                stats = _help_kb_service.get_statistics()
                results["help"] = stats
        except Exception as e:
            results[kb] = {"error": str(e)}
    
    # 格式化输出
    output = f"知识库统计 ({kb_type}):\n\n"
    
    for kb, stats in results.items():
        output += f"【{kb.upper()}】\n"
        if "error" in stats:
            output += f"  错误: {stats['error']}\n"
        else:
            output += f"  文件: {stats.get('total_documents', stats.get('files', 0))}\n"
            output += f"  类: {stats.get('total_classes', stats.get('classes', 0))}\n"
            output += f"  函数: {stats.get('total_functions', stats.get('functions', 0))}\n"
            output += f"  数据库: {stats.get('database_size_mb', 0)} MB\n"
        output += "\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])

    try:
        versions = kb_service.delphi_versions

        if not versions:
            return CallToolResult(
                content=[{"type": "text", "text": "未检测到已安装的 Delphi 版本"}]
            )

        # 格式化结果
        output = "已检测到的 Delphi 版本:\n\n"
        for i, version in enumerate(versions, 1):
            output += f"{i}. {version['name']} ({version['version']})\n"
            output += f"   安装路径: {version['root_dir']}\n"
            output += f"   源码目录: {version['source_dir']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"获取 Delphi 版本时出错: {str(e)}"}],
            isError=True
        )
