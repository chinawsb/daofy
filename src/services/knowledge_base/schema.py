"""
知识库 Schema 定义 —— 统一建表脚本 + 数据库连接管理

所有知识库构建器（SmartCache、ProjectKB、ThirdPartyKB、GenericDocumentKB）
都应从此模块获取 CREATE TABLE SQL 和 get_connection()，确保表结构和 PRAGMA 一致。

注意: 不要在此模块导入任何会触发 ProcessPoolExecutor 子进程缓慢的重型库。
当前导入均为 stdlib，安全。
"""

import contextlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Schema 版本管理
# ============================================================
SCHEMA_VERSION = 3
"""
当前知识库 schema 版本号。
每次修改表结构时递增，用于在加载时检测旧库并执行升级迁移。

版本历史:
  - 3: vocabularies 新增 AST 增强列（code_block, signature, modifiers, end_line 等）
       + entity_refs 引用关系表 + audit_results 审计结果表
  - 2: vocabularies 新增 (type, name, file_id) 唯一索引，去重处理。
  - 1: 初始版本。vocabularies 统一 schema + relative_path + name_lower_rev 反转索引 + metadata 版本管理
"""

SCHEMA_VERSION_KEY = 'schema_version'
"""metadata 表中存储版本号的 key 名称"""


def get_schema_version_from_db(cursor) -> int:
    """从 metadata 表读取 schema 版本号，返回 0 表示无版本信息（旧库）"""
    try:
        cursor.execute("SELECT value FROM metadata WHERE key = ?", (SCHEMA_VERSION_KEY,))
        row = cursor.fetchone()
        if row:
            return int(row[0])
    except Exception as e:
        logger.debug("忽略非致命异常: %s", str(e))
    return 0


def set_schema_version_in_db(cursor, version=None):
    """将 schema 版本号写入 metadata 表"""
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
        logger.info(f"[{kb_name}] 知识库无版本信息，假定为旧版 schema (v1)")
        return True  # 旧版兼容处理
    if stored == SCHEMA_VERSION:
        return True  # 版本匹配
    logger.warning(f"[{kb_name}] 知识库 schema 版本不匹配: 当前 v{stored}, 期望 v{SCHEMA_VERSION}，建议重建")
    return False


# ============================================================
# 源码知识库表结构（files / vocabularies / metadata）
# ============================================================

SOURCE_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_path TEXT UNIQUE NOT NULL,
    relative_path TEXT,
    extension TEXT,
    size INTEGER,
    line_count INTEGER,
    hash TEXT,
    last_modified TEXT,
    category TEXT,
    units_defined TEXT,
    units_imported TEXT,
    description TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
)
"""

SOURCE_VOCABULARIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vocabularies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    name_lower_rev TEXT,
    file_id INTEGER,
    line INTEGER,
    base_class TEXT,
    description TEXT,
    vector BLOB,
    vector_status TEXT DEFAULT 'pending',
    attributes TEXT,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
)
"""

SOURCE_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (julianday('now'))
)
"""

SOURCE_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_files_path ON files(relative_path)",
    "CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)",
    "CREATE INDEX IF NOT EXISTS idx_files_category ON files(category)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_type ON vocabularies(type)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name ON vocabularies(name)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower ON vocabularies(name_lower)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower_rev ON vocabularies(name_lower_rev)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_file_id ON vocabularies(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_vector_status ON vocabularies(vector_status)",
]


# ============================================================
# AST/语义分析增强表（Schema v3+）
# ============================================================

# vocabularies 表 AST 增强列（ALTER TABLE ADD COLUMN 迁移）
# 注意: 注释写在 Python 侧，不要混在 SQL 字符串中（pyright 会误报）
VOCABULARIES_AST_COLUMNS_SQL: List[str] = [
    "ALTER TABLE vocabularies ADD COLUMN end_line INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN end_offset INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN body_length INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN code_block TEXT",
    "ALTER TABLE vocabularies ADD COLUMN signature TEXT",
    "ALTER TABLE vocabularies ADD COLUMN modifiers TEXT",
    "ALTER TABLE vocabularies ADD COLUMN visibility TEXT",
    "ALTER TABLE vocabularies ADD COLUMN type_refs TEXT",
    "ALTER TABLE vocabularies ADD COLUMN member_count INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN inheritance_chain TEXT",
    "ALTER TABLE vocabularies ADD COLUMN generics TEXT",
    "ALTER TABLE vocabularies ADD COLUMN values TEXT",
    "ALTER TABLE vocabularies ADD COLUMN params TEXT",
    "ALTER TABLE vocabularies ADD COLUMN return_type TEXT",
    "ALTER TABLE vocabularies ADD COLUMN calls TEXT",
    "ALTER TABLE vocabularies ADD COLUMN ref_count INTEGER DEFAULT 0",
    "ALTER TABLE vocabularies ADD COLUMN source TEXT DEFAULT 'regex'",
]

# 实体引用关系表（引用图谱基础）
ENTITY_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_name TEXT NOT NULL,
    target_kind TEXT,
    target_file_id INTEGER,
    ref_type TEXT NOT NULL,
    line INTEGER,
    code_snippet TEXT,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (source_id) REFERENCES vocabularies(id) ON DELETE CASCADE
)
"""

