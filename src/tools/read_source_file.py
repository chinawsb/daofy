"""
读取源码文件 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供读取 Delphi 源码文件内容的能力
工具会先在知识库中验证文件是否存在，然后从磁盘直接读取文件内容
支持从全局知识库（官方源码、第三方库）和项目知识库中定位文件
"""

from typing import Any, Optional
from pathlib import Path
from mcp.types import CallToolResult

# 知识库服务实例
delphi_kb_service = None
thirdparty_kb_service = None


def set_knowledge_base_services(delphi_service, thirdparty_service):
    """设置知识库服务实例"""
    global delphi_kb_service, thirdparty_kb_service
    delphi_kb_service = delphi_service
    thirdparty_kb_service = thirdparty_service


def _find_file_in_knowledge_base(file_path: str) -> Optional[Path]:
    """
    在知识库中查找文件
    
    Args:
        file_path: 文件路径（可以是相对路径或完整路径）
        
    Returns:
        文件的完整路径，如果未找到则返回 None
    """
    # 1. 首先检查是否是完整路径且文件存在
    full_path = Path(file_path)
    if full_path.exists() and full_path.is_file():
        return full_path
    
    # 2. 在 Delphi 官方源码知识库中查找
    if delphi_kb_service and delphi_kb_service.kb_instance:
        try:
            import sqlite3
            conn = sqlite3.connect(str(delphi_kb_service.kb_dir / 'knowledge.sqlite'))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 根据路径或文件名查找
            cursor.execute("""
                SELECT full_path FROM files 
                WHERE path = ? OR full_path = ? OR path LIKE ?
                LIMIT 1
            """, (file_path, file_path, f'%/{file_path}'))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and Path(row['full_path']).exists():
                return Path(row['full_path'])
        except Exception:
            pass
    
    # 3. 在第三方库知识库中查找
    if thirdparty_kb_service and thirdparty_kb_service.kb_instance:
        try:
            import sqlite3
            conn = sqlite3.connect(str(thirdparty_kb_service.kb_dir / 'knowledge.sqlite'))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT full_path FROM files 
                WHERE path = ? OR full_path = ? OR path LIKE ?
                LIMIT 1
            """, (file_path, file_path, f'%/{file_path}'))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and Path(row['full_path']).exists():
                return Path(row['full_path'])
        except Exception:
            pass
    
    return None


async def read_source_file(arguments: Any) -> CallToolResult:
    """
    读取 Delphi 源码文件内容
    
    工具会先在知识库中验证文件是否存在，获取文件的完整路径，
    然后直接从磁盘读取文件内容。支持读取完整文件或指定范围的内容。
    
    Args:
        arguments: 包含以下参数:
            - file_path: 文件路径（相对路径或完整路径）(必需)
            - start_line: 起始行号（可选，从1开始，默认1）
            - end_line: 结束行号（可选，默认文件末尾）
            - max_lines: 最大返回行数（可选，默认500，最大1000）
            - search_in: 搜索范围（可选）
                - "all": 所有知识库（默认）
                - "delphi": 仅 Delphi 官方源码
                - "thirdparty": 仅第三方库
    
    Returns:
        文件内容
    """
    file_path = arguments.get("file_path")
    if not file_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供文件路径"}],
            isError=True
        )
    
    # 解析参数
    start_line = arguments.get("start_line", 1)
    end_line = arguments.get("end_line")
    max_lines = min(arguments.get("max_lines", 500), 1000)  # 限制最大1000行
    search_in = arguments.get("search_in", "all")
    
    try:
        # 查找文件
        full_path = _find_file_in_knowledge_base(file_path)
        
        if not full_path:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到文件: {file_path}\n\n"
                        f"提示: 文件可能不在知识库中。您可以:\n"
                        f"1. 使用 search_class 或 search_function 查找相关文件\n"
                        f"2. 使用 semantic_search 语义搜索相关代码\n"
                        f"3. 确保已构建相应的知识库"}],
                isError=True
            )
        
        # 读取文件
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # 处理行号范围
        if start_line < 1:
            start_line = 1
        
        if end_line is None or end_line > total_lines:
            end_line = total_lines
        
        if end_line < start_line:
            end_line = start_line
        
        # 限制最大行数
        if end_line - start_line + 1 > max_lines:
            end_line = start_line + max_lines - 1
        
        # 提取指定范围的行
        selected_lines = all_lines[start_line - 1:end_line]
        
        # 构建输出
        output = f"文件: {full_path.name}\n"
        output += f"完整路径: {full_path}\n"
        output += f"总行数: {total_lines}\n"
        output += f"显示范围: 第 {start_line} 行 到 第 {end_line} 行"
        
        if end_line < total_lines:
            output += f" (共 {end_line - start_line + 1} 行)"
        output += "\n"
        output += "=" * 60 + "\n\n"
        
        # 添加行号并输出
        for i, line in enumerate(selected_lines, start=start_line):
            # 确保行号对齐
            line_num = str(i).rjust(len(str(total_lines)))
            output += f"{line_num} | {line}"
        
        # 如果还有剩余内容，提示用户
        if end_line < total_lines:
            remaining = total_lines - end_line
            output += f"\n... (还有 {remaining} 行未显示) ...\n"
            output += f"提示: 使用 start_line={end_line + 1} 继续读取后续内容\n"
        
        return CallToolResult(content=[{"type": "text", "text": output}])
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"读取文件时出错: {str(e)}"}],
            isError=True
        )


async def search_and_read_file(arguments: Any) -> CallToolResult:
    """
    搜索并读取文件
    
    根据类型名（类、record、interface）或函数名搜索，然后读取找到的文件内容。
    
    Args:
        arguments: 包含以下参数:
            - type_name: 类型名称（类、record、interface，可选）
            - record_name: record 类型名称（可选，与 type_name 二选一）
            - function_name: 函数名（可选）
            - search_in: 搜索范围（可选）
                - "all": 所有知识库（默认）
                - "delphi": 仅 Delphi 官方源码
                - "thirdparty": 仅第三方库
            - start_line: 起始行号（可选，默认1）
            - max_lines: 最大返回行数（可选，默认100）
    
    Returns:
        文件内容
    """
    type_name = arguments.get("type_name")
    record_name = arguments.get("record_name")
    function_name = arguments.get("function_name")
    search_in = arguments.get("search_in", "all")
    start_line = arguments.get("start_line", 1)
    max_lines = arguments.get("max_lines", 100)
    
    # 兼容旧参数名 class_name
    if not type_name and arguments.get("class_name"):
        type_name = arguments.get("class_name")
    
    if not type_name and not record_name and not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供类型名（type_name/record_name）或函数名"}],
            isError=True
        )
    
    try:
        results = []
        
        # 确定搜索名称
        search_name = type_name or record_name
        is_record_search = record_name is not None
        
        # 在 Delphi 官方源码中搜索
        if search_in in ["all", "delphi"] and delphi_kb_service:
            # 确保知识库已加载
            if not delphi_kb_service.kb_instance:
                delphi_kb_service.load_knowledge_base()
            
            if delphi_kb_service.kb_instance:
                if search_name:
                    all_results = delphi_kb_service.search_by_class_name(search_name)
                    if is_record_search:
                        # 过滤出 record 类型
                        all_results = [r for r in all_results if r.get('class', {}).get('type_kind') == 'record']
                    results.extend(all_results)
                if function_name:
                    results.extend(delphi_kb_service.search_by_function_name(function_name))
        
        # 在第三方库中搜索
        if search_in in ["all", "thirdparty"] and thirdparty_kb_service:
            # 确保知识库已加载
            if not thirdparty_kb_service.kb_instance:
                thirdparty_kb_service.load_knowledge_base()
            
            if thirdparty_kb_service.kb_instance:
                if search_name:
                    all_results = thirdparty_kb_service.search_by_class_name(search_name)
                    if is_record_search:
                        # 过滤出 record 类型
                        all_results = [r for r in all_results if r.get('class', {}).get('type_kind') == 'record']
                    results.extend(all_results)
                if function_name:
                    results.extend(thirdparty_kb_service.search_by_function_name(function_name))
        
        if not results:
            search_term = search_name or function_name
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到 '{search_term}'"}],
                isError=True
            )
        
        # 获取第一个结果
        result = results[0]
        file_path = result['file']['full_path']
        
        # 如果找到了类型或函数，尝试定位到具体行
        if search_name and 'class' in result:
            line = result['class'].get('line', 1)
            type_kind = result['class'].get('type_kind', 'class')
            # 显示类型定义前后的一些行
            start_line = max(1, line - 5)
        elif function_name and 'function' in result:
            line = result['function'].get('line', 1)
            start_line = max(1, line - 3)
        
        # 调用 read_source_file 读取文件
        read_args = {
            "file_path": file_path,
            "start_line": start_line,
            "max_lines": max_lines
        }
        
        return await read_source_file(read_args)
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索并读取文件时出错: {str(e)}"}],
            isError=True
        )
