#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通过 MCP 异步任务系统构建项目和第三方知识库
"""

import sys
import os
import time
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.knowledge_base.async_task_manager import get_task_manager, TaskStatus
from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
from src.services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase


def main():
    print("=" * 60)
    print("MCP 异步构建项目和第三方知识库")
    print("=" * 60)
    
    task_manager = get_task_manager()
    start_time = time.time()
    last_report = [time.time()]
    
    # 进度回调
    def progress_callback(progress: float, message: str):
        now = time.time()
        if now - last_report[0] >= 15 or progress >= 100:
            elapsed = int(now - start_time)
            print(f"[{elapsed:4d}秒] [{int(progress):3d}%] {message}")
            last_report[0] = now
    
    # ====== 构建第三方知识库 ======
    print("\n" + "=" * 60)
    print("第一步：构建第三方知识库")
    print("=" * 60)
    
    def build_thirdparty(**kwargs):
        cb = kwargs.get('_progress_callback', progress_callback)
        service = ThirdPartyKnowledgeBase(progress_callback=cb)
        return service.build_thirdparty_knowledge_base(version="11.3", force_rebuild=False)
    
    task_id = task_manager.submit_task(
        name="build_thirdparty_kb",
        func=build_thirdparty,
        progress_callback=progress_callback
    )
    
    print(f"任务已提交: {task_id}")
    print("每15秒报告一次进度...\n")
    
    while True:
        time.sleep(15)
        
        task_info = task_manager.get_task_info(task_id)
        if not task_info:
            print("任务未找到")
            break
        
        elapsed = int(time.time() - start_time)
        
        print(f"[{elapsed:4d}秒] 第三方KB: {task_info.status.value}, 进度: {task_info.progress:.1f}%, 消息: {task_info.message[:60]}...")
        
        if task_info.status == TaskStatus.COMPLETED:
            print(f"\n✅ 第三方知识库完成! 结果: {task_info.result}")
            break
        elif task_info.status == TaskStatus.FAILED:
            print(f"\n❌ 第三方知识库失败: {task_info.message}")
            break
        
        if elapsed > 7200:
            print("\n超时")
            break
    
    thirdparty_time = time.time() - start_time
    print(f"\n第三方知识库耗时: {int(thirdparty_time)}秒")
    
    # ====== 构建项目知识库 ======
    print("\n" + "=" * 60)
    print("第二步：构建项目知识库")
    print("=" * 60)
    
    # 获取项目路径
    project_path = os.environ.get('DELPHI_PROJECT_PATH', r'C:\User\cloudAttendance')
    print(f"项目路径: {project_path}")
    
    start_time = time.time()
    last_report[0] = time.time()
    
    def build_project(**kwargs):
        cb = kwargs.get('_progress_callback', progress_callback)
        project_kb = ProjectKnowledgeBase(project_path, cb)
        results = {}
        results["thirdparty"] = project_kb.build_thirdparty_knowledge_base(force_rebuild=False)
        results["project"] = project_kb.build_project_knowledge_base(force_rebuild=False)
        stats = project_kb.get_statistics()
        results["statistics"] = stats
        return results
    
    task_id2 = task_manager.submit_task(
        name="build_project_kb",
        func=build_project,
        progress_callback=progress_callback
    )
    
    print(f"任务已提交: {task_id2}")
    print("每15秒报告一次进度...\n")
    
    while True:
        time.sleep(15)
        
        task_info = task_manager.get_task_info(task_id2)
        if not task_info:
            print("任务未找到")
            break
        
        elapsed = int(time.time() - start_time)
        
        print(f"[{elapsed:4d}秒] 项目KB: {task_info.status.value}, 进度: {task_info.progress:.1f}%, 消息: {task_info.message[:60]}...")
        
        if task_info.status == TaskStatus.COMPLETED:
            print(f"\n✅ 项目知识库完成! 结果: {task_info.result}")
            break
        elif task_info.status == TaskStatus.FAILED:
            print(f"\n❌ 项目知识库失败: {task_info.message}")
            break
        
        if elapsed > 7200:
            print("\n超时")
            break
    
    project_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)
    print(f"第三方知识库: {int(thirdparty_time)}秒")
    print(f"项目知识库: {int(project_time)}秒")
    print(f"总计: {int(thirdparty_time + project_time)}秒")


if __name__ == "__main__":
    main()
