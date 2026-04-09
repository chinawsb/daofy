import sys
import os
import sqlite3
from pathlib import Path
import time
import re

os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=== 重建 Delphi 知识库 (单线程) ===")

source_dir = r"C:\Program Files (x86)\Embarcadero\Studio\23.0\source"

if not os.path.exists(source_dir):
    print(f"源码目录不存在: {source_dir}")
    sys.exit(1)

source_path = Path(source_dir)
pas_files = list(source_path.rglob("*.pas"))
print(f"找到 {len(pas_files)} 个 .pas 文件")

# 创建数据库
kb_dir = Path("C:/User/cloudAttendance/service/delphi-complier-mcp-server/data/delphi-knowledge-base")
kb_dir.mkdir(parents=True, exist_ok=True)
db_path = kb_dir / "knowledge.sqlite"

print("创建数据库...")
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA journal_mode=WAL")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT,
        hash TEXT,
        scan_date TEXT,
        created_at REAL,
        updated_at REAL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        path TEXT,
        full_path TEXT,
        relative_path TEXT,
        extension TEXT,
        size INTEGER,
        line_count INTEGER,
        hash TEXT,
        last_modified TEXT,
        units TEXT,
        uses TEXT,
        category TEXT,
        description TEXT,
        scan_timestamp REAL,
        created_at REAL,
        updated_at REAL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS vocabularies (
        id INTEGER PRIMARY KEY,
        type TEXT,
        name TEXT,
        name_lower TEXT,
        file_id INTEGER,
        line INTEGER,
        base_class TEXT,
        description TEXT,
        vector BLOB,
        vector_status TEXT,
        attributes TEXT,
        created_at REAL,
        updated_at REAL
    )
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_name_lower ON vocabularies(name_lower)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_file_id ON vocabularies(file_id)")
conn.commit()

# 正则表达式 - 匹配类/类型定义
# 支持: type TStringList = class; / TStringList = class(TStrings) / type TMyType = Integer;
class_pattern = re.compile(r'^\s*(type|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|:)?\s*(?:class|interface|record)?', re.MULTILINE | re.IGNORECASE)
# 匹配 X = class(without type keyword)
class_no_type_pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*class', re.MULTILINE | re.IGNORECASE)
# 单独匹配 type X = Y 形式
type_alias_pattern = re.compile(r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\n;]+)', re.MULTILINE | re.IGNORECASE)
# 匹配 record 定义
record_pattern = re.compile(r'^\s*record\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE | re.IGNORECASE)
# 匹配 interface 定义  
interface_pattern = re.compile(r'^\s*interface\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE | re.IGNORECASE)
func_pattern = re.compile(r'^\s*(function|procedure)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(\;]', re.MULTILINE | re.IGNORECASE)
const_pattern = re.compile(r'^\s*const\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE | re.IGNORECASE)

now = time.time()

for i, file_path in enumerate(pas_files):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.count('\n') + 1
        
        cur.execute("""
            INSERT INTO files (full_path, path, relative_path, extension, size, line_count, description, hash, last_modified, units, uses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(file_path), '', file_path.name, '.pas', file_path.stat().st_size, lines, 'delphi', '', '', '[]', '[]'))
        
        file_id = cur.lastrowid
        
        # 类定义 (type X = class 或 class X)
        for match in class_pattern.finditer(content):
            kind = match.group(1).lower()
            type_kind = 'TC'  # class
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type_kind, match.group(2), match.group(2).lower(), file_id, line_num, '', kind, 'pending', now, now))
        
        # 类定义 (X = class, without type keyword)
        for match in class_no_type_pattern.finditer(content):
            type_kind = 'TC'
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type_kind, match.group(1), match.group(1).lower(), file_id, line_num, '', 'class', 'pending', now, now))
        
        # 类型别名 (type TMyType = Integer)
        for match in type_alias_pattern.finditer(content):
            type_kind = 'TY'
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type_kind, match.group(1), match.group(1).lower(), file_id, line_num, '', 'type', 'pending', now, now))
        
        # record 定义
        for match in record_pattern.finditer(content):
            type_kind = 'TR'
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type_kind, match.group(1), match.group(1).lower(), file_id, line_num, '', 'record', 'pending', now, now))
        
        # interface 定义
        for match in interface_pattern.finditer(content):
            type_kind = 'TI'
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type_kind, match.group(1), match.group(1).lower(), file_id, line_num, '', 'interface', 'pending', now, now))
        
        # 函数/过程
        for match in func_pattern.finditer(content):
            kind = 'FF' if match.group(1).lower() == 'function' else 'FP'
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (kind, match.group(2), match.group(2).lower(), file_id, line_num, '', '', 'pending', now, now))
        
        # 常量
        for match in const_pattern.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            cur.execute("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, description, vector_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ('CC', match.group(1), match.group(1).lower(), file_id, line_num, '', '', 'pending', now, now))
        
        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"已处理 {i + 1}/{len(pas_files)} 个文件")
            
    except Exception as e:
        pass

conn.commit()

cur.execute("SELECT COUNT(*) FROM files")
fc = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM vocabularies")
vc = cur.fetchone()[0]

# Insert metadata
cur.execute("""
    INSERT OR REPLACE INTO metadata (key, value, scan_date, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?)
""", ('total_files', str(fc), time.strftime('%Y-%m-%d %H:%M:%S'), now, now))
cur.execute("""
    INSERT OR REPLACE INTO metadata (key, value, scan_date, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?)
""", ('total_vocabularies', str(vc), time.strftime('%Y-%m-%d %H:%M:%S'), now, now))
conn.commit()

print(f"\n完成! files: {fc}, vocabularies: {vc}")
conn.close()