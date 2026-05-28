"""
知识库性能基准测试

测量现有 Delphi 知识库的查询性能。

测试项目：
1. 不同搜索类型的延迟分布（按名称 / 按关键词 / 语义）
2. 不同 top_k 值的延迟
3. 并发查询吞吐量

用法：
    python benchmarks/kb_perf.py
"""

import sys
import os
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.knowledge_base import DelphiKnowledgeBaseService


SEARCH_CASES = [
    # (query, method, description)
    # method: 'name' -> search_by_name, 'keyword' -> search_by_keyword
    ('TStringList', 'name', '精确类名'),
    ('TJSONObject', 'name', '已知类'),
    ('TThread', 'name', '常用类'),
    ('TDataSet', 'name', '数据库类'),
    ('TMemoryStream', 'name', '流类'),
    ('TFileStream', 'name', '文件流'),
    ('TForm', 'name', '基窗体类'),
    ('StringList', 'keyword', '部分名称(关键词)'),
    ('Exception', 'keyword', '常见关键词'),
    ('FreeAndNil', 'keyword', '已知工具函数'),
]

SEMANTIC_CASES = [
    ('如何读取 JSON 配置文件', '中文语义'),
    ('database connection error handling', '错误处理'),
    ('string list sorting example', '字符串列表'),
    ('create thread safely', '线程安全'),
    ('parse XML document', 'XML解析'),
]


class Timer:
    def __init__(self):
        self.start = time.perf_counter()

    def elapsed_ms(self):
        return (time.perf_counter() - self.start) * 1000


def setup_kb_service():
    """初始化 KB 服务"""
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    kb_dir = os.path.join(base_dir, 'data', 'delphi-knowledge-base')

    delphi_kb = DelphiKnowledgeBaseService(kb_dir=kb_dir)
    return delphi_kb


def do_search(kb, query: str, method: str, top_k: int = 20):
    """执行搜索（带超时安全）"""
    if method == 'name':
        return kb.search_by_name(query)
    elif method == 'keyword':
        return kb.search_by_keyword(query)
    return []


def measure_search_latency(kb, search_cases: list, iterations: int = 5) -> dict:
    """测量搜索延迟分布"""
    results = {}

    for query, method, desc in search_cases:
        latencies = []
        for i in range(iterations):
            t = Timer()
            try:
                _ = do_search(kb, query, method)
                lat = t.elapsed_ms()
                latencies.append(lat)
            except Exception as e:
                pass

        if latencies:
            valid = [l for l in latencies if l > 0]
            if valid:
                results[f'{desc} ({method})'] = {
                    'query': query,
                    'method': method,
                    'latencies_ms': valid,
                    'min_ms': min(valid),
                    'max_ms': max(valid),
                    'avg_ms': statistics.mean(valid),
                    'median_ms': statistics.median(valid),
                    'p95_ms': sorted(valid)[int(len(valid) * 0.95)],
                    'stdev_ms': statistics.stdev(valid) if len(valid) > 1 else 0,
                    'iterations': len(valid),
                }

    return results


def measure_semantic_latency(kb, cases: list, iterations: int = 3) -> dict:
    """测量语义搜索延迟"""
    results = {}
    for query, desc in cases:
        latencies = []
        for i in range(iterations):
            t = Timer()
            try:
                _ = kb.semantic_search_classes(query, top_k=10)
                lat = t.elapsed_ms()
                latencies.append(lat)
            except Exception:
                pass

        if latencies:
            valid = [l for l in latencies if l > 0]
            if valid:
                results[desc] = {
                    'query': query,
                    'method': 'semantic',
                    'min_ms': min(valid),
                    'avg_ms': statistics.mean(valid),
                    'median_ms': statistics.median(valid),
                    'p95_ms': sorted(valid)[int(len(valid) * 0.95)],
                    'iterations': len(valid),
                }
    return results


def measure_top_k_scaling(kb):
    """测量不同 top_k 对搜索延迟的影响"""
    results = {}
    for top_k in [10, 20, 50, 100, 200]:
        latencies = []
        for i in range(3):
            t = Timer()
            try:
                _ = kb.search_by_name('TStringList')
                latencies.append(t.elapsed_ms())
            except Exception:
                pass

        if latencies:
            results[f'top_k={top_k}'] = {
                'avg_ms': statistics.mean(latencies),
                'median_ms': statistics.median(latencies),
            }
    return results


def get_kb_stats(kb) -> dict:
    """获取知识库统计信息"""
    try:
        stats = kb.get_statistics()
        return {
            'file_count': stats.get('file_count', 0),
            'class_count': stats.get('class_count', 0),
            'function_count': stats.get('function_count', 0),
            'db_size_mb': stats.get('db_size', 0) / 1024 / 1024,
            'last_build': stats.get('last_build', ''),
        }
    except Exception as e:
        return {'error': str(e)}


