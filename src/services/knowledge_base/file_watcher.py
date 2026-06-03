"""
文件变更监听器 — 监控 Delphi 源码变化自动触发增量 KB 更新

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

依赖: watchdog (pip install watchdog)
如果 watchdog 未安装，监听器静默降级，不影响其他功能。
"""

import os
import threading
import time as _time
from pathlib import Path
from typing import Callable, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)

# 监听的 Delphi 文件扩展名
DELPHI_EXTENSIONS: Set[str] = {
    '.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc', '.dproj',
}

# 跳过的不需要监听的目录名
SKIP_DIR_NAMES: Set[str] = {
    '.delphi-kb', 'thirdpart', 'vendor', 'lib', 'packages',
    '__pycache__', '.git', '.svn', 'node_modules', 'dist', 'bin', 'obj',
    'Win32', 'Win64', '__history', '__recovery', 'backup', 'logs',
}


# ──────────────────────────────────────────────────────────
# DelphiFileHandler — watchdog 事件处理器（带去抖）
# ──────────────────────────────────────────────────────────


class _DelphiFileHandler:
    """watchdog 文件事件处理器，筛选 Delphi 源码变更并去抖触发。

    Args:
        on_change: 去抖结束后触发的回调函数（在 watchdog 线程中调用）
        debounce_seconds: 去抖等待秒数，默认 3 秒
    """

    def __init__(
        self,
        on_change: Callable[[], None],
        debounce_seconds: float = 3.0,
    ):
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def dispatch(self, event) -> None:
        """watchdog 事件分发入口——兼容 watchdog 的 FileSystemEventHandler 约定。"""
        if event.is_directory:
            return
        ext = Path(event.src_path).suffix.lower()
        if ext in DELPHI_EXTENSIONS:
            self._debounce()

    def _debounce(self) -> None:
        """重置去抖计时器：连续变更只触发一次回调。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        try:
            self.on_change()
        except Exception as e:
            logger.error("文件变更回调执行失败: %s", e, exc_info=True)

    def stop(self) -> None:
        """取消待处理的去抖计时器。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


# ──────────────────────────────────────────────────────────
# ProjectFileWatcher
# ──────────────────────────────────────────────────────────


