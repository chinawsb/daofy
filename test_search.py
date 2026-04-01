import sys
sys.path.insert(0, 'src')
from src.services.knowledge_base.sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase

kb = SQLiteVectorKnowledgeBase('data/delphi-knowledge-base')

print('=== 测试反转匹配搜索 ===')

keywords = ['Create', 'Button']
results = kb.search_by_keywords(keywords, kind_filter=['TC', 'FF', 'FP'])

print(f'搜索: {keywords}')
print(f'找到 {len(results)} 个结果')

for r in results[:10]:
    print(f"  {r['name']} ({r['kind']})")
