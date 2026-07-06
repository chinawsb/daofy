import sqlite3, json

conn = sqlite3.connect('data/experience-knowledge-base/experiences.sqlite')
c = conn.cursor()

# Basic stats
c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_vec, SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) as without_vec FROM experiences")
r = c.fetchone()
total = r[0]
with_vec = r[1]
without_vec = r[2]
print(f"=== 经验库概览 ===")
print(f"总记录数: {total}")
print(f"有向量: {with_vec}")
print(f"无向量: {without_vec}")
print()

# Hit count distribution
c.execute("SELECT hit_count, COUNT(*) FROM experiences GROUP BY hit_count ORDER BY hit_count")
hits = c.fetchall()
print(f"=== Hit 分布 ===")
for h, cnt in hits:
    print(f"  {h}次: {cnt}条")
print()

# Tag distribution
c.execute("SELECT tags FROM experiences")
all_tags = {}
for row in c.fetchall():
    t = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or [])
    for tag in t:
        all_tags[tag] = all_tags.get(tag, 0) + 1
print(f"=== 标签分布 ===")
for k, v in sorted(all_tags.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}条")
print()

# All records
c.execute("SELECT id, problem, tags, hit_count, score, updated_at FROM experiences ORDER BY updated_at DESC")
rows = c.fetchall()
print(f"=== 所有经验记录 (按更新时间倒序) ===")
for r in rows:
    eid = r[0][:12]
    problem = r[1][:120]
    tags = r[2][:80] if r[2] else "[]"
    hits = r[3]
    score = r[4]
    updated = r[5]
    print(f"\n  [{eid}] hits={hits} score={score}")
    print(f"    problem: {problem}")
    print(f"    tags:     {tags}")
    print(f"    updated:  {updated}")

conn.close()