ENTITY_REFS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_source ON entity_refs(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_target ON entity_refs(target_name, target_kind)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_target_file ON entity_refs(target_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_type ON entity_refs(ref_type)",
]

# 审计结果缓存表
AUDIT_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    line INTEGER,
    code_snippet TEXT,
    message TEXT,
    is_ai_confirmed INTEGER DEFAULT 0,
    fix_suggestion TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    UNIQUE(project_path, file_path, rule_id, line)
)
"""

AUDIT_RESULTS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_results(project_path)",
    "CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_results(severity)",
    "CREATE INDEX IF NOT EXISTS idx_audit_rule ON audit_results(rule_id)",
]


def create_source_tables(cursor):
    """创建源码知识库的所有表 + 索引"""
    cursor.execute(SOURCE_FILES_TABLE_SQL)
    cursor.execute(SOURCE_VOCABULARIES_TABLE_SQL)
    cursor.execute(SOURCE_METADATA_TABLE_SQL)
    for sql in SOURCE_INDEXES_SQL:
        cursor.execute(sql)


def drop_source_tables(cursor):
    """删除源码知识库的所有表"""
    cursor.execute("DROP TABLE IF EXISTS audit_results")
    cursor.execute("DROP TABLE IF EXISTS entity_refs")
    cursor.execute("DROP TABLE IF EXISTS vocabularies")
    cursor.execute("DROP TABLE IF EXISTS files")
    cursor.execute("DROP TABLE IF EXISTS metadata")


def migrate_vocabularies_ast_columns(cursor):
    """
    迁移: vocabularies 表增加 AST 增强列（Schema v2 → v3）
    安全幂等: 每列 ADD COLUMN 后有 IF NOT EXISTS 等效检查。
    对于已存在的列会抛出 SQL 异常，忽略即可。
    """
    for sql in VOCABULARIES_AST_COLUMNS_SQL:
        try:
            cursor.execute(sql)
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            pass  # 列已存在，忽略
    logger.info("vocabularies AST 增强列迁移完成")


def create_ast_tables(cursor):
    """创建 AST/语义分析增强表（entity_refs + audit_results）"""
    cursor.execute(ENTITY_REFS_TABLE_SQL)
    for sql in ENTITY_REFS_INDEXES_SQL:
        cursor.execute(sql)
    cursor.execute(AUDIT_RESULTS_TABLE_SQL)
    for sql in AUDIT_RESULTS_INDEXES_SQL:
        cursor.execute(sql)


def drop_ast_tables(cursor):
    """删除 AST 增强表"""
    cursor.execute("DROP TABLE IF EXISTS audit_results")
    cursor.execute("DROP TABLE IF EXISTS entity_refs")


# ============================================================
# 文档知识库表结构（documents / document_entities + FTS5）
# ============================================================

DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    full_path TEXT NOT NULL,
    extension TEXT,
    title TEXT,
    title_lower TEXT,
    title_rev TEXT,
    content TEXT,
    content_type TEXT,
    file_size INTEGER,
    size INTEGER,
    line_count INTEGER,
    hash TEXT,
    last_modified TEXT,
    sections TEXT,
    code_examples TEXT,
    url TEXT,
    requires_extraction INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en'
)
"""

