#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进度跟踪器

用于长时间运行的任务的进度跟踪和反馈
"""

import time
from typing import Callable, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class ProgressInfo:
    """进度信息"""
    current: int  # 当前进度
    total: int  # 总数
    message: str  # 当前状态消息
    percentage: float  # 百分比 (0-100)
    elapsed_time: float  # 已用时间（秒）
    estimated_remaining: float  # 预估剩余时间（秒）
    speed: float  # 处理速度（项目/秒）


class ProgressTracker:
    """进度跟踪器"""

    def __init__(
        self,
        total: int,
        callback: Optional[Callable[[ProgressInfo], None]] = None,
        update_interval: float = 1.0
    ):
        """
        初始化进度跟踪器

        Args:
            total: 总项目数
            callback: 进度回调函数
            update_interval: 更新间隔（秒）
        """
        self.total = total
        self.current = 0
        self.callback = callback
        self.update_interval = update_interval

        self.start_time = time.time()
        self.last_update_time = 0
        self.last_update_count = 0

    def update(self, increment: int = 1, message: str = ""):
        """
        更新进度

        Args:
            increment: 增量
            message: 状态消息
        """
        self.current += increment
        current_time = time.time()

        # 检查是否需要更新（基于时间间隔）
        if current_time - self.last_update_time >= self.update_interval:
            self._notify_progress(message)
            self.last_update_time = current_time
            self.last_update_count = self.current

    def _notify_progress(self, message: str = ""):
        """通知进度更新"""
        if not self.callback:
            return

        elapsed_time = time.time() - self.start_time
        percentage = (self.current / self.total * 100) if self.total > 0 else 0

        # 计算处理速度
        if elapsed_time > 0:
            speed = self.current / elapsed_time
        else:
            speed = 0

        # 估算剩余时间
        if speed > 0 and self.current < self.total:
            remaining_items = self.total - self.current
            estimated_remaining = remaining_items / speed
        else:
            estimated_remaining = 0

        progress_info = ProgressInfo(
            current=self.current,
            total=self.total,
            message=message or f"处理中... ({self.current}/{self.total})",
            percentage=percentage,
            elapsed_time=elapsed_time,
            estimated_remaining=estimated_remaining,
            speed=speed
        )

        self.callback(progress_info)

    def finish(self, message: str = "完成"):
        """
        完成进度跟踪

        Args:
            message: 完成消息
        """
        self.current = self.total
        self._notify_progress(message)

    def get_progress_text(self, progress: ProgressInfo) -> str:
        """
        获取格式化的进度文本

        Args:
            progress: 进度信息

        Returns:
            格式化的进度文本
        """
        elapsed = self._format_time(progress.elapsed_time)
        remaining = self._format_time(progress.estimated_remaining)

        text = (
            f"进度: {progress.current}/{progress.total} "
            f"({progress.percentage:.1f}%) | "
            f"速度: {progress.speed:.1f}项/秒 | "
            f"已用: {elapsed} | "
            f"剩余: {remaining} | "
            f"{progress.message}"
        )

        return text

    def _format_time(self, seconds: float) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}分钟"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}小时"


class ProgressCallback:
    """进度回调处理器"""

    def __init__(self, prefix: str = ""):
        """
        初始化进度回调

        Args:
            prefix: 消息前缀
        """
        self.prefix = prefix
        self.tracker = ProgressTracker(0, self._on_progress)

    def _on_progress(self, progress: ProgressInfo):
        """内部进度回调"""
        text = self.tracker.get_progress_text(progress)
        if self.prefix:
            text = f"[{self.prefix}] {text}"
        print(text)

    def create_tracker(self, total: int) -> ProgressTracker:
        """
        创建进度跟踪器

        Args:
            total: 总项目数

        Returns:
            进度跟踪器
        """
        self.tracker.total = total
        self.tracker.current = 0
        self.tracker.start_time = time.time()
        return self.tracker
