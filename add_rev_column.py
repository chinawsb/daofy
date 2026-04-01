#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
添加 name_lower_rev 列用于反转匹配
"""

import sqlite3

conn = sqlite3.connect('data/delphi-knowledge-base/knowledge.sqlite')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 添加 name_lower_rev 列
print("添加 name_lower_rev 列...")
try:
    cursor.execute("ALTER TABLE entities ADD COLUMN name_lower_rev TEXT")
except Exception as e:
    print(f"列已存在或添加失败: {e}")

# 更新 name_lower_rev
print("更新反转名称...")
cursor.execute("SELECT COUNT(*) FROM entities WHERE name_lower_rev IS NULL")
count = cursor.fetchone()[0]
print(f"需要更新 {count} 条记录...")

# 批量更新 (分批处理)
print("批量更新中...")
batch_size = 10000
offset = 0

while True:
    cursor.execute("SELECT id, name FROM entities WHERE name_lower_rev IS NULL LIMIT ?", (batch_size,))
    rows = cursor.fetchall()
    
    if not rows:
        break
    
    for row in rows:
        rev_name = row['name'][::-1].lower() if row['name'] else ''
        cursor.execute("UPDATE entities SET name_lower_rev = ? WHERE id = ?", (rev_name, row['id']))
    
    conn.commit()
    offset += len(rows)
    print(f"  已更新 {offset}/{count} 条...")

print("完成!")

# 验证
cursor.execute("SELECT COUNT(*) FROM entities WHERE name_lower_rev IS NOT NULL")
updated = cursor.fetchone()[0]
print(f"已更新 {updated} 条记录")

conn.close()
