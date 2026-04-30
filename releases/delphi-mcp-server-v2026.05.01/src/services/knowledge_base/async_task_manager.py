"""
异步任务管理器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

管理长时间运行的后台任务
"""

import asyncio
import threading
import time
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from ...utils.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    # 新增：步骤信息
    current_step: str = ""  # 当前步骤名称
    total_steps: int = 0    # 总步骤数
    step_index: int = 0     # 当前步骤索引（从1开始）


class AsyncTaskManager:
    """异步任务管理器"""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._task_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._task_counter = 0

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        with self._lock:
            self._task_counter += 1
            return f"task_{int(time.time())}_{self._task_counter}"

    def submit_task(self, name: str, func: Callable, *args, progress_callback: Optional[Callable] = None, **kwargs) -> str:
        """
        提交后台任务

        Args:
            name: 任务名称
            func: 任务函数
            *args: 任务函数位置参数
            progress_callback: 进度回调函数
            **kwargs: 任务函数关键字参数

        Returns:
            任务ID
        """
        task_id = self._generate_task_id()

        task_info = TaskInfo(
            task_id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )

        with self._lock:
            self._tasks[task_id] = task_info

        def run_task():
            try:
                with self._lock:
                    task_info.status = TaskStatus.RUNNING
                    task_info.started_at = datetime.now()
                    task_info.message = "任务执行中..."

                logger.info(f"任务 {task_id} ({name}) 开始执行")

                # 创建进度更新函数 - 支持多种回调签名
                def update_progress(*args, **kwargs):
                    # Handle different callback signatures:
                    # 1. ProgressInfo object (from ProgressTracker)
                    # 2. Single numeric value
                    # 3. (current, total, message) - legacy style
                    # 4. (stage, current, total, message) - help KB style
                    
                    if args and hasattr(args[0], 'percentage'):
                        # Case 1: ProgressInfo object
                        pct = args[0].percentage
                        msg = args[0].message
                    elif args and len(args) >= 3:
                        # Case 3 or 4: tuple arguments
                        # For help KB: stage, current, total, message
                        # For legacy: current, total, message
                        if len(args) == 4:
                            # Help KB style: (stage, current, total, message)
                            # Calculate percentage from current/total
                            current = args[1]
                            total = args[2]
                            pct = (current / total * 100) if total > 0 else 0
                            msg = args[3]
                        else:
                            # Legacy style: (current, total, message)
                            current = args[0]
                            total = args[1]
                            pct = (current / total * 100) if total > 0 else 0
                            msg = args[2] if len(args) > 2 else ''
                    elif args and isinstance(args[0], (int, float)):
                        # Case 2: Single numeric value
                        pct = float(args[0])
                        msg = kwargs.get('message', '')
                    else:
                        pct = 0
                        msg = str(args) if args else ''
                    
                    logger.debug(f"Progress update: {pct}% - {msg}")
                    self.update_task_progress(task_id, pct, msg)

                # 将进度回调和任务ID传递给任务函数
                kwargs['_progress_callback'] = update_progress
                kwargs['_task_id'] = task_id

                result = func(*args, **kwargs)

                with self._lock:
                    task_info.status = TaskStatus.COMPLETED
                    task_info.completed_at = datetime.now()
                    task_info.progress = 100.0
                    task_info.message = "任务完成"
                    task_info.result = result

                logger.info(f"任务 {task_id} ({name}) 完成")

            except KeyboardInterrupt:
                logger.info(f"任务 {task_id} ({name}) 被取消")
                with self._lock:
                    task_info.status = TaskStatus.CANCELLED
                    task_info.completed_at = datetime.now()
                    task_info.message = "任务已取消"

            except Exception as e:
                logger.error(f"任务 {task_id} ({name}) 失败: {e}", exc_info=True)
                with self._lock:
                    task_info.status = TaskStatus.FAILED
                    task_info.completed_at = datetime.now()
                    task_info.error = str(e)
                    task_info.message = f"任务失败: {str(e)}"

            finally:
                # 清理线程引用
                with self._lock:
                    if task_id in self._task_threads:
                        del self._task_threads[task_id]

        # 启动后台线程
        thread = threading.Thread(target=run_task, daemon=True)
        with self._lock:
            self._task_threads[task_id] = thread

        thread.start()
        logger.info(f"任务 {task_id} ({name}) 已提交到后台")

        return task_id

    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """获取所有任务"""
        with self._lock:
            return dict(self._tasks)

    def update_task_progress(self, task_id: str, progress: float, message: str = "",
                            current_step: str = "", step_index: int = 0, total_steps: int = 0):
        """更新任务进度"""
        with self._lock:
            if task_id in self._tasks:
                # Always update progress
                self._tasks[task_id].progress = min(100.0, max(0.0, progress))
                # Always update message (even if empty to show current status)
                self._tasks[task_id].message = message
                if current_step:
                    self._tasks[task_id].current_step = current_step
                if step_index > 0:
                    self._tasks[task_id].step_index = step_index
                if total_steps > 0:
                    self._tasks[task_id].total_steps = total_steps

    def cancel_task(self, task_id: str) -> bool:
        """取消任务（仅对支持取消的任务有效）"""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task_info = self._tasks[task_id]
            if task_info.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return False

            task_info.status = TaskStatus.CANCELLED
            task_info.message = "任务已取消"
            task_info.completed_at = datetime.now()

            # 注意：线程无法强制终止，这里只是标记状态
            return True

    def is_task_cancelled(self, task_id: str) -> bool:
        """检查任务是否已被取消"""
        with self._lock:
            if task_id in self._tasks:
                return self._tasks[task_id].status == TaskStatus.CANCELLED
            return False

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务"""
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

        with self._lock:
            to_remove = []
            for task_id, task_info in self._tasks.items():
                if task_info.created_at.timestamp() < cutoff:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                logger.debug(f"清理旧任务: {task_id}")


# 全局任务管理器实例
_task_manager: Optional[AsyncTaskManager] = None


def get_task_manager() -> AsyncTaskManager:
    """获取全局任务管理器实例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = AsyncTaskManager()
    return _task_manager
