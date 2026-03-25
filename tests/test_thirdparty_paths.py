#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试全局第三方库路径提取
"""

import sys
import os

# 切换到 MCP 服务器目录
mcp_server_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
os.chdir(mcp_server_dir)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase

def test_thirdparty_paths():
    """测试第三方库路径提取"""
    print("=" * 60)
    print("测试全局第三方库路径提取")
    print("=" * 60)
    print()
    
    # 初始化知识库服务
    kb = ThirdPartyKnowledgeBase()
    
    # 检测到的 Delphi 版本
    print("检测到的 Delphi 版本:")
    for version in kb.delphi_versions:
        print(f"  - {version['name']} ({version['version']})")
        print(f"    安装路径: {version['root_dir']}")
    print()
    
    if not kb.delphi_versions:
        print("错误: 未检测到 Delphi 版本")
        return
    
    # 获取第三方库路径
    print("正在提取第三方库路径...")
    print("-" * 60)
    
    paths = kb.get_library_paths()
    
    print()
    print("=" * 60)
    print(f"总共找到 {len(paths)} 个第三方库路径:")
    print("=" * 60)
    print()
    
    for i, path in enumerate(paths, 1):
        # 检查路径是否存在
        exists = os.path.exists(path)
        status = "✓" if exists else "✗"
        print(f"{i:3}. {status} {path}")
        
        # 如果路径存在，显示一些统计信息
        if exists and os.path.isdir(path):
            try:
                files = os.listdir(path)
                pas_files = [f for f in files if f.lower().endswith('.pas')]
                print(f"     └─ 文件数: {len(files)}, .pas文件: {len(pas_files)}")
            except Exception as e:
                print(f"     └─ 无法读取: {e}")
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_thirdparty_paths()
