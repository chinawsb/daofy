"""
Delphi 知识库服务模块

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)
"""

from .service import DelphiKnowledgeBaseService

# ============================================================
# 知识库 Schema 版本管理
# 每次修改表结构时递增此版本号，以便在加载时自动检测并触发重建
# ============================================================
SCHEMA_VERSION = 1
"""
当前知识库 schema 版本号。
每次修改表结构时递增，用于在加载时检测旧库并提示重建。

版本历史:
  - 1: 当前版本。vocabularies 统一 schema + relative_path 列 + name_lower_rev 反转索引 + metadata 版本管理
"""

SCHEMA_VERSION_KEY = 'schema_version'
"""metadata 表中存储版本号的 key 名称"""


def get_schema_version_from_db(cursor) -> int:
    """从 metadata 表读取 schema 版本号，返回 0 表示无版本信息（旧库）"""
    try:
        cursor.execute(f"SELECT value FROM metadata WHERE key = '{SCHEMA_VERSION_KEY}'")
        row = cursor.fetchone()
        if row:
            return int(row[0])
    except Exception:
        pass
    return 0


def set_schema_version_in_db(cursor, version=None):
    """将 schema 版本号写入 metadata 表"""
    from datetime import datetime
    v = version if version is not None else SCHEMA_VERSION
    cursor.execute(
        "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
        (SCHEMA_VERSION_KEY, str(v), datetime.now().timestamp())
    )


def check_schema_version(cursor, kb_name: str = "unknown") -> bool:
    """
    检查 schema 版本是否匹配。
    返回 True 表示版本匹配或可兼容，False 表示需要重建。
    """
    stored = get_schema_version_from_db(cursor)
    if stored == 0:
        print(f"[{kb_name}] 知识库无版本信息，假定为旧版 schema (v1)")
        return True  # 旧版兼容处理
    if stored == SCHEMA_VERSION:
        return True  # 版本匹配
    print(f"[{kb_name}] 知识库 schema 版本不匹配: 当前 v{stored}, 期望 v{SCHEMA_VERSION}，建议重建")
    return False


__all__ = [
    'DelphiKnowledgeBaseService',
    'SCHEMA_VERSION',
    'SCHEMA_VERSION_KEY',
    'get_schema_version_from_db',
    'set_schema_version_in_db',
    'check_schema_version',
]
