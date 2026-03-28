#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试统一知识库接口
"""

import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from src.tools.knowledge_base import (
    search_knowledge,
    build_unified_knowledge_base,
    get_unified_knowledge_stats,
    set_delphi_kb_service,
    set_project_kb_service,
    set_thirdparty_kb_service,
    set_help_kb_service
)


async def main():
    print("=" * 60)
    print("测试统一知识库接口")
    print("=" * 60)
    
    # 初始化知识库服务
    from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
    help_kb = DelphiHelpKnowledgeBase()
    set_help_kb_service(help_kb)
    
    # 测试 search_knowledge
    print("\n1. 测试 search_knowledge:")
    result = await search_knowledge({
        "kb_type": "help",
        "search_type": "semantic",
        "query": "TButton",
        "top_k": 3
    })
    text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
    print(f"   结果: {text[:200]}...")
    
    # 测试 get_unified_knowledge_stats
    print("\n2. 测试 get_knowledge_base_stats:")
    result = await get_unified_knowledge_stats({
        "kb_type": "help"
    })
    text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
    print(f"   结果: {text[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
