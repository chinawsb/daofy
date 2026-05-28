#!/usr/bin/env python3
"""
Daofy 平台性能基准测试套件 — 运行器

依次运行所有基准测试，汇总结果。

用法:
    python benchmarks/run_all.py                    # 默认运行全部
    python benchmarks/run_all.py --skip-kb          # 跳过 KB 测试（KB 未构建时）
    python benchmarks/run_all.py --output results.md # 输出 Markdown 报告

测试内容:
    1. MAPDATA V4 压缩率模拟    (mapdata_v4_sim.py)
    2. EBP-Offset 扫描基准      (ebp_scan.py)
    3. KB 查询性能              (kb_perf.py)
    4. VEH 延迟 (需要 Pascal 编译: veh_latency.dpr)
"""

import sys
import os
import subprocess
import time
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')
BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
TUTORIAL_DIR = os.path.join(BASE_DIR, 'docs', 'tutorial')
TEST_MAP = os.path.join(TUTORIAL_DIR, 'test-project', 'Win32', 'Debug', 'TestProject.map')
TEST_EXE = os.path.join(TUTORIAL_DIR, 'test-project', 'Win32', 'Debug', 'TestProject.exe')


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def run_benchmark(name: str, script: str, args: list = None) -> dict:
    """运行一个基准测试脚本并捕获输出"""
    print(f'\n{"=" * 60}')
    print(f'  [{name}]')
    print(f'{"=" * 60}')
    print()

    script_path = os.path.join(os.path.dirname(__file__), script)
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)

    stdout_lines = []
    stderr_lines = []
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
            encoding='utf-8',
            errors='replace'
        )
        elapsed = time.time() - start
        stdout_lines = result.stdout.splitlines()
        stderr_lines = result.stderr.splitlines()

        # 打印输出 (safe encode for Windows console)
        for line in stdout_lines:
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode('utf-8', errors='replace').decode('utf-8'))

        if result.stderr.strip():
            print(f'\n  [STDERR]')
            for line in stderr_lines:
                print(f'  {line}')

        success = result.returncode == 0

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f'\n  [TIMEOUT] Exceeded 300 seconds')
        success = False
    except Exception as e:
        elapsed = time.time() - start
        print(f'\n  [ERROR] {e}')
        success = False

    print()
    return {
        'name': name,
        'success': success,
        'elapsed_s': round(elapsed, 2),
        'output': '\n'.join(stdout_lines),
        'errors': '\n'.join(stderr_lines) if stderr_lines else '',
    }


def check_prerequisites():
    """检查前置条件"""
    print('Checking prerequisites...')
    checks = []

    # .map 文件
    has_map = os.path.exists(TEST_MAP)
    checks.append(('TestProject.map', has_map))
    if not has_map:
        print('  ⚠️  TestProject.map not found. Run compile_project first.')

    # .exe 文件
    has_exe = os.path.exists(TEST_EXE)
    checks.append(('TestProject.exe', has_exe))

    # KB （只检查数据目录）
    kb_dir = os.path.join(BASE_DIR, 'data', 'delphi-knowledge-base')
    has_kb = os.path.exists(os.path.join(kb_dir, 'knowledge_base.sqlite')) or \
             os.path.exists(os.path.join(kb_dir, 'documents.sqlite'))
    checks.append(('Delphi Knowledge Base', has_kb))
    if not has_kb:
        print('  ⚠️  Delphi KB not built. Run delphi_kb(action=build, kb_type=delphi) first.')

    print()
    return {
        'has_map': has_map,
        'has_exe': has_exe,
        'has_kb': has_kb,
    }


