"""
经验追踪器 — 跟踪工具调用历史，自动检测经验保存机会。

在 MCP server 内部维护一个滚动调用日志，AI 调用 experience(action="suggest")
时分析日志中的模式，预填经验草稿（problem/solution/tags/context），
供 AI 审核后通过 experience(action="save") 正式保存。

模式检测：
  - fix_cycle:    compile fail → file write → compile success
  - learn_apply:  kb search → file write → compile success
  - clean_fix:    file write → compile success（无前置失败）
"""

import json
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_RECENT_CALLS = 50  # 滚动日志上限


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    name: str
    action: str
    project_path: str = ""
    file_path: str = ""
    success: bool = False
    error_text: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ExperienceTracker:
    """工具调用追踪器 — 滚动日志 + 模式检测。

    线程安全。维护一个固定深度的环形缓冲区，只保留最近调用。
    """

    def __init__(self):
        self._calls: deque[ToolCallRecord] = deque(maxlen=MAX_RECENT_CALLS)
        self._lock = threading.Lock()

    # ── 记录 ──

    def record(self, name: str, arguments: dict, success: bool,
               result_text: str = "") -> None:
        """记录一次工具调用。

        Args:
            name: 工具名 (delphi_project, delphi_file, delphi_kb)
            arguments: 调用参数
            success: 是否成功
            result_text: 结果文本片段（如错误信息）
        """
        action = str(arguments.get("action", ""))
        project_path = str(arguments.get("project_path", arguments.get("file_path", "")))
        file_path = str(arguments.get("file_path", arguments.get("project_path", "")))

        # 提取有意义的错误文本
        error_text = ""
        if not success:
            # 从结果中提取错误摘要
            if result_text:
                # 取前 300 字符作为错误摘要
                error_text = result_text.strip()[:300]

        record = ToolCallRecord(
            name=name,
            action=action,
            project_path=project_path,
            file_path=file_path,
            success=success,
            error_text=error_text,
        )
        with self._lock:
            self._calls.append(record)
        logger.debug("tracker record: %s/%s success=%s", name, action, success)

    def get_recent(self, n: int = 30) -> list[ToolCallRecord]:
        """返回最近 N 条记录（线程安全快照）。"""
        with self._lock:
            return list(self._calls)[-n:]

    def clear(self) -> None:
        """清空追踪日志。"""
        with self._lock:
            self._calls.clear()

    # ── 模式检测 ──

    def suggest(self) -> Optional[dict]:
        """分析最近调用历史，检测可保存的经验模式。

        Returns:
            预填的经验草稿 dict（含 problem、solution、tags、context），
            或 None（未检测到有价值模式）。
        """
        calls = self.get_recent(30)
        if len(calls) < 2:
            return None

        # ── 检测修复闭环 (fix_cycle) ──
        result = self._detect_fix_cycle(calls)
        if result:
            return result

        # ── 检测学-用闭环 (learn_apply) ──
        result = self._detect_learn_apply(calls)
        if result:
            return result

        # ── 检测干净修改 (clean_fix) ──
        result = self._detect_clean_fix(calls)
        if result:
            return result

        return None

    def _detect_fix_cycle(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """检测：compile fail → file write → compile success"""
        # 找最近一次成功的 compile
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 2:
            return None

        # 在它之前找 file write
        write_indices = []
        for i in range(success_compile_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action in ("write", "replace", "insert", "delete"):
                write_indices.append(i)
                if len(write_indices) >= 3:  # 最多看 3 次写操作
                    break

        if not write_indices:
            return None

        # 在 write 之前或之间找失败的 compile
        last_write_idx = write_indices[-1]
        for i in range(last_write_idx - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and not c.success:
                return self._build_draft("fix_cycle", calls, i, success_compile_idx,
                                         write_indices, "修复编译错误")

        return None

    def _detect_learn_apply(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """检测：delphi_kb search → file write → compile success"""
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 2:
            return None

        # 在 compile 前找 write
        write_indices = []
        for i in range(success_compile_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action == "write":
                write_indices.append(i)
                if len(write_indices) >= 2:
                    break

        if not write_indices:
            return None

        # 在 write 前找 kb search
        last_write_idx = write_indices[-1]
        for i in range(last_write_idx - 1, -1, -1):
            c = calls[i]
            if c.name == "delphi_kb" and c.action == "search" and c.success:
                return self._build_draft("learn_apply", calls, i, success_compile_idx,
                                         write_indices, "参考知识库后修改代码")

        return None

    def _detect_clean_fix(self, calls: list[ToolCallRecord]) -> Optional[dict]:
        """检测：file write → compile success（无前置失败，纯净修改）"""
        success_compile_idx = None
        for i in range(len(calls) - 1, -1, -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and c.success:
                success_compile_idx = i
                break

        if success_compile_idx is None or success_compile_idx < 1:
            return None

        # 在 compile 前找 write（最多 5 次内）
        write_indices = []
        for i in range(success_compile_idx - 1, max(-1, success_compile_idx - 6), -1):
            c = calls[i]
            if c.name == "delphi_file" and c.action in ("write", "replace", "insert", "delete"):
                write_indices.append(i)
                if len(write_indices) >= 3:
                    break

        if not write_indices:
            return None

        # 确认没有前置 compile fail
        for i in range(min(write_indices) - 1, max(-1, min(write_indices) - 3), -1):
            c = calls[i]
            if c.name in ("delphi_project", "compile_project") and c.action == "compile" and not c.success:
                return None  # 有失败 compile → 属于 fix_cycle，非 clean_fix

        return self._build_draft("clean_fix", calls, write_indices[-1],
                                 success_compile_idx, write_indices, "代码修改通过编译")

    # ── 草稿构建 ──

    def _build_draft(self, pattern: str, calls: list[ToolCallRecord],
                     start_idx: int, end_idx: int,
                     write_indices: list[int],
                     summary: str) -> dict:
        """构建经验草稿。

        Args:
            pattern: 检测到的模式名
            calls: 全量调用列表
            start_idx: 起始索引（最早相关调用）
            end_idx: 结束索引（最新相关调用）
            write_indices: 写操作索引列表
            summary: 分类摘要

        Returns:
            预填的经验草稿
        """
        relevant = calls[start_idx:end_idx + 1]
        file_paths = sorted(set(
            c.file_path for c in relevant if c.file_path
        ))

        # 收集编译错误
        compile_errors = []
        for c in relevant:
            if c.name in ("delphi_project", "compile_project") and not c.success and c.error_text:
                compile_errors.append(c.error_text)

        # 构建 problem 描述
        if compile_errors:
            problem = f"[Auto] {summary}: 编译错误已修复\n\n"
            for err in compile_errors[:3]:
                problem += f"  - {err[:200]}\n"
        elif pattern == "learn_apply":
            problem = f"[Auto] {summary}: 查询知识库后应用修改"
        else:
            files_str = ", ".join(Path(p).name for p in file_paths[:5])
            problem = f"[Auto] {summary}: {files_str}"

        # 构建 solution 描述
        solution_parts = [f"检测到模式: {pattern}"]
        if file_paths:
            solution_parts.append(f"\n涉及文件:\n" + "\n".join(f"  - {p}" for p in file_paths[:8]))
        if compile_errors:
            solution_parts.append(f"\n修复的编译错误:\n" + "\n".join(f"  - {e[:150]}" for e in compile_errors[:5]))
        solution = "\n".join(solution_parts)

        # 操作序列时间线
        timeline = []
        for c in relevant:
            action_desc = f"{c.name}/{c.action}"
            status = "✓" if c.success else "✗"
            target = c.file_path or c.project_path or ""
            timeline.append(f"  {status} {action_desc} {Path(target).name if target else ''}")
        solution += "\n\n操作序列:\n" + "\n".join(timeline)

        tags = ["auto-saved"]
        if pattern == "fix_cycle":
            tags.extend(["compile", "bugfix"])
        elif pattern == "learn_apply":
            tags.extend(["knowledge-base", "code"])
        elif pattern == "clean_fix":
            tags.extend(["compile", "code"])

        context = {
            "auto_saved": True,
            "pattern": pattern,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "problem": problem,
            "solution": solution,
            "tags": tags,
            "context": context,
        }


# 全局单例
_instance: Optional[ExperienceTracker] = None
_instance_lock = threading.Lock()


def get_tracker() -> ExperienceTracker:
    """获取全局 ExperienceTracker 实例（单例）"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ExperienceTracker()
    return _instance
