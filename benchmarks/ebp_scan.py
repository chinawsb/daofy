"""
EBP-Offset ModRM 扫描基准测试

模拟 EBP 偏移量发现的二进制扫描过程：
1. 解析 .map 获取函数范围（段号 + 起始地址 + 长度）
2. 打开对应 .exe 二进制文件
3. 按函数地址范围扫描 ModRM 字节 $45（[EBP+disp8] 模式）
4. 统计扫描性能和模式发现

用法:
    python benchmarks/ebp_scan.py <path/to/project.map> [path/to/project.exe]
"""

import sys
import os
import re
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class FunctionInfo:
    def __init__(self):
        self.name = ''
        self.segment = 0
        self.offset = 0  # 函数在段内的偏移
        self.length = 0  # 函数大小（字节）
        self.module = ''  # 所属单元


def parse_map_functions(map_path: str):
    """
    解析 Delphi .map 文件，提取函数符号的范围
    
    Delphi .map 格式 (DCC_MapFile=3):
      段表(顶部):  0001:00401000 001FB634H .text CODE
      符号(by Value): 0001:0000FF0C       SysInit.GetProcAddress
      (Delphi 12 不输出符号长度，需推断)
    """
    with open(map_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    seg_starts = {}   # segment_number → start_address
    seg_lengths = {}  # segment_number → length
    symbols_raw = []  # [(seg, offset, name), ...]
    functions = []
    section = None

    for line in lines:
        stripped = line.strip()

        # ===== 段表（顶部区域）=====
        if 'Start' in stripped and 'Length' in stripped and 'Name' in stripped:
            section = 'segments'
            continue
        if section == 'segments':
            m = re.match(r'^(\w+):([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)H?\s+(\S+)', stripped)
            if m:
                seg_num = int(m.group(1), 16)
                seg_start = int(m.group(2), 16)
                seg_len_val = int(m.group(3), 16)
                seg_starts[seg_num] = seg_start
                seg_lengths[seg_num] = seg_len_val
                continue

        # ===== 跳过 Detailed map of segments（避免覆盖 seg_starts）=====
        if stripped.startswith('Detailed map of segments'):
            section = 'detailed_skip'
            continue
        if section == 'detailed_skip':
            # 继续跳过，直到下个节
            if 'Publics by' in stripped or stripped.startswith('Line numbers for'):
                section = None
            continue

        # ===== 符号表 =====
        if 'Publics by' in stripped:
            if 'Value' in stripped:
                section = 'symbols'
            elif 'Name' in stripped:
                section = 'skip_symbols'
            continue

        if section == 'skip_symbols':
            continue

        # 符号行: " 0001:0000FF0C       SysInit.GetProcAddress"
        if section == 'symbols' and stripped:
            # 行号表开始，结束符号解析
            if stripped.startswith('Line numbers for'):
                section = 'line_numbers'
                continue
            
            m = re.match(r'^(\w+):([0-9A-Fa-f]+)\s+(\S.+)', stripped)
            if m:
                seg_num = int(m.group(1), 16)
                offset = int(m.group(2), 16)
                sym_name = m.group(3)
                symbols_raw.append((seg_num, offset, sym_name))
                continue

    # 按 (段, 偏移) 排序
    symbols_raw.sort(key=lambda x: (x[0], x[1]))

    # 推断长度：用下一个同段符号的偏移差
    for i, (seg, off, name) in enumerate(symbols_raw):
        if i + 1 < len(symbols_raw):
            next_seg, next_off, _ = symbols_raw[i + 1]
            if next_seg == seg:
                length = next_off - off
            else:
                length = seg_lengths.get(seg, 0) - off
        else:
            length = seg_lengths.get(seg, 0) - off

        if length < 4:
            continue  # 跳过过小的符号（数据符号）

        fi = FunctionInfo()
        fi.name = name
        fi.segment = seg
        fi.offset = off
        fi.length = length
        functions.append(fi)

    return functions, seg_starts


def find_exe_path(map_path: str) -> str:
    """从 .map 路径推断 .exe 路径"""
    base = os.path.splitext(map_path)[0]
    exe = base + '.exe'
    if os.path.exists(exe):
        return exe

    # 在 Debug/Release 目录中查找
    dir_map = os.path.dirname(map_path)
    parent = os.path.dirname(dir_map)
    for sub in ['Debug', 'Release']:
        exe_path = os.path.join(parent, sub, os.path.basename(base) + '.exe')
        if os.path.exists(exe_path):
            return exe_path

    # 向上搜索
    for root, dirs, files in os.walk(os.path.dirname(map_path)):
        for f in files:
            if f.lower().endswith('.exe'):
                return os.path.join(root, f)
    return ''


def scan_for_ebp_refs(exe_path: str, functions: list, seg_starts: dict) -> dict:
    """
    扫描 EXE 中的 EBP-Offset 引用

    ModRM 模式: [EBP+disp8] → ModRM byte = 01XXX101 (binary)
    ModRM byte bits: mod(2) reg(3) r/m(3)
    - mod=01 (8-bit displacement)
    - reg=don't care
    - r/m=101 (EBP)
    Result: 010_XXXX_101 = 0x45 for [EBP+disp8] with reg=000
    Also match: 0x4D (reg=001), 0x55 (reg=010), 0x6D (reg=011)
    0x75 (reg=100), 0x7D (reg=101), 0x45 (reg=110), 0x4D (reg=111)

    So match range of 0x45 to 0x7D with step 8 + particular bit pattern.
    Actually: the ModRM byte for [EBP+disp8] is:
    mod=01 (01), reg=XXX (any), r/m=101 (101) 
    => 01_XXX_101 binary
    => For reg=000: 01_000_101 = 0x45
    => For reg=001: 01_001_101 = 0x4D
    => For reg=010: 01_010_101 = 0x55
    => For reg=011: 01_011_101 = 0x5D
    => For reg=100: 01_100_101 = 0x65
    => For reg=101: 01_101_101 = 0x6D (this uses EBP-relative addressing mode with EBP as register)
    => For reg=110: 01_110_101 = 0x75
    => For reg=111: 01_111_101 = 0x7D

    So hex pattern: 0x45 + N*8 where N = 0 to 7, but with exact values being 0x45, 0x4D, 0x55, 0x5D, 0x65, 0x6D, 0x75, 0x7D
    """
    with open(exe_path, 'rb') as f:
        exe_data = f.read()

    exe_size = len(exe_data)
    func_results = []
    total_ebp_refs = 0
    total_candidates = 0

    # PE 头解析
    section_offset = 0
    image_base = 0
    pe_offset = 0
    section_offsets = {}
    num_sections = 0
    if exe_data[:2] == b'MZ':
        pe_offset = int.from_bytes(exe_data[0x3C:0x40], 'little')
        if exe_data[pe_offset:pe_offset+4] == b'PE\x00\x00':
            # Section headers follow COFF header
            coff_header_size = 20
            optional_header_size = int.from_bytes(
                exe_data[pe_offset+4+16:pe_offset+4+18], 'little')
            section_offset = pe_offset + 4 + coff_header_size + optional_header_size
            # Optional header magic → PE32 or PE32+
            opt_hdr = pe_offset + 4 + coff_header_size
            magic = int.from_bytes(exe_data[opt_hdr:opt_hdr+2], 'little')
            if magic == 0x10b:  # PE32
                image_base = int.from_bytes(exe_data[opt_hdr+0x1C:opt_hdr+0x20], 'little')
            elif magic == 0x20b:  # PE32+
                image_base = int.from_bytes(exe_data[opt_hdr+0x18:opt_hdr+0x20], 'little')

    # 解析 PE 节表 → 构建 RVA → 文件偏移映射
    if pe_offset > 0 and section_offset > 0:
        num_sections = int.from_bytes(
            exe_data[pe_offset+4+2:pe_offset+4+4], 'little')
        for i in range(num_sections):
            sec_entry = section_offset + i * 40
            sec_name = exe_data[sec_entry:sec_entry+8].rstrip(b'\x00').decode('ascii', errors='replace')
            virtual_size = int.from_bytes(exe_data[sec_entry+8:sec_entry+12], 'little')
            virtual_addr = int.from_bytes(exe_data[sec_entry+12:sec_entry+16], 'little')
            raw_size = int.from_bytes(exe_data[sec_entry+16:sec_entry+20], 'little')
            raw_offset = int.from_bytes(exe_data[sec_entry+20:sec_entry+24], 'little')
            section_offsets[sec_name] = (virtual_addr, raw_offset, raw_size, virtual_size)

    # 扫描每个函数
    scan_start = time.time()
    skipped_no_section = 0
    skipped_out_of_range = 0
    for idx, func in enumerate(functions):
        if func.name.startswith('@') or func.name.startswith('$'):
            continue  # 跳过编译器生成的符号

        # 跳过过大的函数（可能不是函数）
        if func.length > 1024 * 1024:
            continue

        # 地址翻译：.map 段:偏移 → PE 文件偏移
        # .map 给出: segment_number:offset_from_segment_base
        # seg_starts[seg] = segment_base (VA, 含 image base, 如 0x00401000)
        # 需找到 PE 中包含该 VA 的节
        if func.segment not in seg_starts:
            continue

        seg_base = seg_starts[func.segment]  # e.g. 0x00401000
        func_va = seg_base + func.offset     # 函数虚拟地址，如 0x0040173C

        # 找到包含 func_va 的 PE 节
        file_addr = -1
        for sec_name, (sec_rva, sec_raw, sec_raw_size, sec_vsize) in section_offsets.items():
            sec_va = image_base + sec_rva
            sec_end_va = sec_va + max(sec_raw_size, sec_vsize)
            if sec_va <= func_va < sec_end_va:
                # RVA within this section → translate to file offset
                rva = func_va - image_base
                file_addr = sec_raw + (rva - sec_rva)
                file_end = file_addr + func.length
                break

        if file_addr < 0:
            skipped_no_section += 1
            continue

        if file_addr < 0 or file_end > exe_size or file_end <= file_addr:
            skipped_out_of_range += 1
            continue

        # 扫描该函数范围内的 EBP-offset 引用
        func_ebp_refs = 0
        scan_pos = file_addr

        while scan_pos < file_end - 1:
            b = exe_data[scan_pos]
            # [EBP+disp8] ModRM pattern: 01XXX101
            if b in (0x45, 0x4D, 0x55, 0x5D, 0x65, 0x6D, 0x75, 0x7D):
                # 读取后面的 disp8 位移量（有符号）
                disp = int.from_bytes(
                    exe_data[scan_pos+1:scan_pos+2], 'little', signed=True)
                func_ebp_refs += 1
                total_ebp_refs += 1
                scan_pos += 2  # ModRM + disp8
            # [EBP+disp32] ModRM: 10XXX101 = 0x85-0xBD
            elif b in (0x85, 0x8D, 0x95, 0x9D, 0xA5, 0xAD, 0xB5, 0xBD):
                disp = int.from_bytes(
                    exe_data[scan_pos+1:scan_pos+5], 'little', signed=True)
                func_ebp_refs += 1
                total_ebp_refs += 1
                scan_pos += 5
            else:
                scan_pos += 1

        if func_ebp_refs > 0:
            func_results.append({
                'name': func.name,
                'module': '',
                'length': func.length,
                'ebp_refs': func_ebp_refs,
                'refs_per_kb': func_ebp_refs / (func.length / 1024)
            })
            total_candidates += 1

    scan_time = time.time() - scan_start

    # 按 EBP 引用密度排序
    func_results.sort(key=lambda x: -x['ebp_refs'])

    return {
        'exe_path': exe_path,
        'exe_size': exe_size,
        'functions': func_results[:30],  # 返回 top 30
        'total_functions_scanned': len(functions),
        'functions_with_ebp': len(func_results),
        'total_ebp_refs': total_ebp_refs,
        'scan_time': scan_time,
        'avg_refs_per_function': total_ebp_refs / max(len(func_results), 1),
        'total_functions_with_ebp_pct': len(func_results) / max(len(functions), 1) * 100,
        'skipped_no_section': skipped_no_section,
        'skipped_out_of_range': skipped_out_of_range,
        'image_base': image_base,
    }


def format_size(size: int) -> str:
    if size < 1024:
        return f'{size} B'
    elif size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    else:
        return f'{size / 1024 / 1024:.2f} MB'


def main():
    if len(sys.argv) < 2:
        map_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'docs', 'tutorial', 'test-project',
            'Win32', 'Debug', 'TestProject.map'
        )
    else:
        map_path = sys.argv[1]

    if len(sys.argv) >= 3:
        exe_path = sys.argv[2]
    else:
        exe_path = find_exe_path(map_path)
        if not exe_path:
            exe_path = os.path.join(
                os.path.dirname(map_path),
                os.path.splitext(os.path.basename(map_path))[0] + '.exe'
            )

    if not os.path.exists(map_path):
        print(f'[ERROR] .map file not found: {map_path}')
        sys.exit(1)

    print('=' * 70)
    print('  EBP-Offset ModRM Scan Benchmark')
    print('=' * 70)
    print(f'\n  .map: {map_path}')
    print(f'  .exe: {exe_path}')
    if os.path.exists(exe_path):
        print(f'  .exe size: {format_size(os.path.getsize(exe_path))}')
    else:
        print(f'  [WARN] .exe not found at: {exe_path}')
    print()

    # 解析 .map
    t0 = time.time()
    functions, seg_starts = parse_map_functions(map_path)
    parse_time = time.time() - t0
    print(f'  Parse .map time:      {parse_time * 1000:.1f} ms')
    print(f'  Functions found:      {len(functions)}')
    print(f'  Segments mapped:      {len(seg_starts)}')
    print()

    # 检查 EXE 是否存在
    if not os.path.exists(exe_path):
        print('[SKIP] No .exe found. Run compile_project first.')
        return

    # 扫描 EBP 引用
    print('  Scanning binary for EBP-offset references...')
    scan_results = scan_for_ebp_refs(exe_path, functions, seg_starts)

    print(f'  Scan time:            {scan_results["scan_time"]:.3f}s')
    print(f'  Functions scanned:    {scan_results["total_functions_scanned"]}')
    print(f'  Funcs with EBP refs:  {scan_results["functions_with_ebp"]} '
          f'({scan_results["total_functions_with_ebp_pct"]:.1f}%)')
    print(f'  Total EBP references: {scan_results["total_ebp_refs"]}')
    print(f'  Avg refs/func:        {scan_results["avg_refs_per_function"]:.1f}')
    print(f'  Skipped (no section): {scan_results["skipped_no_section"]}')
    print(f'  Skipped (out range):  {scan_results["skipped_out_of_range"]}')
    print(f'  Image base:           0x{scan_results["image_base"]:08X}')
    print()

    if scan_results['functions']:
        print('  Top 30 Functions by EBP References')
        print('  ' + '-' * 70)
        print(f'  {"#":<4} {"Function":<35} {"Module":<15} {"Bytes":>8} {"EBP refs":>8}')
        print(f'  {"-"*70}')
        for i, f in enumerate(scan_results['functions'][:30]):
            print(f'  {i+1:<4} {f["name"]:<35} {f["module"]:<15} {f["length"]:>8} {f["ebp_refs"]:>8}')
        print()

    # 性能评估
    print('  Performance Estimate for MAPDATA V4')
    print('  ' + '-' * 50)
    scan_time = scan_results['scan_time']
    func_count = scan_results['total_functions_scanned']
    ebp_total = scan_results['total_ebp_refs']

    # 估算在大型项目上的表现
    for scale, name in [(1, 'This project'), (3, '3x (medium ERP)'), (10, '10x (large ERP)'), (30, '30x (mega project)')]:
        est_time = scan_time * scale
        est_funcs = func_count * scale
        print(f'  {name:<25} {est_funcs:>8} funcs  {est_time:>6.2f}s')

    total_refs = sum(f['ebp_refs'] for f in scan_results['functions'])
    print()
    print('  Target: <3s for 50MB .map, <5s for any project.')
    print('=' * 70)


if __name__ == '__main__':
    main()