def generate_report(results: list, prereqs: dict):
    """生成 Markdown 格式的结果报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    report_path = os.path.join(RESULTS_DIR, f'benchmark_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md')

    lines = [
        f'# Daofy 平台性能基准测试报告',
        f'',
        f'**测试时间**: {now}',
        f'**运行环境**: {sys.platform}',
        f'**Python**: {sys.version}',
        f'',
        f'## 前置条件',
        f'',
        f'| 资源 | 状态 |',
        f'|------|------|',
    ]

    for name, present in [
        ('TestProject.map', prereqs['has_map']),
        ('TestProject.exe', prereqs['has_exe']),
        ('Delphi Knowledge Base', prereqs['has_kb']),
    ]:
        status = 'Yes' if present else 'No'
        lines.append(f'| {name} | {status} |')

    lines.extend([
        f'',
        f'## 测试结果',
        f'',
        f'| 测试 | 状态 | 耗时 |',
        f'|------|------|------|',
    ])

    for r in results:
        status = 'PASS' if r['success'] else 'FAIL'
        lines.append(f'| {r["name"]} | {status} | {r["elapsed_s"]}s |')

    lines.extend([
        f'',
        f'## 详细输出',
        f'',
    ])

    for r in results:
        lines.extend([
            f'### {r["name"]}',
            f'',
            f'```',
            r['output'],
            f'```',
            f'',
        ])

        if r['errors']:
            lines.extend([
                f'**错误输出**:',
                f'```',
                r['errors'],
                f'```',
                f'',
            ])

    report = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\nReport saved to: {report_path}')
    return report_path


def main():
    parser = argparse.ArgumentParser(description='Daofy Platform Benchmark Suite')
    parser.add_argument('--skip-kb', action='store_true', help='Skip KB benchmarks')
    parser.add_argument('--skip-ebp', action='store_true', help='Skip EBP scan benchmark')
    parser.add_argument('--skip-mapdata', action='store_true', help='Skip MAPDATA simulation')
    parser.add_argument('--output', type=str, help='Output report path (default: auto)')
    args = parser.parse_args()

    print('=' * 60)
    print('  Daofy Platform Benchmark Suite')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)
    print()

    ensure_results_dir()
    prereqs = check_prerequisites()
    results = []

    # 1. MAPDATA V4 模拟
    if not args.skip_mapdata and prereqs['has_map']:
        results.append(run_benchmark(
            'MAPDATA V4 Compression',
            'mapdata_v4_sim.py',
            [TEST_MAP]
        ))
    else:
        print('[SKIP] MAPDATA V4 simulation\n')

    # 2. EBP-Offset 扫描
    if not args.skip_ebp and prereqs['has_map']:
        exe_args = [TEST_MAP]
        if prereqs['has_exe']:
            exe_args.append(TEST_EXE)
        results.append(run_benchmark(
            'EBP-Offset Scan',
            'ebp_scan.py',
            exe_args
        ))
    else:
        print('[SKIP] EBP-Offset scan\n')

    # 3. KB 性能
    if not args.skip_kb and prereqs['has_kb']:
        results.append(run_benchmark(
            'Knowledge Base Performance',
            'kb_perf.py'
        ))
    else:
        print('[SKIP] KB performance\n')

    # 4. VEH 延迟 — 需要先编译 Pascal 程序
    print()
    veh_exe = os.path.join(os.path.dirname(__file__), 'veh_latency.exe')
    if os.path.exists(veh_exe):
        print('Found precompiled veh_latency.exe, running...')
        start = time.time()
        result = subprocess.run([veh_exe], capture_output=True, text=True, timeout=60)
        elapsed = time.time() - start
        # Replace non-ASCII chars for markdown safety
        safe_out = result.stdout.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        safe_err = result.stderr.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        results.append({
            'name': 'VEH Latency',
            'success': result.returncode == 0,
            'elapsed_s': round(elapsed, 2),
            'output': safe_out,
            'errors': safe_err,
        })
        for line in result.stdout.splitlines():
            safe = line.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            print(safe)
    else:
        print('[SKIP] VEH latency — compile veh_latency.dpr first:')
        print('  To compile: use compile_project with a .dproj wrapping veh_latency.dpr')
        print('  Or: dcc32 -CC -B benchmarks/veh_latency.dpr')

    # 汇总
    print('=' * 60)
    print('  Summary')
    print('=' * 60)
    print(f'\n  {"Benchmark":<30} {"Status":>8} {"Time":>8}')
    print(f'  {"-"*48}')
    for r in results:
        status = '[PASS]' if r['success'] else '[FAIL]'
        print(f'  {r["name"]:<30} {status:>8} {r["elapsed_s"]:>7.1f}s')

    passed = sum(1 for r in results if r['success'])
    total = len(results)
    print(f'\n  Passed: {passed}/{total}\n')

    # 生成报告
    report_path = generate_report(results, prereqs)
    print(f'\nDone. Report: {report_path}')


if __name__ == '__main__':
    main()