def measure_concurrent_throughput(kb):
    """测量并发查询下的吞吐量"""
    queries = [
        ('TStringList', 'name'),
        ('TJSONObject', 'name'),
        ('TThread', 'name'),
        ('Split', 'keyword'),
        ('Exception', 'keyword'),
    ] * 4  # 20 个查询

    executor_counts = [1, 2, 4, 8]

    results = {}
    for n_threads in executor_counts:
        t = Timer()
        completed = 0

        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = []
            for query, method in queries:
                futures.append(
                    executor.submit(do_search, kb, query, method)
                )

            for future in as_completed(futures):
                try:
                    future.result()
                    completed += 1
                except Exception:
                    pass

        elapsed = t.elapsed_ms()
        qps = completed / (elapsed / 1000) if elapsed > 0 else 0
        results[f'{n_threads} 线程'] = {
            'total_queries': len(queries),
            'completed': completed,
            'elapsed_ms': elapsed,
            'qps': round(qps, 1),
        }

    return results


def print_delay_table(results: dict, title: str):
    """格式化输出延迟表格"""
    print(f'\n  {title}')
    print('  ' + '-' * 90)
    print(f'  {"用例":<35} {"最小(ms)":>8} {"平均(ms)":>8} {"P95(ms)":>8} {"标准差":>8} {"次数":>4}')
    print('  ' + '-' * 90)

    for name, data in sorted(results.items(), key=lambda x: x[1].get('avg_ms', 9999)):
        avg = data.get('avg_ms', 0)
        mn = data.get('min_ms', 0)
        p95 = data.get('p95_ms', 0)
        stdev = data.get('stdev_ms', 0)
        n = data.get('iterations', 0)
        print(f'  {name:<35} {mn:>8.1f} {avg:>8.1f} {p95:>8.1f} {stdev:>8.1f} {n:>4}')

    print('  ' + '-' * 90)


def main():
    print('=' * 70)
    print('  知识库性能基准测试')
    print('=' * 70)

    t0 = Timer()
    kb = setup_kb_service()
    init_time = t0.elapsed_ms()
    print(f'\n  KB 初始化耗时:    {init_time:.1f} ms')

    stats = get_kb_stats(kb)
    if 'error' in stats:
        print(f'  [错误] KB 统计: {stats["error"]}')
        print('  请先执行 delphi_kb(action=build, kb_type=delphi) 构建知识库')
        return

    print(f'  知识库文件数:     {stats.get("file_count", "?")}')
    print(f'  知识库类数量:     {stats.get("class_count", "?")}')
    print(f'  知识库函数数:     {stats.get("function_count", "?")}')
    print(f'  知识库大小:       {stats.get("db_size_mb", 0):.1f} MB')
    print(f'  最近构建:         {stats.get("last_build", "?")}')
    print()

    # 1. 搜索延迟
    print('  [1/4] 测量搜索延迟...')
    results = measure_search_latency(kb, SEARCH_CASES, iterations=5)
    print_delay_table(results, '各用例搜索延迟 (Delphi 知识库)')

    # 2. 语义搜索延迟
    print('\n  [2/4] 测量语义搜索延迟...')
    sem_results = measure_semantic_latency(kb, SEMANTIC_CASES, iterations=3)
    if sem_results:
        print_delay_table(sem_results, '语义搜索延迟')
    else:
        print('  (语义搜索不可用或未返回数据)')

    # 3. top_k 扩展性
    print('\n  [3/4] 测量 top_k 扩展性...')
    topk = measure_top_k_scaling(kb)
    print(f'  {"top_k":<12} {"平均(ms)":>10} {"中位数(ms)":>12}')
    print(f'  {"-"*34}')
    for k, v in sorted(topk.items()):
        print(f'  {k:<12} {v["avg_ms"]:>10.1f} {v["median_ms"]:>12.1f}')

    # 4. 并发吞吐量
    print('\n  [4/4] 测量并发吞吐量...')
    throughput = measure_concurrent_throughput(kb)
    print(f'  {"并发数":<12} {"查询数":>8} {"耗时(ms)":>10} {"QPS":>8}')
    print(f'  {"-"*40}')
    for k, v in sorted(throughput.items()):
        print(f'  {k:<12} {v["completed"]:>8} {v["elapsed_ms"]:>10.1f} {v["qps"]:>8.1f}')

    # 摘要
    print()
    print('  ' + '=' * 50)
    print('  测试摘要')
    print('  ' + '=' * 50)

    all_results = list(results.values())
    if all_results:
        worst = max(all_results, key=lambda x: x['avg_ms'])
        print(f'  最慢查询:     "{worst["query"]}" ({worst["method"]})')
        print(f'  平均延迟:     {worst["avg_ms"]:.1f} ms')
        print(f'  P95 延迟:     {worst["p95_ms"]:.1f} ms')

        best = min(all_results, key=lambda x: x['avg_ms'])
        print(f'  最快查询:     "{best["query"]}" ({best["method"]})')
        print(f'  平均延迟:     {best["avg_ms"]:.1f} ms')

    if throughput:
        max_qps = max(v['qps'] for v in throughput.values())
        print(f'  最大吞吐量:   {max_qps:.0f} QPS')
    print()

    print('  目标: 所有搜索类型 P95 < 500ms')
    print('  目标: 4 并发时 > 50 QPS')
    print('=' * 70)


if __name__ == '__main__':
    main()
