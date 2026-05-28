"""
MAPDATA V4 压缩率基准测试 (v2 — 适配 Delphi .map 实际格式)

模拟 MAPDATA V4 序列化流程，测量真实 .map 文件上的压缩效果。
适配 Delphi DCC_MapFile=3 输出的 .map 格式。

用法:
    python benchmarks/mapdata_v4_sim.py <path/to/project.map>
"""

import sys
import os
import re
import math
import time
from collections import Counter
from typing import List, Tuple, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def parse_map_file(path: str) -> dict:
    """
    解析 Delphi .map 文件 (DCC_MapFile=3)
    
    Delphi .map 格式:
      段表(顶部):  0001:00401000 001FB634H .text CODE
      详细段:      0001:00000000 0000FEB4 C=CODE S=.text G=(none) M=System ACBP=A9
      符号(by Name):  0001:0000FF0C       SysInit.GetProcAddress
      符号(by Value): 0001:0000FF0C 00000001 SysInit.GetProcAddress
    """
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    result = {
        'segments': [],       # 段表
        'symbols': [],        # 符号表
        'line_numbers': [],   # 行号映射
        'segment_count': 0,
        'symbol_count': 0,
        'line_number_count': 0,
        'raw_size': os.path.getsize(path),
        'raw_lines': len(lines),
    }

    section = None
    for line in lines:
        stripped = line.strip()
        
        # ===== 段表（顶部区域，在 "Detailed map" 之前）=====
        # 段表头: " Start         Length     Name                   Class"
        if 'Start' in stripped and 'Length' in stripped and 'Name' in stripped:
            section = 'segments'
            continue
        
        if section == 'segments':
            # 段表数据行: "0001:00401000 001FB634H .text CODE"
            m = re.match(r'^(\w+):([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)H?\s+(\S+)', stripped)
            if m:
                result['segments'].append({
                    'number': int(m.group(1), 16),
                    'start': int(m.group(2), 16),
                    'length': int(m.group(3), 16),
                    'name': m.group(4),
                })
                continue

        # 跳过 Detailed map 区域（太细了，不在这里解析）
        if stripped.startswith('Detailed map of segments'):
            section = 'detailed'
            continue

        # ===== 符号表 =====
        # 只读 Publics by Value（按地址排序，适合长度推断）
        if 'Publics by' in stripped:
            if 'Value' in stripped:
                section = 'symbols'
            # 跳过 Publics by Name 避免重复
            elif 'Name' in stripped:
                section = 'skip_symbols'
            continue

        if section == 'skip_symbols':
            # 跳到下一个节（空行后出现新节头）
            if 'Publics by' in stripped:
                # 进入 Value 区
                if 'Value' in stripped:
                    section = 'symbols'
                continue
            continue

        # 符号行: " 0001:0000FF0C       SysInit.GetProcAddress"
        # Delphi 12 的 .map 中，Publics by Value 也没有长度列，格式同 by Name
        if section == 'symbols' and stripped:
            # 行号表开始，退出符号解析
            if stripped.startswith('Line numbers for'):
                section = 'line_numbers'
                result['line_numbers'].append(stripped)
                continue
            m = re.match(r'^(\w+):([0-9A-Fa-f]+)\s+(\S.+)', stripped)
            if m:
                seg_num = int(m.group(1), 16)
                offset = int(m.group(2), 16)
                sym_name = m.group(3)
                result['symbols'].append({
                    'segment': seg_num,
                    'offset': offset,
                    'length': 0,  # Delphi .map 不输出长度，后续推断
                    'name': sym_name,
                })
                continue

        # ===== 行号表 =====
        if stripped.startswith('Line numbers for'):
            section = 'line_numbers'
            continue

        if section == 'line_numbers' and stripped:
            result['line_numbers'].append(stripped)

    # 推断无长度符号的长度（取同段中下一个符号的偏移差）
    symbols_sorted = sorted(
        [s for s in result['symbols'] if s['length'] == 0],
        key=lambda x: (x['segment'], x['offset'])
    )
    for i, sym in enumerate(symbols_sorted):
        if i + 1 < len(symbols_sorted):
            next_sym = symbols_sorted[i + 1]
            if next_sym['segment'] == sym['segment']:
                sym['length'] = next_sym['offset'] - sym['offset']
            else:
                sym['length'] = 16
        else:
            sym['length'] = 16

    result['segment_count'] = len(result['segments'])
    result['symbol_count'] = len(result['symbols'])
    result['line_number_count'] = len(result['line_numbers'])

    return result


