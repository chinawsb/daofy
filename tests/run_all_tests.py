#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行所有测试"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 按依赖分类
# 基本测试（无外部依赖，随时可运行）
BASIC_TESTS = [
    ("test_delphi_versions.py", "版本映射测试"),
    ("test_dproj_parser.py", ".dproj 解析测试"),
    ("test_validator.py", "路径验证测试"),
    ("test_config_manager.py", "配置管理器测试"),
    ("test_sqlite_vector_knowledge_base.py", "向量查询KB测试"),
    ("test_mcp_tools.py", "MCP工具参数验证测试"),
    ("test_kb_service_extended.py", "知识库服务扩展测试"),
    ("test_edge_cases.py", "边界条件测试"),
    ("test_config_usage.py", "配置使用测试"),
    ("test_file_tool.py", "文件操作工具测试"),
    ("test_file_backup.py", "文件备份编码检测测试"),
    ("test_dfm_utils.py", "DFM 转换工具测试"),
    ("test_create_component_dfm.py", "组件 DFM 生成测试"),
    ("test_coding_rules.py", "编码规则工具测试"),
    ("test_code_hosting.py", "代码托管平台工具测试"),
    ("test_pasfmt.py", "pasfmt 格式化工具测试"),
]

# 扩展测试（需要 Delphi 编译器或特定依赖）
EXTENDED_TESTS = [
    ("test_compiler_service.py", "编译服务测试"),
    ("test_knowledge_base.py", "知识库集成测试"),
    ("test_document_kb.py", "文档知识库测试"),
    ("test_document_async.py", "文档异步测试"),
    ("test_document_multiprocess.py", "文档多进程测试"),
    ("test_thirdparty_kb_full.py", "三方库完整测试"),
    ("test_thirdparty_paths.py", "三方库路径测试"),
]

# 运行模式：默认只运行基本测试；传 --all 则全部运行
RUN_ALL = "--all" in sys.argv
test_list = BASIC_TESTS + (EXTENDED_TESTS if RUN_ALL else [])

print("=" * 60)
print("  Daofy 完整测试")
print("=" * 60)
if not RUN_ALL:
    print("  提示: 加 --all 参数运行扩展测试（需要 Delphi 环境）")
print()

passed = 0
failed = 0
skipped = 0

for test_file, desc in test_list:
    test_path = Path(__file__).parent / test_file
    if not test_path.exists():
        print(f"[SKIP] {desc}: 文件不存在")
        skipped += 1
        continue

    print(f"运行: {desc}")
    print("-" * 40)

    try:
        result = subprocess.run(
            [sys.executable, "-u", str(test_path)],
            capture_output=False,
            timeout=120
        )

        if result.returncode == 0:
            print(f"[OK] {desc}")
            passed += 1
        else:
            print(f"[FAIL] {desc}")
            failed += 1
    except subprocess.TimeoutExpired:
        print(f"[FAIL] {desc}: 超时 (120s)")
        failed += 1

    print()

print("=" * 60)
print(f"  结果: {passed}/{len(test_list)} 通过, {failed} 失败, {skipped} 跳过")
if not RUN_ALL:
    print(f"  加 --all 运行全部 {len(test_list) + len(EXTENDED_TESTS)} 个测试")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
