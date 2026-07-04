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
import sqlite3
import logging
import locale
from mcp.types import CallToolResult
from ..constants import DIR_DELPHI_KB
from ..utils.file_backup import detect_encoding
from .project_knowledge_base import get_project_kb

logger = logging.getLogger(__name__)

# 知识库服务实例
delphi_kb_service = None
thirdparty_kb_service = None


def set_knowledge_base_services(delphi_service, thirdparty_service):
    """设置知识库服务实例"""
    global delphi_kb_service, thirdparty_kb_service
    delphi_kb_service = delphi_service
    thirdparty_kb_service = thirdparty_service


def _get_kb_db_path(kb_service) -> Path:
    """获取知识库实际的数据库文件路径（读取 config.json）"""
    kb_dir = kb_service.kb_dir
    config_path = kb_dir / "config.json"
    db_name = "knowledge.sqlite"  # 默认值
    if config_path.exists():
        try:
            import json
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
            db_name = config.get('database', {}).get('file', db_name)
        except Exception as e:
            logger.debug("读取知识库配置失败: %s", str(e))
    return kb_dir / db_name


def _search_project_kb_db(project_path: str, file_path: str) -> Optional[Path]:
    """在项目知识库 SQLite 中搜索文件"""
    try:
        kb_dir = Path(project_path).parent / DIR_DELPHI_KB
        db_file = kb_dir / "knowledge.sqlite"
        if not db_file.exists():
            return None
        from src.services.knowledge_base.schema import use_connection
        with use_connection(str(db_file), use_wal=False) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            normalized = file_path.replace('\\', '/')
            backslashed = file_path.replace('/', '\\')
            name_part = Path(file_path).name
            c.execute("""
                SELECT full_path FROM files
                WHERE full_path = ? OR full_path = ? OR full_path = ?
                   OR full_path LIKE ? OR full_path LIKE ?
                   OR relative_path = ? OR relative_path = ? OR relative_path = ?
                   OR relative_path LIKE ? OR relative_path LIKE ?
                   OR relative_path LIKE ?
                LIMIT 1
            """, (
                file_path, normalized, backslashed,
                f'%/{normalized}', f'%\\{backslashed}',
                file_path, normalized, backslashed,
                f'%/{normalized}', f'%\\{backslashed}',
                f'%/{name_part}'
            ))
            row = c.fetchone()
            if row and row['full_path'] and Path(row['full_path']).exists():
                return Path(row['full_path'])
    except Exception as e:
        logger.debug("项目KB搜索失败: %s", str(e))
    return None