# 字符级拆分模式：把 Delphi 类型名/符号名拆成最细粒度的可复用单元
# TDictionary<String,TList<Integer>>
# → TDictionary , < , String , , , TList , < , Integer , > , >
#
# System.Generics.Collections.TList<System.Classes.TPersistent>
# → System , . , Generics , . , Collections , . , TList , < ,
#   System , . , Classes , . , TPersistent , >
#
# {System.Generics.Collections}TList<...>
# → { , System , . , Generics , . , Collections , } , TList , < , ...
#
# System..TObject
# → System , . , . , TObject
#
# 每个部分独立进字典，尖括号/花括号/逗号/点号全部复用。
_TOKEN_PARTS = [
    r'\w+',           # 单词标识符（字母数字下划线）
    r'<\s*',          # < (可能带空格)
    r'>',             # >
    r',',             # ,
    r'\{',            # {
    r'\}',            # }
    r'\[',            # [
    r'\]',            # ]
    r'@',             # @
    r'\$',            # $
    r'\.',            # .
    r'\(',            # )
    r'\)',            # )
]
_TOKEN_PATTERN = re.compile('|'.join(_TOKEN_PARTS))


def tokenize_name(name: str) -> List[str]:
    """将 Delphi 符号名按语法单元拆分为 token 列表"""
    found = _TOKEN_PATTERN.findall(name)
    return found if found else [name]


def extract_tokens(data: dict) -> List[str]:
    """从结构化数据中提取 token"""
    tokens = []

    # 段名
    for seg in data['segments']:
        tokens.append(seg['name'])

    # 符号名 → 按语法单元拆分
    for sym in data['symbols']:
        tokens.extend(tokenize_name(sym['name']))

    return tokens


