"""
重建所有知识库脚本

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin

由于数据库结构变更（path -> full_path），需要重建所有知识库
"""

import sys
import os
import shutil
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.logger import init_default_logger, get_logger

# 初始化日志
logger = init_default_logger()


def get_kb_directories():
    """获取所有知识库目录"""
    data_dir = project_root / "data"
    
    kb_dirs = {
        "delphi-source": data_dir / "delphi-knowledge-base",
        "thirdparty": data_dir / "thirdparty-knowledge-base",
        "help": data_dir / "help-knowledge-base",
    }
    
    # 查找项目知识库（在 projects 目录下）
    projects_dir = data_dir / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                kb_dirs[f"project-{project_dir.name}"] = project_dir
    
    return kb_dirs


def check_kb_exists(kb_dir):
    """检查知识库是否存在"""
    if not kb_dir.exists():
        return False
    
    # 检查是否有 SQLite 数据库文件
    db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
    return db_file.exists()


def delete_kb_database(kb_dir):
    """删除知识库的数据库文件（保留 source_index.json）"""
    if not kb_dir.exists():
        return
    
    # 删除 SQLite 数据库
    db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
    if db_file.exists():
        print(f"  删除旧数据库: {db_file}")
        db_file.unlink()
    
    # 删除 WAL 和 SHM 文件（如果存在）
    for ext in ['-wal', '-shm']:
        wal_file = db_file.parent / (db_file.name + ext)
        if wal_file.exists():
            wal_file.unlink()


def rebuild_delphi_source_kb():
    """重建 Delphi 官方源码知识库"""
    print("\n" + "=" * 60)
    print("1. Delphi 官方源码知识库")
    print("=" * 60)
    
    try:
        from src.services.knowledge_base.service import DelphiKnowledgeBaseService
        
        kb_service = DelphiKnowledgeBaseService()
        kb_dir = kb_service.kb_dir
        
        if not check_kb_exists(kb_dir):
            print("知识库不存在，跳过")
            return True
        
        print(f"知识库位置: {kb_dir}")
        response = input("是否重建? (y/N): ")
        if response.lower() != 'y':
            print("跳过")
            return True
        
        # 删除旧数据库
        delete_kb_database(kb_dir)
        
        # 重新加载（会自动重建）
        print("正在重建...")
        kb_service.load_knowledge_base(force_rebuild=True)
        print("✅ 重建完成")
        return True
        
    except Exception as e:
        print(f"❌ 重建失败: {e}")
        return False


def rebuild_thirdparty_kb():
    """重建第三方库知识库"""
    print("\n" + "=" * 60)
    print("2. 第三方库知识库")
    print("=" * 60)
    
    try:
        from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
        
        kb = ThirdPartyKnowledgeBase()
        kb_dir = kb.kb_dir
        
        if not check_kb_exists(kb_dir):
            print("知识库不存在，跳过")
            return True
        
        print(f"知识库位置: {kb_dir}")
        response = input("是否重建? (y/N): ")
        if response.lower() != 'y':
            print("跳过")
            return True
        
        # 删除旧数据库
        delete_kb_database(kb_dir)
        
        # 重新加载（会自动重建）
        print("正在重建...")
        kb.load_knowledge_base()
        print("✅ 重建完成")
        return True
        
    except Exception as e:
        print(f"❌ 重建失败: {e}")
        return False


def rebuild_help_kb():
    """重建帮助文档知识库"""
    print("\n" + "=" * 60)
    print("3. 帮助文档知识库")
    print("=" * 60)

    try:
        from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase

        kb = DelphiHelpKnowledgeBase()
        kb_dir = kb.kb_dir

        if not check_kb_exists(kb_dir):
            print("知识库不存在，跳过")
            return True

        print(f"知识库位置: {kb_dir}")
        response = input("是否重建? (y/N): ")
        if response.lower() != 'y':
            print("跳过")
            return True

        # 删除旧数据库
        delete_kb_database(kb_dir)

        # 重新构建知识库（增量构建，跳过CHM解压）
        print("正在重建...")
        success = kb.build_knowledge_base_incremental(force_rebuild=True)
        if success:
            print("✅ 重建完成")
        else:
            print("❌ 重建失败")
        return success

    except Exception as e:
        print(f"❌ 重建失败: {e}")
        return False


def rebuild_project_kbs():
    """重建项目知识库"""
    print("\n" + "=" * 60)
    print("4. 项目知识库")
    print("=" * 60)
    
    data_dir = project_root / "data" / "projects"
    if not data_dir.exists():
        print("没有项目知识库")
        return True
    
    success_count = 0
    fail_count = 0
    
    for project_dir in data_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        print(f"\n项目: {project_dir.name}")
        
        # 检查项目知识库
        project_kb_dir = project_dir / "project_kb"
        thirdparty_kb_dir = project_dir / "thirdparty_kb"
        
        for kb_dir in [project_kb_dir, thirdparty_kb_dir]:
            if not kb_dir.exists():
                continue
            
            if not check_kb_exists(kb_dir):
                continue
            
            print(f"  知识库: {kb_dir.name}")
            response = input(f"  是否重建 {kb_dir.name}? (y/N): ")
            if response.lower() != 'y':
                print("  跳过")
                continue
            
            try:
                # 删除旧数据库
                delete_kb_database(kb_dir)
                print(f"  ✅ 已删除旧数据库")
                success_count += 1
            except Exception as e:
                print(f"  ❌ 删除失败: {e}")
                fail_count += 1
    
    print(f"\n项目知识库处理完成: {success_count} 成功, {fail_count} 失败")
    return fail_count == 0


def main():
    """主函数"""
    print("=" * 60)
    print("重建所有知识库")
    print("=" * 60)
    print()
    print("由于数据库结构变更（path -> full_path），需要重建所有知识库")
    print("这将删除旧的 SQLite 数据库并重新构建")
    print()
    
    # 显示所有知识库
    print("发现的知识库:")
    kb_dirs = get_kb_directories()
    for name, kb_dir in kb_dirs.items():
        exists = check_kb_exists(kb_dir)
        status = "✅ 存在" if exists else "❌ 不存在"
        print(f"  - {name}: {status}")
    print()
    
    response = input("是否开始重建流程? (y/N): ")
    if response.lower() != 'y':
        print("取消")
        return
    
    print()
    
    # 重建各个知识库
    results = {
        "Delphi 官方源码": rebuild_delphi_source_kb(),
        "第三方库": rebuild_thirdparty_kb(),
        "帮助文档": rebuild_help_kb(),
        "项目知识库": rebuild_project_kbs(),
    }
    
    # 显示结果
    print("\n" + "=" * 60)
    print("重建结果汇总")
    print("=" * 60)
    for name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
    
    print()
    print("提示: 如果某些知识库重建失败，可以单独运行对应的构建脚本")
    print("  - Delphi 官方源码: 使用 mcp_delphi-compiler_build_knowledge_base")
    print("  - 第三方库: 使用 mcp_delphi-compiler_build_thirdparty_knowledge_base")
    print("  - 帮助文档: 使用 build_help_kb.py 或 build_help_kb_incremental.py")
    print("  - 项目知识库: 使用 mcp_delphi-compiler_init_project_knowledge_base")


if __name__ == "__main__":
    main()
