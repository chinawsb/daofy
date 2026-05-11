#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行所有测试"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

tests = [
    ("test_delphi_versions.py", "版本映射测试"),
    ("run_extended_tests.py", "知识库服务扩展测试"),
    ("test_mcp_tools.py", "MCP工具参数验证测试"),
    ("test_compiler_service.py", "编译服务测试"),
]

print("=" * 60)
print("  Delphi MCP Server 完整测试")
print("=" * 60)
print()

passed = 0
failed = 0

for test_file, desc in tests:
    test_path = Path(__file__).parent / test_file
    if not test_path.exists():
        print(f"[SKIP] {desc}: 文件不存在")
        continue
    
    print(f"运行: {desc}")
    print("-" * 40)
    
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
    
    print()

print("=" * 60)
print(f"  结果: {passed}/{len(tests)} 测试套件通过")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
