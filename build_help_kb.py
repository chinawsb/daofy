"""
构建 Delphi 帮助文档知识库脚本

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
from src.utils.logger import init_default_logger, get_logger

# 初始化日志
logger = init_default_logger()


def main():
    """主函数"""
    print("=" * 60)
    print("Delphi 帮助文档知识库构建工具")
    print("=" * 60)
    print()

    # 创建帮助知识库实例
    help_kb = DelphiHelpKnowledgeBase()

    # 检查是否已存在
    if help_kb.is_kb_exists():
        print("帮助文档知识库已存在。")
        stats = help_kb.get_statistics()
        print(f"  - 文档数量: {stats.get('total_documents', 0)}")
        print(f"  - 数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
        print()
        response = input("是否强制重建? (y/N): ")
        if response.lower() != 'y':
            print("取消构建。")
            return
        force_rebuild = True
    else:
        force_rebuild = False
        print("帮助文档知识库不存在，开始构建...")

    print()
    print("开始构建帮助文档知识库...")
    print("注意: 这个过程可能需要几分钟时间，请耐心等待。")
    print()

    try:
        success = help_kb.build_knowledge_base(force_rebuild=force_rebuild)

        if success:
            stats = help_kb.get_statistics()
            print()
            print("=" * 60)
            print("✅ 帮助文档知识库构建成功!")
            print("=" * 60)
            print()
            print(f"统计信息:")
            print(f"  - 文档数量: {stats.get('total_documents', 0)}")
            print(f"  - 数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
            print()
            print(f"知识库位置: {help_kb.kb_dir}")
            print()
        else:
            print()
            print("=" * 60)
            print("❌ 帮助文档知识库构建失败")
            print("=" * 60)
            print()
            print("可能的原因:")
            print("  - 未找到 Delphi 帮助目录")
            print("  - 未找到 7-Zip (用于解压 CHM 文件)")
            print("  - Delphi CHM 帮助文件不存在")
            print()

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ 构建过程中出错: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