def simulate_v4_serialization(data: dict) -> dict:
    """模拟 MAPDATA V4 序列化，计算压缩率"""

    # 1. 提取 tokens 并统计频率
    tokens = extract_tokens(data)
    token_freq = Counter(tokens)

    # 2. 按频率排序（高频在前，获得小 varint ID）
    sorted_tokens = sorted(token_freq.items(), key=lambda x: -x[1])

    # 3. 构建 token → ID 映射
    token_to_id: Dict[str, int] = {}
    for i, (token, _) in enumerate(sorted_tokens):
        token_to_id[token] = i

    # 4. 计算 token 字典大小（UTF-8 编码）
    dict_size = sum(len(t.encode('utf-8')) for t, _ in sorted_tokens)

    # 5. 模拟 varint 编码后的符号表大小
    total_varint_size = 0
    varint_counts = {'1byte': 0, '2byte': 0, '3byte+': 0}

    for sym in data['symbols']:
        # 每个符号：段号(varint) + 偏移(varint) + 长度(varint) + token_id 列表
        seg_varint = count_varint_bytes(sym['segment'])
        off_varint = count_varint_bytes(sym['offset'])
        len_varint = count_varint_bytes(sym['length'])
        total_varint_size += seg_varint + off_varint + len_varint

        varint_counts['1byte'] += (seg_varint == 1) + (off_varint == 1) + (len_varint == 1)
        varint_counts['2byte'] += (seg_varint == 2) + (off_varint == 2) + (len_varint == 2)
        varint_counts['3byte+'] += (seg_varint >= 3) + (off_varint >= 3) + (len_varint >= 3)

        # 符号名 token IDs (varint) — 使用字符级拆分
        for part in tokenize_name(sym['name']):
            tid = token_to_id.get(part, 0)
            total_varint_size += count_varint_bytes(tid)

    # 6. 行号映射大小（粗略：每个符号两行 + 文件路径引用）
    # 假设每 3 个符号有 1 个行号条目
    line_count = len(data.get('line_numbers', []))
    line_size_estimate = line_count * 20  # 每行约 20 字节

    # 7. 段表
    seg_table_size = data['segment_count'] * 16  # 段号+起始+长度+标志

    # 8. 总 MAPDATA V4 大小
    mapdata_size = (dict_size           # token 字典
                    + total_varint_size  # 符号表
                    + seg_table_size     # 段表
                    + line_size_estimate # 行号映射
                    + 256)               # 头部开销

    # 9. 原始 .map 大小
    raw_size = data['raw_size']

    return {
        'raw_size': raw_size,
        'mapdata_size': mapdata_size,
        'compression_ratio': raw_size / max(mapdata_size, 1),
        'dict_size': dict_size,
        'dict_entries': len(sorted_tokens),
        'symbol_table_size': total_varint_size,
        'segment_table_size': seg_table_size,
        'line_info_size': line_size_estimate,
        'symbol_count': data['symbol_count'],
        'segment_count': data['segment_count'],
        'top_10_tokens': [(t, f) for t, f in sorted_tokens[:10]],
        'token_distribution': {
            'total_unique': len(sorted_tokens),
            'single_occurrence': sum(1 for _, f in sorted_tokens if f == 1),
            'top_10_percent_coverage': sum(f for _, f in sorted_tokens[:max(1, len(sorted_tokens)//10)]),
            'total_occurrences': sum(f for _, f in sorted_tokens),
        },
        'varint_distribution': varint_counts,
    }


def count_varint_bytes(value: int) -> int:
    """计算 value 编码为 varint 需要的字节数"""
    if value < 0:
        value = abs(value)
    if value < 128:
        return 1
    if value < 16384:
        return 2
    if value < 2097152:
        return 3
    if value < 268435456:
        return 4
    return 5


def format_size(size: int) -> str:
    if size < 1024:
        return f'{size} B'
    elif size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    else:
        return f'{size / 1024 / 1024:.2f} MB'


def main():
    if len(sys.argv) < 2:
        # 默认使用测试项目中的 .map
        map_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'docs', 'tutorial', 'test-project',
            'Win32', 'Debug', 'TestProject.map'
        )
    else:
        map_path = sys.argv[1]

    if not os.path.exists(map_path):
        print(f'[ERROR] .map file not found: {map_path}')
        sys.exit(1)

    print('=' * 70)
    print('  MAPDATA V4 Compression Simulation')
    print('=' * 70)
    print(f'\n  Source: {map_path}')
    print(f'  Size:   {format_size(os.path.getsize(map_path))}')
    print()

    # 解析
    t0 = time.time()
    data = parse_map_file(map_path)
    parse_time = time.time() - t0

    print(f'  Parse time:    {parse_time*1000:.1f} ms')
    print(f'  Segments:      {data["segment_count"]}')
    print(f'  Symbols:       {data["symbol_count"]}')
    print(f'  Line entries:  {data["line_number_count"]}')
    print()

    # 模拟序列化
    t0 = time.time()
    result = simulate_v4_serialization(data)
    sim_time = time.time() - t0

    print(f'  Simulation time: {sim_time*1000:.1f} ms')
    print()
    print('  ' + '-' * 66)
    print('  MAPDATA V4 Size Breakdown')
    print('  ' + '-' * 66)
    print(f'  {"Component":<30} {"Size":>12} {"% of raw":>10}')
    print(f'  {"-"*52}')
    print(f'  {"Token dictionary":<30} {format_size(result["dict_size"]):>12} {result["dict_size"]/max(result["raw_size"],1)*100:>9.1f}%')
    print(f'  {"Symbol table (varint)":<30} {format_size(result["symbol_table_size"]):>12} {result["symbol_table_size"]/max(result["raw_size"],1)*100:>9.1f}%')
    print(f'  {"Segment table":<30} {format_size(result["segment_table_size"]):>12} {result["segment_table_size"]/max(result["raw_size"],1)*100:>9.1f}%')
    print(f'  {"Line info (est.)":<30} {format_size(result["line_info_size"]):>12} {result["line_info_size"]/max(result["raw_size"],1)*100:>9.1f}%')
    print(f'  {"-"*52}')
    print(f'  {"MAPDATA V4 total":<30} {format_size(result["mapdata_size"]):>12} {result["mapdata_size"]/max(result["raw_size"],1)*100:>9.1f}%')
    print()

    print(f'  Compression ratio: {result["compression_ratio"]:.2f}x')
    print(f'  Raw .map:          {format_size(result["raw_size"])}')
    print(f'  MAPDATA V4:        {format_size(result["mapdata_size"])}')
    print()

    print('  Token Dictionary Stats')
    print('  ' + '-' * 50)
    print(f'  Total unique tokens:   {result["dict_entries"]}')
    print(f'  Single-occurrence:     {result["token_distribution"]["single_occurrence"]} '
          f'({result["token_distribution"]["single_occurrence"]/max(result["dict_entries"],1)*100:.0f}%)')
    print(f'  Total occurrences:     {result["token_distribution"]["total_occurrences"]}')
    print(f'  Top-10% covers:        {result["token_distribution"]["top_10_percent_coverage"]} '
          f'({result["token_distribution"]["top_10_percent_coverage"]/max(result["token_distribution"]["total_occurrences"],1)*100:.0f}%)')
    print(f'  Dictionary size:       {format_size(result["dict_size"])}')
    print()

    print('  Top 10 Most Frequent Tokens')
    print('  ' + '-' * 50)
    print(f'  {"Rank":<6} {"Token":<25} {"Frequency":>10} {"Varint ID":>10}')
    print(f'  {"-"*51}')
    for i, (tok, freq) in enumerate(result['top_10_tokens']):
        varint_bytes = count_varint_bytes(i)
        print(f'  {i:<6} {tok:<25} {freq:>10} {varint_bytes:>5} byte(s)')
    print()

    print('  Varint Distribution (symbol table fields)')
    print(f'  1-byte:  {result["varint_distribution"]["1byte"]:>6}  '
          f'({result["varint_distribution"]["1byte"]/(result["symbol_count"]*3 + 1)*100:.1f}%)')
    print(f'  2-byte:  {result["varint_distribution"]["2byte"]:>6}  '
          f'({result["varint_distribution"]["2byte"]/(result["symbol_count"]*3 + 1)*100:.1f}%)')
    print(f'  3+byte:  {result["varint_distribution"]["3byte+"]:>6}  '
          f'({result["varint_distribution"]["3byte+"]/(result["symbol_count"]*3 + 1)*100:.1f}%)')
    print()
    print('  Target: <5MB for source projects under 20MB .map')
    print('=' * 70)


if __name__ == '__main__':
    main()
