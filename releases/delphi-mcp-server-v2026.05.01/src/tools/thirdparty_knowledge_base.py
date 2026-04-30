"""
第三方库知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供第三方库知识库构建和查询的 MCP 工具
"""

from typing import Any
from mcp.types import CallToolResult

# 第三方库知识库服务实例
thirdparty_kb_service = None


def set_thirdparty_knowledge_base_service(service):
    """设置第三方库知识库服务实例"""
    global thirdparty_kb_service
    thirdparty_kb_service = service


async def build_thirdparty_knowledge_base(arguments: Any) -> CallToolResult:
    """
    构建第三方库知识库

    Args:
        arguments: 包含以下参数:
            - version: Delphi 版本 (可选)
            - force_rebuild: 是否强制重建 (可选,默认 false)

    Returns:
        构建结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    version = arguments.get("version")
    force_rebuild = arguments.get("force_rebuild", False)

    try:
        # 获取路径列表（不构建，仅显示）
        paths = thirdparty_kb_service.get_library_paths(version)

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "未找到第三方库路径，请检查 Delphi 安装和 Library 配置"}],
                isError=True
            )

        # 构建知识库
        success = thirdparty_kb_service.build_thirdparty_knowledge_base(
            version=version,
            force_rebuild=force_rebuild
        )

        if success:
            stats = thirdparty_kb_service.get_statistics()
            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"第三方库知识库构建成功!\n\n"
                            f"扫描路径数: {len(paths)}\n"
                            f"统计信息:\n"
                            f"- 类数量: {stats.get('classes', 0)}\n"
                            f"- 函数数量: {stats.get('functions', 0)}\n"
                            f"- 文件数量: {stats.get('files', 0)}\n"
                            f"- 词汇表大小: {stats.get('vocabulary_size', 0)}\n"
                            f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n\n"
                            f"扫描的第三方库路径:\n" +
                            "\n".join([f"  - {p}" for p in paths[:10]]) +
                            (f"\n  ... 等共 {len(paths)} 个路径" if len(paths) > 10 else "")
                }]
            )
        else:
            return CallToolResult(
                content=[{"type": "text", "text": "第三方库知识库构建失败"}],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"构建第三方库知识库时出错: {str(e)}"}],
            isError=True
        )


async def search_thirdparty_class(arguments: Any) -> CallToolResult:
    """
    在第三方库中搜索类

    Args:
        arguments: 包含以下参数:
            - class_name: 类名 (必需)

    Returns:
        搜索结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    class_name = arguments.get("class_name")
    if not class_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供类名"}],
            isError=True
        )

    try:
        results = thirdparty_kb_service.search_by_class_name(class_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未在第三方库中找到类 '{class_name}'"}]
            )

        # 格式化结果
        output = f"在第三方库中找到 {len(results)} 个类 '{class_name}':\n\n"
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


async def search_thirdparty_function(arguments: Any) -> CallToolResult:
    """
    在第三方库中搜索函数

    Args:
        arguments: 包含以下参数:
            - function_name: 函数名 (必需)

    Returns:
        搜索结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    function_name = arguments.get("function_name")
    if not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供函数名"}],
            isError=True
        )

    try:
        results = thirdparty_kb_service.search_by_function_name(function_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未在第三方库中找到函数 '{function_name}'"}]
            )

        # 格式化结果
        output = f"在第三方库中找到 {len(results)} 个函数 '{function_name}':\n\n"
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


async def semantic_search_thirdparty(arguments: Any) -> CallToolResult:
    """
    在第三方库中进行语义搜索

    Args:
        arguments: 包含以下参数:
            - query: 搜索查询 (必需)
            - top_k: 返回结果数量 (可选,默认 10)

    Returns:
        搜索结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
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
        class_results = thirdparty_kb_service.semantic_search_classes(query, top_k=top_k)
        function_results = thirdparty_kb_service.semantic_search_functions(query, top_k=top_k)

        if not class_results and not function_results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未在第三方库中找到与 '{query}' 相关的内容"}]
            )

        # 格式化结果
        output = f"在第三方库中语义搜索 '{query}' 的结果:\n\n"

        if class_results:
            output += f"相关的类 (Top {len(class_results)}):\n"
            for class_name, score in class_results[:5]:
                # 获取详细信息
                exact_results = thirdparty_kb_service.search_by_class_name(class_name)
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
                exact_results = thirdparty_kb_service.search_by_function_name(func_name)
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


