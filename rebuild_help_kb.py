#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接运行帮助知识库重建（绕过MCP服务器交互）
每15秒报告一次进度
"""

import sys
import os

# 设置UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase


def main():
    print("=" * 60)
    print("Delphi 帮助知识库重建")
    print("=" * 60)
    
    # 初始化
    help_kb = DelphiHelpKnowledgeBase()
    
    # 进度跟踪器 - 每15秒报告一次
    last_report_time = [time.time()]
    current_stage = [""]
    current_progress = [0.0]
    
    def progress_callback(stage: str, current: int, total: int, message: str):
        """每15秒报告进度的回调"""
        current_time = time.time()
        
        # 阶段映射
        stage_map = {
            'extract': ('解压CHM文件', 1, 4),
            'scan': ('扫描HTML文件', 2, 4),
            'index': ('构建向量索引', 3, 4),
            'cleanup': ('清理临时文件', 4, 4)
        }
        
        step_name, step_idx, total_steps = stage_map.get(stage, (stage, 1, 4))
        
        # 计算总体进度
        if total > 0:
            stage_progress = (current / total * 100)
        else:
            stage_progress = 0
        overall_progress = ((step_idx - 1) * 25 + stage_progress * 0.25)
        
        current_stage[0] = step_name
        current_progress[0] = overall_progress
        
        # 每15秒或完成时报告
        if current_time - last_report_time[0] >= 15 or overall_progress >= 100:
            elapsed = current_time - last_report_time[0]
            last_report_time[0] = current_time
            
            # 估算剩余时间
            if overall_progress > 0:
                total_estimated = current_time - start_time
                remaining = (total_estimated / overall_progress * 100) - total_estimated
                remaining_str = f", 预计剩余 {int(remaining)}秒"
            else:
                remaining_str = ""
            
            print(f"[{int(overall_progress):3d}%] [步骤{step_idx}/{total_steps}] {step_name}: {message}{remaining_str}")
    
    # 开始构建
    print("\n开始重建帮助知识库...\n")
    start_time = time.time()
    
    try:
        # 强制重建
        success = help_kb.build_knowledge_base(
            help_names=None,  # 全部
            max_files_per_help=None,  # 无限制
            progress_callback=progress_callback,
            save_markdown=False,  # 不保存markdown，提升性能
            cleanup_original=False  # 不清理原始文件
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        if success:
            # 显示统计信息
            stats = help_kb.get_statistics()
            print(f"✅ 帮助知识库重建成功!")
            print(f"   文档数量: {stats.get('total_documents', 0)}")
            print(f"   类定义: {stats.get('total_classes', 0)}")
            print(f"   函数定义: {stats.get('total_functions', 0)}")
            print(f"   数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
        else:
            print("❌ 帮助知识库重建失败!")
        print(f"   总耗时: {int(duration)}秒")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 任务已被用户取消")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
