#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接通过 Python 调用 MCP 异步任务系统构建帮助知识库
"""

import sys
import os
import time

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.knowledge_base.async_task_manager import get_task_manager, TaskStatus
from src.tools.help_knowledge_base import _build_kb_task


def main():
    print("=" * 60)
    print("MCP 异步任务构建帮助知识库")
    print("=" * 60)
    
    # 获取任务管理器
    task_manager = get_task_manager()
    
    # 定义进度回调
    last_report = [time.time()]
    
    def progress_callback(progress: float, message: str):
        now = time.time()
        if now - last_report[0] >= 15 or progress >= 100:
            elapsed = int(now - start_time)
            print(f"[{elapsed:4d}秒] [{int(progress):3d}%] {message}")
            last_report[0] = now
    
    # 提交任务
    print("\n提交构建任务...")
    start_time = time.time()
    
    # 使用增量模式（跳过解压）
    task_id = task_manager.submit_task(
        name="build_help_kb",
        func=_build_kb_task,
        help_names=None,  # 全部
        save_markdown=False,  # 不保存markdown提升性能
        progress_callback=progress_callback
    )
    
    print(f"任务已提交: {task_id}")
    print("每15秒报告一次进度...\n")
    
    # 轮询任务状态
    while True:
        time.sleep(15)
        
        task_info = task_manager.get_task_info(task_id)
        if not task_info:
            print("任务未找到")
            break
        
        elapsed = int(time.time() - start_time)
        
        print(f"[{elapsed:4d}秒] 状态: {task_info.status.value}, 进度: {task_info.progress:.1f}%, 消息: {task_info.message[:50]}...")
        
        if task_info.status == TaskStatus.COMPLETED:
            print("\n" + "=" * 60)
            print("✅ 任务完成!")
            if task_info.result:
                print(f"   结果: {task_info.result}")
            break
        elif task_info.status == TaskStatus.FAILED:
            print("\n" + "=" * 60)
            print("❌ 任务失败!")
            print(f"   错误: {task_info.message}")
            break
        
        # 超时保护（3小时）
        if elapsed > 10800:
            print("\n超时，停止轮询")
            break
    
    print(f"\n总耗时: {int(time.time() - start_time)}秒")


if __name__ == "__main__":
    main()
