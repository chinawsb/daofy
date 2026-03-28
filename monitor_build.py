#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库构建过程监控脚本 (使用psutil)
监控各阶段的Python进程数量和CPU占用率
"""

import psutil
import time
import threading
import json
import os
from datetime import datetime
from typing import List, Dict, Optional


class ProcessMonitor:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.samples: List[Dict] = []
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
    def _get_process_info(self) -> Dict:
        """获取当前进程树的信息"""
        current_pid = os.getpid()
        
        # 获取主进程和所有子进程
        try:
            main_process = psutil.Process(current_pid)
            children = main_process.children(recursive=True)
            
            python_processes = []
            total_memory = 0
            
            # 主进程
            try:
                mem = main_process.memory_info().rss
                python_processes.append({
                    'pid': current_pid,
                    'name': main_process.name(),
                    'memory_mb': mem / 1024 / 1024
                })
                total_memory += mem
            except:
                pass
            
            # 子进程
            for child in children:
                try:
                    if 'python' in child.name().lower():
                        mem = child.memory_info().rss
                        python_processes.append({
                            'pid': child.pid,
                            'name': child.name(),
                            'memory_mb': mem / 1024 / 1024
                        })
                        total_memory += mem
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return {
                'count': len(python_processes),
                'processes': python_processes,
                'total_memory_mb': total_memory / 1024 / 1024
            }
        except Exception as e:
            return {'count': 0, 'processes': [], 'total_memory_mb': 0, 'error': str(e)}
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                # 获取系统整体CPU
                cpu_percent = psutil.cpu_percent(interval=None)
                
                # 获取进程树信息
                process_info = self._get_process_info()
                
                sample = {
                    'timestamp': datetime.now().isoformat(),
                    'system_cpu_percent': cpu_percent,
                    'python': process_info
                }
                self.samples.append(sample)
            except Exception as e:
                print(f"Monitor error: {e}")
            
            time.sleep(self.interval)
    
    def start(self):
        """开始监控"""
        self.samples = []
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self) -> List[Dict]:
        """停止监控并返回结果"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        return self.samples
    
    def get_summary(self) -> Dict:
        """获取统计摘要"""
        if not self.samples:
            return {}
        
        cpu_values = [s['system_cpu_percent'] for s in self.samples if 'system_cpu_percent' in s]
        python_counts = [s['python']['count'] for s in self.samples if 'python' in s]
        
        return {
            'sample_count': len(self.samples),
            'system_cpu': {
                'min': min(cpu_values) if cpu_values else 0,
                'max': max(cpu_values) if cpu_values else 0,
                'avg': sum(cpu_values) / len(cpu_values) if cpu_values else 0
            },
            'python_processes': {
                'min': min(python_counts) if python_counts else 0,
                'max': max(python_counts) if python_counts else 0,
                'avg': sum(python_counts) / len(python_counts) if python_counts else 0
            }
        }


def run_with_monitoring():
    """运行知识库构建并监控"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    print("=" * 70)
    print("知识库构建过程监控 (使用psutil)")
    print("=" * 70)
    
    # 创建监控器
    monitor = ProcessMonitor(interval=0.5)
    
    # 启动监控
    monitor.start()
    
    # 执行构建
    kb_service = DelphiKnowledgeBaseService()
    start_time = time.time()
    
    print("\n开始构建...")
    print("-" * 70)
    
    kb_service.build_knowledge_base(force_rebuild=True)
    
    end_time = time.time()
    
    # 停止监控
    samples = monitor.stop()
    summary = monitor.get_summary()
    
    print("-" * 70)
    print(f"\n构建完成! 总耗时: {end_time - start_time:.2f}秒")
    
    # 打印统计结果
    print("\n" + "=" * 70)
    print("系统 CPU 使用率统计")
    print("=" * 70)
    print(f"  最小: {summary['system_cpu']['min']:.1f}%")
    print(f"  最大: {summary['system_cpu']['max']:.1f}%")
    print(f"  平均: {summary['system_cpu']['avg']:.1f}%")
    
    print("\n" + "=" * 70)
    print("Python 进程数量统计 (包含主进程+子进程)")
    print("=" * 70)
    print(f"  最小: {summary['python_processes']['min']}")
    print(f"  最大: {summary['python_processes']['max']}")
    print(f"  平均: {summary['python_processes']['avg']:.1f}")
    
    # 按时间分段分析
    print("\n" + "=" * 70)
    print("各时间段详细数据")
    print("=" * 70)
    
    n = len(samples)
    if n > 0:
        # 扫描阶段大约60-65%, 向量阶段35-40%
        total_time = end_time - start_time
        scan_end = int(n * 0.65)
        
        phases = [
            (0, scan_end // 3, "扫描-初期"),
            (scan_end // 3, scan_end * 2 // 3, "扫描-中期"),
            (scan_end * 2 // 3, scan_end, "扫描-后期"),
            (scan_end, n, "向量计算")
        ]
        
        for start_idx, end_idx, name in phases:
            if start_idx >= n:
                break
            end_idx = min(end_idx, n)
            phase_samples = samples[start_idx:end_idx]
            
            if phase_samples:
                phase_cpu = [s['system_cpu_percent'] for s in phase_samples if 'system_cpu_percent' in s]
                phase_py = [s['python']['count'] for s in phase_samples if 'python' in s]
                phase_mem = [s['python']['total_memory_mb'] for s in phase_samples if 'python' in s]
                
                print(f"\n【{name}】(样本 {start_idx}-{end_idx}, 持续约{(end_idx-start_idx)*0.5:.1f}秒)")
                print(f"  系统CPU: 最小 {min(phase_cpu):.1f}%, 最大 {max(phase_cpu):.1f}%, 平均 {sum(phase_cpu)/len(phase_cpu):.1f}%")
                print(f"  Python进程数: 最小 {min(phase_py)}, 最大 {max(phase_py)}, 平均 {sum(phase_py)/len(phase_py):.1f}")
                print(f"  Python内存: 最大 {max(phase_mem):.1f}MB, 平均 {sum(phase_mem)/len(phase_mem):.1f}MB")
    
    # 保存详细日志
    log_file = Path('cpu_monitor_log.json')
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': summary,
            'samples': samples
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细日志已保存到: {log_file}")
    
    # 打印阶段汇总表格
    print("\n" + "=" * 70)
    print("阶段汇总表格")
    print("=" * 70)
    print(f"{'阶段':<15} {'平均CPU%':<12} {'最大进程数':<12} {'最大内存MB':<12}")
    print("-" * 50)
    
    for start_idx, end_idx, name in phases:
        if start_idx >= n:
            break
        end_idx = min(end_idx, n)
        phase_samples = samples[start_idx:end_idx]
        
        if phase_samples:
            phase_cpu = [s['system_cpu_percent'] for s in phase_samples if 'system_cpu_percent' in s]
            phase_py = [s['python']['count'] for s in phase_samples if 'python' in s]
            phase_mem = [s['python']['total_memory_mb'] for s in phase_samples if 'python' in s]
            
            print(f"{name:<15} {sum(phase_cpu)/len(phase_cpu):<12.1f} {max(phase_py):<12} {max(phase_mem):<12.1f}")


if __name__ == "__main__":
    run_with_monitoring()