async def get_thirdparty_kb_stats(arguments: Any) -> CallToolResult:
    """
    获取第三方库知识库统计信息

    Args:
        arguments: 无参数

    Returns:
        统计信息
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    try:
        stats = thirdparty_kb_service.get_statistics()

        if not stats:
            return CallToolResult(
                content=[{"type": "text", "text": "第三方库知识库未构建,请先使用 build_thirdparty_knowledge_base 工具构建知识库"}]
            )

        # 格式化结果
        output = "第三方库知识库统计信息:\n\n"
        output += f"- 类数量: {stats.get('classes', 0)}\n"
        output += f"- 函数数量: {stats.get('functions', 0)}\n"
        output += f"- 文件数量: {stats.get('files', 0)}\n"
        output += f"- 词汇表大小: {stats.get('vocabulary_size', 0)}\n"
        output += f"- 数据库大小: {stats.get('database_size_mb', 0):.2f} MB\n"
        output += f"- 第三方库路径数: {stats.get('thirdparty_paths_count', 0)}\n"
        output += f"- Delphi 版本: {stats.get('delphi_version', 'Unknown')}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"获取统计信息时出错: {str(e)}"}],
            isError=True
        )


async def get_thirdparty_paths(arguments: Any) -> CallToolResult:
    """
    获取第三方库路径列表

    Args:
        arguments: 包含以下参数:
            - version: Delphi 版本 (可选)

    Returns:
        第三方库路径列表
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    version = arguments.get("version")

    try:
        paths = thirdparty_kb_service.get_library_paths(version)

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "未找到第三方库路径"}]
            )

        # 格式化结果
        output = f"找到 {len(paths)} 个第三方库路径:\n\n"
        for i, path in enumerate(paths, 1):
            output += f"{i}. {path}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"获取路径列表时出错: {str(e)}"}],
            isError=True
        )


async def search_record(arguments: Any) -> CallToolResult:
    """
    在第三方库中搜索 record 类型

    Args:
        arguments: 包含以下参数:
            - record_name: record 类型名称 (必需)

    Returns:
        搜索结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    record_name = arguments.get("record_name")
    if not record_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供 record 类型名称"}],
            isError=True
        )

    try:
        # 使用 search_by_class_name 搜索，然后过滤 type_kind='record' 的结果
        results = thirdparty_kb_service.search_by_class_name(record_name)

        # 过滤出 record 类型
        record_results = [r for r in results if r.get('class', {}).get('type_kind') == 'record']

        if not record_results:
            # 如果没有精确匹配，尝试搜索所有类型并显示建议
            all_results = thirdparty_kb_service.search_by_class_name(record_name)
            if all_results:
                output = f"未找到 record 类型 '{record_name}'，但找到以下类型:\n\n"
                for result in all_results[:5]:
                    type_kind = result.get('class', {}).get('type_kind', 'class')
                    output += f"  - {result['class']['name']} ({type_kind})\n"
                    output += f"    位置: {result['file']['path']}\n"
                    output += f"    行号: {result['class']['line']}\n\n"
                return CallToolResult(content=[{"type": "text", "text": output}])
            else:
                return CallToolResult(
                    content=[{"type": "text", "text": f"在第三方库中未找到 '{record_name}'"}]
                )

        # 格式化结果
        output = f"在第三方库中找到 {len(record_results)} 个 record 类型 '{record_name}':\n\n"

        for i, result in enumerate(record_results, 1):
            output += f"{i}. 类型: {result['class']['name']}\n"
            output += f"   基类/父记录: {result['class']['base_class'] or '无'}\n"
            output += f"   文件: {result['file']['path']}\n"
            output += f"   完整路径: {result['file']['full_path']}\n"
            output += f"   行号: {result['class']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索时出错: {str(e)}"}],
            isError=True
        )


async def search_by_filename(arguments: Any) -> CallToolResult:
    """
    按文件名搜索文件

    Args:
        arguments: 包含以下参数:
            - filename: 文件名或通配符模式 (必需)
            - search_in: 搜索范围 (可选)
                - "all": 所有知识库 (默认)
                - "delphi": 仅 Delphi 官方源码
                - "thirdparty": 仅第三方库

    Returns:
        搜索结果
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "第三方库知识库服务未初始化"}],
            isError=True
        )

    filename = arguments.get("filename")
    if not filename:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供文件名"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        import sqlite3
        from pathlib import Path

        results = []

        # 在第三方库中搜索
        if search_in in ["all", "thirdparty"]:
            conn = sqlite3.connect(str(thirdparty_kb_service.kb_dir / 'knowledge.sqlite'))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 使用 LIKE 进行通配符匹配
            pattern = filename.replace('*', '%').replace('?', '_')
            cursor.execute("""
                SELECT path, full_path, extension, size, line_count FROM files
                WHERE path LIKE ? OR full_path LIKE ?
                ORDER BY path
            """, (f'%{pattern}%', f'%{pattern}%'))

            for row in cursor.fetchall():
                results.append({
                    'source': '第三方库',
                    'path': row['path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count']
                })

            conn.close()

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到匹配 '{filename}' 的文件"}]
            )

        # 格式化结果
        output = f"找到 {len(results)} 个匹配 '{filename}' 的文件:\n\n"

        for i, result in enumerate(results[:20], 1):  # 最多显示20个
            output += f"{i}. [{result['source']}] {result['path']}\n"
            output += f"   完整路径: {result['full_path']}\n"
            output += f"   大小: {result['size']} 字节, 行数: {result['line_count']}\n\n"

        if len(results) > 20:
            output += f"... 还有 {len(results) - 20} 个结果未显示\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索时出错: {str(e)}"}],
            isError=True
        )