def _find_file_in_knowledge_base(file_path: str, project_path: Optional[str] = None) -> Optional[Path]:
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
    
    # 准备多种路径格式用于匹配（DB 可能存 正斜杠 / 或 反斜杠 \）
    normalized = file_path.replace('\\', '/')            # 正斜杠版本
    backslashed = file_path.replace('/', '\\')            # 反斜杠版本
    name_part = Path(file_path).name                      # 仅文件名，如 "System.Classes.pas"
    
    # 2. 在所有知识库中查找（Delphi 官方 + 第三方库）
    for kb_service in [delphi_kb_service, thirdparty_kb_service]:
        if not kb_service:
            continue
        # 自动加载知识库（首次调用时 kb_instance 为 None）
        if kb_service.kb_instance is None:
            try:
                kb_service.load_knowledge_base()
            except Exception as e:
                logger.debug("加载知识库失败: %s", str(e))
        if not kb_service.kb_instance:
            continue
        try:
            db_path = _get_kb_db_path(kb_service)
            if not db_path.exists():
                continue
            
            from src.services.knowledge_base.schema import use_connection
            with use_connection(str(db_path), use_wal=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # 检测 files 表的路径列名
                cursor.execute(f"PRAGMA table_info(files)")
                col_names = {r['name'] for r in cursor.fetchall()}
                path_col = 'relative_path' if 'relative_path' in col_names else 'path'
                
                # 多策略匹配：
                #   1) 精确匹配（原始路径、正斜杠、反斜杠三种格式）
                #   2) LIKE 模糊匹配（路径后缀匹配，处理两种分隔符）
                #   3) 按文件名后缀匹配
                cursor.execute(f"""
                    SELECT full_path FROM files 
                    WHERE {path_col} = ? OR {path_col} = ? OR {path_col} = ?
                       OR {path_col} LIKE ? OR {path_col} LIKE ?
                       OR {path_col} LIKE ? OR {path_col} LIKE ?
                       OR full_path LIKE ? OR full_path LIKE ?
                       OR {path_col} LIKE ?
                    LIMIT 1
                """, (
                    file_path, normalized, backslashed,
                    f'%/{normalized}', f'%\\{normalized}',
                    f'%/{backslashed}', f'%\\{backslashed}',
                    f'%/{normalized}', f'%\\{backslashed}',
                    f'%/{name_part}'
                ))
                
                row = cursor.fetchone()
            
            if row and row['full_path'] and Path(row['full_path']).exists():
                return Path(row['full_path'])
        except Exception as e:
            logger.debug("全局KB搜索失败: %s", str(e))
    
    # 3. 在项目知识库中查找
    if project_path:
        try:
            result = _search_project_kb_db(project_path, file_path)
            if result:
                return result
        except Exception as e:
            logger.debug("项目KB搜索失败: %s", str(e))
    
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
    project_path = arguments.get("project_path")
    
    try:
        # 查找文件
        full_path = _find_file_in_knowledge_base(file_path, project_path)
        
        if not full_path:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到文件: {file_path}\n\n"
                        f"提示: 文件可能不在知识库中。您可以:\n"
                        f"1. 使用 search_class 或 search_function 查找相关文件\n"
                        f"2. 使用 semantic_search 语义搜索相关代码\n"
                        f"3. 确保已构建相应的知识库"}],
                isError=True
            )
        
        # 编码检测 + 降级链读取（与 delphi_file._read_content 一致）
        detected = detect_encoding(str(full_path))
        encodings_to_try = [detected]
        if detected not in ('utf-8', 'utf-8-sig'):
            encodings_to_try.append('utf-8')
        try:
            ansi = locale.getpreferredencoding()
            if ansi.lower() not in (e.lower() for e in encodings_to_try):
                encodings_to_try.append(ansi)
        except Exception as e:
            logger.debug("获取 ANSI 编码失败（不影响主流程）: %s", e)

        encoding_used = 'utf-8'
        all_lines = None
        for enc in encodings_to_try:
            try:
                with open(full_path, 'r', encoding=enc) as f:
                    all_lines = f.readlines()
                encoding_used = enc
                break
            except UnicodeDecodeError:
                continue

        if all_lines is None:
            # 所有编码尝试失败，保底用 utf-8 并忽略错误字符
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
        output += f"编码: {encoding_used}\n"
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
                - "project": 仅项目源码（需要 project_path）
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
    project_path = arguments.get("project_path")
    
    # 兼容旧参数名 class_name
    if not type_name and arguments.get("class_name"):
        type_name = arguments.get("class_name")
    
    if not type_name and not record_name and not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供类型名（type_name/record_name）或函数名"}],
            isError=True
        )

    if search_in == "project" and not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "search_in='project' 需要提供 project_path 参数"}],
            isError=True
        )
    
    try:
        results = []
        
        # 确定搜索名称
        search_name = type_name or record_name
        is_record_search = record_name is not None

        # 在项目知识库中搜索（需要 project_path）。search_in=all 时只有显式
        # 提供项目路径才包含项目结果，避免无上下文时意外扫描当前目录。
        if search_in in ["all", "project"] and project_path:
            try:
                project_kb = get_project_kb(project_path)
                project_kb.load_knowledge_bases()
                if search_name:
                    if project_kb.project_kb is None:
                        project_results = []
                    else:
                        project_results = project_kb.project_kb.search_by_name(search_name)
                    if is_record_search:
                        project_results = [
                            r for r in project_results
                            if r.get('kind_code', '') == 'TR'
                            or r.get('kind') == 'record'
                        ]
                    elif type_name:
                        project_results = [
                            r for r in project_results
                            if r.get('kind_code', '') in ('TC', 'TR', 'TI', 'TE', 'TS', 'TY')
                        ]
                    results.extend(project_results)
                if function_name:
                    if project_kb.project_kb is not None:
                        func_results = project_kb.project_kb.search_by_name(function_name)
                        func_results = [
                            r for r in func_results
                            if r.get('kind_code', '') in ('FF', 'FP')
                        ]
                        results.extend(func_results)
            except Exception as e:
                logger.debug("项目KB搜索失败: %s", str(e))
        
        # 在 Delphi 官方源码中搜索
        if search_in in ["all", "delphi"] and delphi_kb_service:
            # 确保知识库已加载
            if not delphi_kb_service.kb_instance:
                delphi_kb_service.load_knowledge_base()
            
            if delphi_kb_service.kb_instance:
                if search_name:
                    # DelphiKnowledgeBaseService 只有 search_by_name，用它搜索后按 kind_code 过滤
                    all_results = delphi_kb_service.search_by_name(search_name)
                    if is_record_search:
                        all_results = [r for r in all_results if r.get('kind_code', '') == 'TR']
                    elif type_name:
                        # 搜索类/接口/枚举等类型定义
                        all_results = [r for r in all_results if r.get('kind_code', '') in ('TC', 'TR', 'TI', 'TE', 'TS', 'TY')]
                    results.extend(all_results)
                if function_name:
                    func_results = delphi_kb_service.search_by_name(function_name)
                    func_results = [r for r in func_results if r.get('kind_code', '') in ('FF', 'FP')]
                    results.extend(func_results)
        
        # 在第三方库中搜索（ThirdPartyKnowledgeBase 有 search_by_class_name / search_by_function_name）
        if search_in in ["all", "thirdparty"] and thirdparty_kb_service:
            # 确保知识库已加载
            if not thirdparty_kb_service.kb_instance:
                thirdparty_kb_service.load_knowledge_base()
            
            if thirdparty_kb_service.kb_instance:
                if search_name:
                    all_results = thirdparty_kb_service.search_by_class_name(search_name)
                    if is_record_search:
                        all_results = [r for r in all_results if r.get('kind_code', '') == 'TR']
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
        
        # 从结果中提取文件路径：check 多层格式
        # search_by_name 返回格式: result['file']['path'] / result['file']['full_path']
        # search_by_class_name 返回格式: result['full_path'] / result['relative_path']
        file_path = None
        file_info = result.get('file')
        if isinstance(file_info, dict):
            file_path = file_info.get('full_path') or file_info.get('path')
        if not file_path:
            file_path = result.get('full_path') or result.get('relative_path')
        
        # 如果还没有，从 file_id 回退查询
        if not file_path:
            file_id = result.get('file_id')
            kb = delphi_kb_service or thirdparty_kb_service
            if file_id and kb:
                try:
                    db_path = _get_kb_db_path(kb)
                    if db_path.exists():
                        from src.services.knowledge_base.schema import use_connection
                        with use_connection(str(db_path), use_wal=False) as conn:
                            conn.row_factory = sqlite3.Row
                            cur = conn.cursor()
                            cur.execute("SELECT full_path, relative_path, path FROM files WHERE id = ?", (file_id,))
                            row = cur.fetchone()
                            if row:
                                file_path = row['full_path'] or row['relative_path'] or row['path']
                except Exception as e:
                    logger.debug("搜索文件路径失败: %s", str(e))
        
        if not file_path:
            return CallToolResult(
                content=[{"type": "text", "text": f"搜索结果缺少文件路径信息: {result}"}],
                isError=True
            )
        
        line = result.get('line', 1)
        start_line = max(1, line - 5)
        
        # 调用 read_source_file 读取文件
        read_args = {
            "file_path": file_path,
            "start_line": start_line,
            "max_lines": max_lines,
            "project_path": project_path,
        }
        
        return await read_source_file(read_args)
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"搜索并读取文件时出错: {str(e)}"}],
            isError=True
        )