DOCUMENT_ENTITIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS document_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    definition TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id)
)
"""

DOCUMENTS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)",
    "CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(hash)",
    "CREATE INDEX IF NOT EXISTS idx_documents_title_lower ON documents(title_lower)",
    "CREATE INDEX IF NOT EXISTS idx_documents_title_rev ON documents(title_rev)",
    "CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language)",
    "CREATE INDEX IF NOT EXISTS idx_document_entities_name ON document_entities(name)",
]

# 文档知识库也使用统一的 metadata 表记录构建信息
DOCUMENTS_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (julianday('now'))
)
"""


def create_document_tables(cursor):
    """创建文档知识库的所有表 + 索引"""
    cursor.execute(DOCUMENTS_TABLE_SQL)
    cursor.execute(DOCUMENT_ENTITIES_TABLE_SQL)
    cursor.execute(DOCUMENTS_METADATA_TABLE_SQL)
    for sql in DOCUMENTS_INDEXES_SQL:
        cursor.execute(sql)


def drop_document_tables(cursor):
    """删除文档知识库的所有表"""
    cursor.execute("DROP TABLE IF EXISTS document_entities")
    cursor.execute("DROP TABLE IF EXISTS documents")
    cursor.execute("DROP TABLE IF EXISTS metadata")


# ============================================================
# 通用 PRAGMA 设置
# ============================================================

def get_connection(db_path: str, use_wal: bool = True) -> sqlite3.Connection:
    """
    创建 SQLite 连接并应用统一的性能 PRAGMA 设置。

    所有知识库代码应通过此函数获取连接，确保:
    - PRAGMA 设置一致（避免 WAL/DELETE 混用导致 locked）
    - busy_timeout 统一（避免 database is locked）
    - 后续可集中调整连接参数

    Args:
        db_path: 数据库文件路径
        use_wal: 是否使用 WAL 模式（构建=WAL 提升写性能，查询=DELETE 避免 .wal 残留）

    Returns:
        配置好的 sqlite3.Connection
    """
    conn = sqlite3.connect(str(db_path))
    apply_performance_pragmas(conn, use_wal=use_wal)
    return conn


@contextlib.contextmanager
def use_connection(db_path: str, use_wal: bool = True) -> Iterator[sqlite3.Connection]:
    """
    安全上下文: 创建连接 → yield → 自动关闭。
    即使中间抛异常也能保证 conn.close() 被调用，避免资源泄漏。

    Args:
        db_path: 数据库文件路径
        use_wal: 是否使用 WAL 模式

    Yields:
        sqlite3.Connection
    """
    conn = None
    try:
        conn = get_connection(db_path, use_wal=use_wal)
        yield conn
    finally:
        if conn is not None:
            conn.close()


def apply_performance_pragmas(conn, use_wal: bool = False):
    """
    应用 SQLite 性能优化 PRAGMA

    Args:
        conn: SQLite 连接
        use_wal: 是否使用 WAL 模式。统一使用 WAL 避免模式切换冲突
                 （DELETE 模式需要独占锁，同一 DB 已有 WAL 连接时会 locked）
    """
    if use_wal:
        conn.execute("PRAGMA journal_mode=WAL")
    else:
        # 查询也使用 WAL 模式，避免与已有 WAL 连接冲突
        # PRAGMA journal_mode=DELETE 需要独占锁，会报 database is locked
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA locking_mode=NORMAL")


__all__ = [
    'SCHEMA_VERSION',
    'SCHEMA_VERSION_KEY',
    'get_schema_version_from_db',
    'set_schema_version_in_db',
    'check_schema_version',
    'SOURCE_FILES_TABLE_SQL',
    'SOURCE_VOCABULARIES_TABLE_SQL',
    'SOURCE_METADATA_TABLE_SQL',
    'SOURCE_INDEXES_SQL',
    'VOCABULARIES_AST_COLUMNS_SQL',
    'ENTITY_REFS_TABLE_SQL',
    'ENTITY_REFS_INDEXES_SQL',
    'AUDIT_RESULTS_TABLE_SQL',
    'AUDIT_RESULTS_INDEXES_SQL',
    'create_source_tables',
    'drop_source_tables',
    'migrate_vocabularies_ast_columns',
    'create_ast_tables',
    'drop_ast_tables',
    'DOCUMENTS_TABLE_SQL',
    'DOCUMENT_ENTITIES_TABLE_SQL',
    'DOCUMENTS_INDEXES_SQL',
    'create_document_tables',
    'drop_document_tables',
    'get_connection',
    'use_connection',
    'apply_performance_pragmas',
]
