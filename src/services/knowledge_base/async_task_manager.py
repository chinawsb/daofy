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


class CancelledError(Exception):
    """任务取消异常——由 _cancellation_check 抛出，被 run_task 捕获"""
    pass


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
    # 新增：去重键（可选）
    _dedup_key: Optional[str] = None
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
        self._progress_condition = threading.Condition(self._lock)
        self._task_counter = 0

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        with self._lock:
            self._task_counter += 1
            return f"task_{int(time.time())}_{self._task_counter}"

    def find_running_task_by_key(self, dedup_key: str) -> Optional[str]:
        """
        查找是否有正在运行或待处理的 dedup 任务

        Args:
            dedup_key: 去重键

        Returns:
            已有任务的 task_id，或 None
        """
        with self._lock:
            for tid, info in self._tasks.items():
                if info.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    stored_key = getattr(info, '_dedup_key', None)
                    if stored_key == dedup_key:
                        return tid
        return None

    def submit_task(self, name: str, func: Callable, *args,
                    progress_callback: Optional[Callable] = None,
                    dedup_key: Optional[str] = None,
                    on_complete: Optional[Callable[..., None]] = None,
                    **kwargs) -> str:
        """
        提交后台任务

        Args:
            name: 任务名称
            func: 任务函数
            *args: 任务函数位置参数
            progress_callback: 进度回调函数
            dedup_key: 去重键。同一 key 的任务已在运行/待处理时，返回已有 task_id
            **kwargs: 任务函数关键字参数

        Returns:
            任务ID
        """
        # 防重入检查：同一 dedup_key 的任务已在运行则复用 task_id
        if dedup_key is not None:
            existing = self.find_running_task_by_key(dedup_key)
            if existing is not None:
                logger.info(f"复用已有任务 task_id={existing} (dedup_key={dedup_key})")
                return existing

        task_id = self._generate_task_id()

        task_info = TaskInfo(
            task_id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        task_info._dedup_key = dedup_key

        with self._lock:
            self._tasks[task_id] = task_info

        def run_task():
            try:
                with self._lock:
                    task_info.status = TaskStatus.RUNNING
                    task_info.started_at = datetime.now()
                    task_info.message = "任务执行中..."

                logger.info(f"任务 {task_id} ({name}) 开始执行")

                # 创建进度更新函数——在回调中嵌入取消检查，下游无需修改
                def update_progress(*args, **kwargs):
                    # Handle different callback signatures:
                    # 1. ProgressInfo object (from ProgressTracker) — has .percentage
                    # 2. (percent, message) or (percent, message, extra_dict) — standard
                    
                    if args and hasattr(args[0], 'percentage'):
                        # Case 1: ProgressInfo object
                        pct = args[0].percentage
                        msg = args[0].message
                    elif args and isinstance(args[0], (int, float)):
                        # Case 2: (percent, message, extra_dict?)
                        pct = float(args[0])
                        msg = str(args[1]) if len(args) > 1 else kwargs.get('message', '')
                    else:
                        pct = 0
                        msg = str(args) if args else ''
                    
                    # 在每次进度回调中嵌入取消检查
                    if self.is_task_cancelled(task_id):
                        raise CancelledError(f"任务 {task_id} ({name}) 已取消")
                    
                    logger.debug(f"Progress update: {pct}% - {msg}")
                    self.update_task_progress(task_id, pct, msg)

                # 创建取消检查函数——任务函数在循环边界调用它来响应取消
                def _cancellation_check():
                    """检查任务是否被取消，取消时抛出 CancelledError"""
                    if self.is_task_cancelled(task_id):
                        raise CancelledError(f"任务 {task_id} ({name}) 已取消")

                # 将进度回调、取消检查和任务ID传递给任务函数
                kwargs['_progress_callback'] = update_progress
                kwargs['_cancellation_check'] = _cancellation_check
                kwargs['_task_id'] = task_id

                result = func(*args, **kwargs)

                with self._lock:
                    task_info.status = TaskStatus.COMPLETED
                    task_info.completed_at = datetime.now()
                    task_info.progress = 100.0
                    task_info.message = "任务完成"
                    task_info.result = result

                logger.info(f"任务 {task_id} ({name}) 完成")

                # 触发完成回调（用于 MCP 推送通知）
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"任务 {task_id} 完成回调失败: {cb_err}")

            except CancelledError as e:
                logger.info(f"任务 {task_id} ({name}) 已取消")
                with self._lock:
                    task_info.status = TaskStatus.CANCELLED
                    task_info.completed_at = datetime.now()
                    task_info.message = str(e)
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"任务 {task_id} 取消回调失败: {cb_err}")

            except Exception as e:
                logger.error(f"任务 {task_id} ({name}) 失败: {e}", exc_info=True)
                with self._lock:
                    task_info.status = TaskStatus.FAILED
                    task_info.completed_at = datetime.now()
                    task_info.error = str(e)
                    task_info.message = f"任务失败: {str(e)}"
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"任务 {task_id} 失败回调失败: {cb_err}")

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

    def wait_for_progress_change(self, task_id: str, timeout_seconds: float = 120) -> Optional[TaskInfo]:
        """长轮询等待任务进度变化
        
        阻塞等待直到进度变化、任务完成/失败/取消、或超时。
        
        Args:
            task_id: 任务ID
            timeout_seconds: 最大等待秒数（默认 120）
        
        Returns:
            变化后的 TaskInfo，或 None（任务不存在）
        """
        deadline = time.time() + timeout_seconds
        with self._progress_condition:
            while time.time() < deadline:
                task = self._tasks.get(task_id)
                if not task:
                    return None
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    return task
                old_progress = task.progress
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._progress_condition.wait(timeout=min(30.0, remaining))
                task = self._tasks.get(task_id)
                if task and task.progress != old_progress:
                    return task  # 进度有变化，立即返回
            return self._tasks.get(task_id)  # 超时返回当前状态

    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """获取所有任务"""
        with self._lock:
            return dict(self._tasks)

    def update_task_progress(self, task_id: str, progress: float, message: str = "",
                            current_step: str = "", step_index: int = 0, total_steps: int = 0):
        """更新任务进度（通知所有等待的长轮询）"""
        with self._lock:
            if task_id in self._tasks:
                old_progress = self._tasks[task_id].progress
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
                # 进度有变化则通知等待的长轮询
                if progress != old_progress:
                    self._progress_condition.notify_all()

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

            # 通知长轮询的 wait_for_progress_change 立即返回
            self._progress_condition.notify_all()

            # 注意：线程无法强制终止，由 _cancellation_check 在任务函数中响应
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
