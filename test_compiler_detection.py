#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试新添加的编译器检测功能
"""

import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from src.tools.config import search_compilers, set_config_manager
from src.services.config_manager import ConfigManager


async def main():
    print("=" * 60)
    print("测试编译器搜索功能")
    print("=" * 60)
    
    # 初始化配置管理器
    config_mgr = ConfigManager()
    set_config_manager(config_mgr)
    
    # 测试自动检测（不传参数）
    print("\n1. 测试 search_compilers() (自动检测):")
    result = await search_compilers()
    print(f"   结果: {result}")
    
    # 测试指定路径搜索
    print("\n2. 测试 search_compilers(search_path):")
    result = await search_compilers(r"C:\Program Files (x86)\Embarcadero\Studio")
    print(f"   结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())