class ProjectFileWatcher:
    """项目文件监听器：监控 Delphi 源码变更，自动触发增量 KB 更新。

    启动时检测 watchdog 是否可用，不可用时静默降级。
    通过 AsyncTaskManager 提交后台构建任务，自带去重防堆叠。
    内置看门狗定时检查 Observer 线程健康，崩溃后自动重启。

    Args:
        project_path: 项目 .dproj 文件路径
        project_dir: 项目根目录（用于文件监听范围）
    """

    # 看门狗检查间隔（秒）
    _HEALTH_CHECK_INTERVAL: float = 60.0

    def __init__(self, project_path: str, project_dir: str):
        self._project_path = project_path
        self._project_dir = project_dir
        self._observer: Optional[object] = None
        self._handler: Optional[_DelphiFileHandler] = None
        self._watchdog_available = False
        self._health_timer: Optional[threading.Timer] = None

    def start(self) -> bool:
        """启动文件监听。返回 True 表示成功启动，False 表示降级。

        降级原因：watchdog 未安装、项目目录不存在、Observer 创建失败。
        """
        # ── 检查 watchdog 可用性 ──
        try:
            from watchdog.observers import Observer  # noqa: F401
            self._watchdog_available = True
        except ImportError:
            logger.info(
                "watchdog 未安装，文件变更监听已跳过。"
                "如需自动增量 KB 更新: pip install watchdog"
            )
            return False

        project_dir = Path(self._project_dir)
        if not project_dir.is_dir():
            logger.warning("项目目录不存在，无法启动文件监听: %s", project_dir)
            return False

        # ── 创建去抖处理器 ──
        self._handler = _DelphiFileHandler(self._on_change, debounce_seconds=3.0)

        # ── 启动 Observer ──
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEvent

            self._observer = Observer()
            # watchdog 要求 handler 实现特定接口，
            # 用 lambda 包装 dispatch 调用
            class _WatchdogHandler:
                def __init__(self, handler: _DelphiFileHandler):
                    self._handler = handler

                def dispatch(self, event: FileSystemEvent) -> None:
                    self._handler.dispatch(event)

            watchdog_handler = _WatchdogHandler(self._handler)
            self._observer.schedule(
                watchdog_handler, str(project_dir), recursive=True
            )
            self._observer.daemon = True
            self._observer.start()
            self._start_health_check()
            logger.info("文件变更监听已启动: %s", project_dir)
            return True

        except Exception as e:
            logger.warning("文件监听启动失败: %s", e)
            return False

    def _start_health_check(self) -> None:
        """启动看门狗定时器，定期检查 Observer 线程是否存活。"""
        def _check():
            if self._observer is None:
                return
            try:
                alive = getattr(self._observer, 'is_alive', lambda: True)()
                if not alive:
                    logger.warning("文件监听 Observer 线程已终止，正在重启...")
                    project_dir = self._project_dir
                    self._observer = self._rebuild_observer()
                    if self._observer:
                        self._observer.start()
                        logger.info("文件监听 Observer 已重启: %s", project_dir)
            except Exception as e:
                logger.debug("文件监听健康检查异常: %s", e)

        def _schedule():
            if self._observer is not None:
                self._health_timer = threading.Timer(
                    self._HEALTH_CHECK_INTERVAL, _schedule
                )
                self._health_timer.daemon = True
                self._health_timer.start()
                _check()

        _schedule()

    def _rebuild_observer(self):
        """重建 Observer 实例（健康检查检测到崩溃时调用）。"""
        try:
            from watchdog.observers import Observer
            obs = Observer()
            class _WatchdogHandler:
                def __init__(self, handler):
                    self._handler = handler
                def dispatch(self, event):
                    self._handler.dispatch(event)
            if self._handler:
                obs.schedule(
                    _WatchdogHandler(self._handler),
                    str(Path(self._project_dir)),
                    recursive=True,
                )
            obs.daemon = True
            logger.info("Observer 实例已重建")
            return obs
        except Exception as e:
            logger.warning("重建 Observer 失败: %s", e)
            return None

    def stop(self) -> None:
        """停止文件监听并清理资源。"""
        # 停止看门狗
        if self._health_timer is not None:
            self._health_timer.cancel()
            self._health_timer = None

        if self._handler is not None:
            self._handler.stop()
            self._handler = None

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception as e:
                logger.debug("停止文件监听时发生非致命错误: %s", e)
            self._observer = None
            logger.info("文件变更监听已停止")

    def _on_change(self) -> None:
        """文件变更触发：通过 AsyncTaskManager 提交增量 KB 构建任务（去重）。"""
        try:
            from src.services.knowledge_base.async_task_manager import (
                get_task_manager,
            )
            from src.services.knowledge_base.project_knowledge_base import (
                ProjectKnowledgeBase,
            )

            task_mgr = get_task_manager()
            dedup_key = f"file_watcher_rebuild_{self._project_path}"

            def rebuild_task(**kwargs: str) -> bool:
                """后台增量构建 KB。"""
                pp = kwargs.get("project_path", self._project_path)
                pkb = ProjectKnowledgeBase(pp, progress_callback=kwargs.get("_progress_callback"))
                return pkb.build_project_knowledge_base(rebuild=False)

            task_id = task_mgr.submit_task(
                name=f"文件变更自动增量更新 ({Path(self._project_path).stem})",
                func=rebuild_task,
                project_path=self._project_path,
                dedup_key=dedup_key,
            )
            logger.debug("文件变更触发增量 KB 更新: task_id=%s", task_id)

        except Exception as e:
            logger.error("触发增量 KB 更新失败: %s", e, exc_info=True)
