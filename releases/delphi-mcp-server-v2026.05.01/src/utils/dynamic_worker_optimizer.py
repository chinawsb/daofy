#!/usr/bin/env python3
"""
动态Worker数量优化器
基于实际处理速度评估最优worker数量
"""

import time
import multiprocessing
from typing import Callable, List, Any, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed


class DynamicWorkerOptimizer:
    """动态Worker数量优化器"""
    
    def __init__(self):
        self.cpu_cores = multiprocessing.cpu_count()
        self.max_possible_workers = max(2, self.cpu_cores - 1)
    
    def calculate_optimal_workers(
        self,
        task_count: int,
        task_function: Callable,
        task_args: List[Any] = None,
        use_process_pool: bool = True,
        min_workers: int = 2,
        max_workers: Optional[int] = None,
        test_sample_size: Optional[int] = None,
        skip_small_tasks: bool = True
    ) -> int:
        """
        计算最优worker数量
        
        Args:
            task_count: 任务总数
            task_function: 任务函数
            task_args: 任务参数列表（用于测试）
            use_process_pool: 是否使用进程池（True）或线程池（False）
            min_workers: 最小worker数量
            max_workers: 最大worker数量（None表示使用CPU核心数-1）
            test_sample_size: 测试样本大小（None表示自动确定）
            skip_small_tasks: 小任务数量时跳过测试
            
        Returns:
            最优worker数量
        """
        if max_workers is None:
            max_workers = self.max_possible_workers
        else:
            max_workers = min(max_workers, self.max_possible_workers)
        
        # 确保最小worker数量不超过最大值
        min_workers = min(min_workers, max_workers)
        
        # 任务数量很少时直接返回合理数量
        if skip_small_tasks and task_count < 50:
            return max(min_workers, min(4, max_workers))
        
        # 根据任务数量调整测试策略
        if task_count < 200:
            sample_size = min(50, task_count)
            test_limit = min(4, max_workers)
        elif task_count < 1000:
            sample_size = min(100, task_count)
            test_limit = min(6, max_workers)
        else:
            sample_size = min(100, task_count)
            test_limit = max_workers
        
        if test_sample_size is not None:
            sample_size = min(test_sample_size, task_count)
        
        # 如果没有提供测试参数，无法进行动态测试
        if not task_args or len(task_args) < sample_size:
            # 根据任务数量返回合理的默认值
            if task_count < 50:
                return max(min_workers, min(4, max_workers))
            elif task_count < 200:
                return max(min_workers, min(4, max_workers))
            elif task_count < 1000:
                return max(min_workers, min(6, max_workers))
            else:
                return max_workers
        
        # 获取测试样本
        test_args = task_args[:sample_size]
        
        # 动态性能测试
        best_workers = min_workers
        best_throughput = 0
        test_worker_counts = list(range(min_workers, test_limit + 1, 2))
        
        for workers in test_worker_counts:
            try:
                start_time = time.time()
                
                # 测试当前worker数量的性能
                if use_process_pool:
                    with ProcessPoolExecutor(max_workers=workers) as executor:
                        results = list(executor.map(task_function, test_args))
                else:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        results = list(executor.map(task_function, test_args))
                
                elapsed = time.time() - start_time
                throughput = sample_size / elapsed if elapsed > 0 else 0
                
                # 检查是否有性能提升
                if throughput > best_throughput:
                    best_throughput = throughput
                    best_workers = workers
                else:
                    # 性能没有提升，停止测试
                    if workers > min_workers:
                        improvement = (throughput - best_throughput) / best_throughput * 100 if best_throughput > 0 else 0
                        if improvement < 5:  # 性能提升少于5%，停止测试
                            break
                
            except Exception as e:
                # 测试失败，返回当前最佳配置
                print(f"Worker {workers} 测试失败: {e}")
                break
        
        return best_workers
    
    def get_default_workers(
        self,
        task_count: int,
        min_workers: int = 2,
        max_workers: Optional[int] = None
    ) -> int:
        """
        获取默认worker数量（不进行动态测试）
        
        Args:
            task_count: 任务总数
            min_workers: 最小worker数量
            max_workers: 最大worker数量
            
        Returns:
            合理的worker数量
        """
        if max_workers is None:
            max_workers = self.max_possible_workers
        else:
            max_workers = min(max_workers, self.max_possible_workers)
        
        # 根据任务数量返回合理的默认值
        if task_count < 50:
            return max(min_workers, min(4, max_workers))
        elif task_count < 200:
            return max(min_workers, min(4, max_workers))
        elif task_count < 1000:
            return max(min_workers, min(6, max_workers))
        else:
            return max_workers
    
    def get_system_info(self) -> dict:
        """获取系统信息"""
        return {
            'cpu_cores': self.cpu_cores,
            'max_possible_workers': self.max_possible_workers,
            'logical_cpus': multiprocessing.cpu_count(logical=True),
            'physical_cpus': multiprocessing.cpu_count(logical=False)
        }


# 全局实例
_global_optimizer = None


def get_optimizer() -> DynamicWorkerOptimizer:
    """获取全局优化器实例"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = DynamicWorkerOptimizer()
    return _global_optimizer


def calculate_optimal_workers(
    task_count: int,
    task_function: Callable = None,
    task_args: List[Any] = None,
    use_process_pool: bool = True,
    **kwargs
) -> int:
    """
    计算最优worker数量（便捷函数）
    
    Args:
        task_count: 任务总数
        task_function: 任务函数（可选，用于动态测试）
        task_args: 任务参数（可选，用于动态测试）
        use_process_pool: 是否使用进程池
        **kwargs: 其他参数传递给calculate_optimal_workers
        
    Returns:
        最优worker数量
    """
    optimizer = get_optimizer()
    
    # 如果没有提供测试函数，使用默认配置
    if task_function is None or task_args is None:
        return optimizer.get_default_workers(task_count, **kwargs)
    
    return optimizer.calculate_optimal_workers(
        task_count=task_count,
        task_function=task_function,
        task_args=task_args,
        use_process_pool=use_process_pool,
        **kwargs
    )