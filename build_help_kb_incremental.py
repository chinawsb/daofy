"""
增量构建 Delphi 帮助文档知识库脚本

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin

此脚本跳过 CHM 解压步骤，直接扫描已解压的 HTML 文件构建知识库
适用于之前已经解压过的情况
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
    print("Delphi 帮助文档知识库增量构建工具")
    print("(跳过解压，直接扫描已解压的 HTML 文件)")
    print("=" * 60)
    print()

    # 创建帮助知识库实例
    help_kb = DelphiHelpKnowledgeBase()

    # 检查是否存在已解压的文件
    extracted_dir = help_kb.kb_dir / "extracted"
    if not extracted_dir.exists() or not any(extracted_dir.iterdir()):
        print("❌ 未找到已解压的 HTML 文件")
        print("请先运行 build_help_kb.py 进行完整构建")
        return

    print(f"找到已解压目录: {extracted_dir}")
    
    # 统计已解压的文件
    html_count = len(list(extracted_dir.rglob("*.html"))) + len(list(extracted_dir.rglob("*.htm")))
    print(f"  - HTML 文件数量: {html_count}")
    print()

    # 检查是否已存在知识库
    need_rebuild = False
    if help_kb.is_kb_exists():
        print("帮助文档知识库已存在。")
        stats = help_kb.get_statistics()
        print(f"  - 文档数量: {stats.get('total_documents', 0)}")
        print(f"  - 数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
        print()
        response = input("是否强制重建向量索引? (y/N): ")
        if response.lower() != 'y':
            print("取消构建。")
            return
        need_rebuild = True
    else:
        print("帮助文档知识库不存在，开始增量构建...")

    print()
    print("开始增量构建帮助文档知识库...")
    print("注意: 这个过程可能需要几分钟时间，请耐心等待。")
    print()

    # 如果需要重建，先删除旧的数据库文件
    if need_rebuild:
        import shutil
        index_dir = help_kb.kb_dir / "index"
        if index_dir.exists():
            print("删除旧的数据库文件...")
            for db_file in index_dir.glob("*.sqlite*"):
                try:
                    db_file.unlink()
                    print(f"  已删除: {db_file.name}")
                except Exception as e:
                    print(f"  删除失败 {db_file.name}: {e}")
        # 同时删除 source_index.json
        source_index = index_dir / "source_index.json"
        if source_index.exists():
            try:
                source_index.unlink()
                print(f"  已删除: {source_index.name}")
            except Exception as e:
                print(f"  删除失败 {source_index.name}: {e}")
        print()

    try:
        # 使用增量构建方法
        success = help_kb.build_knowledge_base_incremental()

        if success:
            stats = help_kb.get_statistics()
            print()
            print("=" * 60)
            print("✅ 帮助文档知识库增量构建成功!")
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
            print("❌ 帮助文档知识库增量构建失败")
            print("=" * 60)
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
