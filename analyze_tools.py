#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化 server.py 的工具列表 - 只保留核心统一工具
"""

import re

with open('src/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到所有工具定义
tool_pattern = r'(Tool\(\s*name="[^"]+",\s*description="[^"]+",\s*inputSchema=\{[^}]+\}\s*\))'
tools = re.findall(tool_pattern, content, re.DOTALL)

# 需要保留的工具名称
keep_tools = {
    'compile_project',
    'compile_file', 
    'get_compiler_args',
    'set_compiler_config',
    'search_compilers',
    'check_environment',
    'get_coding_rules',
    'search_knowledge',
    'build_knowledge_base',
    'get_knowledge_base_stats',
    'list_delphi_versions',
    'init_project_knowledge_base',
    'analyze_project_dependencies',
    'resolve_smart_library_paths',
    'read_source_file',
    'search_and_read_file',
    'start_async_task',
    'get_task_status', 
    'get_task_result',
    'list_tasks',
    'cancel_task',
    'format_delphi_file',
    'format_delphi_code',
    'set_pasfmt_path',
    'install_pasfmt',
    'check_pasfmt_installation'
}

# 统计
print(f"总工具数: {len(tools)}")
print(f"保留工具数: {len(keep_tools)}")

# 打印需要保留的工具
for t in tools:
    name_match = re.search(r'name="([^"]+)"', t)
    if name_match:
        name = name_match.group(1)
        if name in keep_tools:
            print(f"✅ 保留: {name}")
        else:
            print(f"❌ 删除: {name}")
