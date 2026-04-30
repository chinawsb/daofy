"""
编译历史模型

定义编译历史记录相关的数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class CompileHistoryEntry:
    """编译历史记录"""
    timestamp: datetime
    project_path: str
    status: str
    duration: int
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "project_path": self.project_path,
            "status": self.status,
            "duration": self.duration,
            "error_message": self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompileHistoryEntry':
        """从字典创建实例"""
        timestamp = datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp']
        return cls(
            timestamp=timestamp,
            project_path=data.get('project_path', ''),
            status=data.get('status', ''),
            duration=data.get('duration', 0),
            error_message=data.get('error_message')
        )


@dataclass
class HistoryFile:
    """历史文件结构"""
    entries: List[CompileHistoryEntry] = field(default_factory=list)
    max_entries: int = 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "entries": [e.to_dict() for e in self.entries],
            "max_entries": self.max_entries
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryFile':
        """从字典创建实例"""
        entries = [CompileHistoryEntry.from_dict(e) for e in data.get('entries', [])]
        return cls(
            entries=entries,
            max_entries=data.get('max_entries', 100)
        )

    def add_entry(self, entry: CompileHistoryEntry):
        """添加历史记录"""
        # 添加到列表开头
        self.entries.insert(0, entry)

        # 如果超过最大记录数,删除最旧的记录
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[:self.max_entries]

    def get_recent_entries(self, limit: int = 10) -> List[CompileHistoryEntry]:
        """获取最近的历史记录"""
        return self.entries[:limit]

    def clear(self):
        """清空历史记录"""
        self.entries.clear()

    def get_entry_count(self) -> int:
        """获取历史记录数量"""
        return len(self.entries)
