"""
知识库模块

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
"""

# 统一 schema 管理
from .schema import (
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    get_schema_version_from_db,
    set_schema_version_in_db,
    check_schema_version,
    create_source_tables,
    drop_source_tables,
    create_document_tables,
    drop_document_tables,
    apply_performance_pragmas,
)

__all__ = [
    'SCHEMA_VERSION',
    'SCHEMA_VERSION_KEY',
    'get_schema_version_from_db',
    'set_schema_version_in_db',
    'check_schema_version',
    'create_source_tables',
    'drop_source_tables',
    'create_document_tables',
    'drop_document_tables',
    'apply_performance_pragmas',
]
