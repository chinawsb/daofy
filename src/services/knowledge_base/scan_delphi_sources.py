#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 源码知识库扫描器
扫描 Delphi 官方源码目录,建立索引供 CodeArts 使用
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional, Callable
from multiprocessing import cpu_count
import re
import time

try:
    from ...utils.progress_tracker import ProgressTracker, ProgressInfo
except ImportError:
    # 如果相对导入失败，使用绝对导入
    from src.utils.progress_tracker import ProgressTracker, ProgressInfo


def _analyze_file_worker(args: tuple) -> Optional[Dict]:
    """
    分析单个文件的工作函数（用于多进程）
    
    Args:
        args: (file_path_str, source_dir_str)
        
    Returns:
        文件信息字典或None
    """
    import time as _time
    _ts = _time.time()
    file_path_str, source_dir_str = args
    file_path = Path(file_path_str)
    source_dir = Path(source_dir_str)
    
    try:
        # 获取文件元数据（一次stat调用）
        stat_info = file_path.stat()
        
        # 一次读取文件，同时计算哈希和获取内容
        with open(file_path, 'rb') as f:
            data = f.read()
        
        content = data.decode('utf-8', errors='ignore')
        lines = content.split('\n')
        line_count = len(lines)
        
        # 相对路径
        rel_path = file_path.relative_to(source_dir)
        
        # 提取实体（统一 entities 格式）
        entities = _extract_all_entities(content, file_path.suffix.lower())
        
        # 提取文件信息
        # hash 使用 mtime+size，避免计算 MD5（除非 config.json 配置 hash_mode=md5）
        file_hash = f"{stat_info.st_mtime}:{stat_info.st_size}"
        file_info = {
            'path': str(rel_path).replace('\\', '/'),
            'full_path': str(file_path),
            'extension': file_path.suffix.lower(),
            'size': stat_info.st_size,
            'line_count': line_count,
            'hash': file_hash,
            'last_modified': datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            'units': _extract_units(content),
            'uses': _extract_uses(content),
            'entities': entities,  # 统一实体表
            '_worker_ts': _ts,    # worker 开始处理的时间戳(用于诊断)
        }
        
        return file_info
        
    except Exception as e:
        print(f"分析文件失败 {file_path}: {e}")
        return None


# Kind 常量（两字母代码）
KIND_CLASS = 'TC'      # class
KIND_RECORD = 'TR'     # record
KIND_INTERFACE = 'TI'  # interface
KIND_ENUM = 'TE'       # enum
KIND_SET = 'TS'        # set of
KIND_TYPE_ALIAS = 'TY' # type alias
KIND_FIELD = 'MF'      # field
KIND_PROPERTY = 'MP'   # property
KIND_METHOD = 'MM'     # method
KIND_EVENT = 'ME'      # event
KIND_FUNC = 'FF'       # function
KIND_PROC = 'FP'       # procedure
KIND_CONST = 'CC'      # const
KIND_RESOURCE = 'CR'   # resourcestring
KIND_UNIT = 'UI'       # unit in uses
KIND_HELPER = 'TH'     # class helper for / record helper for
KIND_STRING_LITERAL = 'KS'  # string literal (error messages, UI strings, etc.)


def _add_func_entity(entities: List[Dict], content: str, match: re.Match, name: str, ret_type: Optional[str]) -> None:
    """
    通用函数实体添加逻辑
    根据匹配文本中的关键字确定 kind 和 definition
    
    Args:
        entities: 实体列表（追加写入）
        content: 源文件内容
        match: 正则匹配结果
        name: 函数/过程名
        ret_type: 返回类型（可能为 None）
    """
    line = content[:match.start()].count('\n') + 1
    mt = match.group(0).strip().lower()
    
    # 根据关键字确定 kind 代码
    if 'destructor' in mt:
        kind = KIND_PROC
        defn = 'destructor'
    elif 'constructor' in mt:
        kind = KIND_FUNC
        defn = 'constructor'
    elif 'operator' in mt:
        kind = KIND_FUNC
        defn = f'operator: {ret_type}' if ret_type else 'operator'
    elif 'function' in mt:
        kind = KIND_FUNC
        defn = f'function: {ret_type}' if ret_type else 'function'
    else:  # procedure
        kind = KIND_PROC
        defn = 'procedure'
    
    start_offset = match.start()
    entities.append({
        'name': name,
        'kind': kind,
        'parent': None,
        'line': line,
        'start_line': line,
        'start_offset': start_offset,
        'definition': defn
    })


def _extract_all_entities(content: str, file_ext: str = '') -> List[Dict]:
    """
    提取所有实体（统一格式）
    返回带有 kind 两字母代码的实体列表
    只记录 start_line，end_line 通过查询时用"下一个类型开始行"确定
    """
    entities = []
    
    # 提取 class 类型 (TC)
    for match in _CLASS_PATTERN.finditer(content):
        name = match.group(1)
        base = match.group(2)  # None if no parent specified, Delphi defaults to TObject
        start_line = content[:match.start()].count('\n') + 1
        start_offset = match.start()  # 文件偏移
        entities.append({
            'name': name,
            'kind': KIND_CLASS,
            'parent': base,
            'line': start_line,
            'start_line': start_line,
            'start_offset': start_offset,
            'definition': f'class({base})' if base else 'class'
        })
    
    # 提取 record 类型 (TR)
    for match in _RECORD_PATTERN.finditer(content):
        name = match.group(1)
        base = match.group(2)
        start_line = content[:match.start()].count('\n') + 1
        start_offset = match.start()
        entities.append({
            'name': name,
            'kind': KIND_RECORD,
            'parent': base,
            'line': start_line,
            'start_line': start_line,
            'start_offset': start_offset,
            'definition': f'record({base})' if base else 'record'
        })
    
    # 提取 interface 类型 (TI)
    # _INTERFACE_PATTERN 组: 1=name, 2=keyword, 3=parent(可选)
    for match in _INTERFACE_PATTERN.finditer(content):
        name = match.group(1)
        base = match.group(3) if match.lastindex and match.lastindex >= 3 else None
        kw = match.group(2).lower()
        start_line = content[:match.start()].count('\n') + 1
        start_offset = match.start()
        entities.append({
            'name': name,
            'kind': KIND_INTERFACE,
            'parent': base,
            'line': start_line,
            'start_line': start_line,
            'start_offset': start_offset,
            'definition': f'interface({base})' if base else kw
        })
    
    # 提取 class helper 类型 (TH)
    # _HELPER_PATTERN 组: 1=name, 2=ancestor(可选), 3=target
    for match in _HELPER_PATTERN.finditer(content):
        name = match.group(1)
        target = match.group(3) if match.lastindex and match.lastindex >= 3 else match.group(2)
        start_line = content[:match.start()].count('\n') + 1
        start_offset = match.start()
        entities.append({
            'name': name,
            'kind': KIND_HELPER,
            'parent': target,
            'line': start_line,
            'start_line': start_line,
            'start_offset': start_offset,
            'definition': f'class helper for {target}'
        })
    
    # 提取 record helper 类型 (TH)
    # _RECORD_HELPER_PATTERN 组: 1=name, 2=ancestor(可选), 3=target
    for match in _RECORD_HELPER_PATTERN.finditer(content):
        name = match.group(1)
        target = match.group(3) if match.lastindex and match.lastindex >= 3 else match.group(2)
        start_line = content[:match.start()].count('\n') + 1
        start_offset = match.start()
        entities.append({
            'name': name,
            'kind': KIND_HELPER,
            'parent': target,
            'line': start_line,
            'start_line': start_line,
            'start_offset': start_offset,
            'definition': f'record helper for {target}'
        })
    
    # 提取 enum 类型 (TE)
    for match in _ENUM_PATTERN.finditer(content):
        name = match.group(1)
        values = match.group(2).strip()
        if ',' in values:  # 真正的枚举
            line = content[:match.start()].count('\n') + 1
            entities.append({
                'name': name,
                'kind': KIND_ENUM,
                'parent': None,
                'line': line,
                'definition': 'enum'
            })
    
    # 提取 set 类型 (TS)
    for match in _SET_PATTERN.finditer(content):
        name = match.group(1)
        line = content[:match.start()].count('\n') + 1
        entities.append({
            'name': name,
            'kind': KIND_SET,
            'parent': None,
            'line': line,
            'definition': 'set'
        })
    
    # 提取函数/过程/构造/析构/运算符 (FF/FP)
    # 统一处理 _FUNC_PATTERN_1 (带参数统一模式)
    for match in _FUNC_PATTERN_1.finditer(content):
        _add_func_entity(entities, content, match, match.group(1), match.group(3) if match.lastindex and match.lastindex >= 3 else None)
    
    # 统一处理 _FUNC_PATTERN_3 (函数无参带返回值)
    for match in _FUNC_PATTERN_3.finditer(content):
        _add_func_entity(entities, content, match, match.group(1), match.group(2))
    
    # 统一处理 _FUNC_PATTERN_4 (过程/构造/析构无参)
    for match in _FUNC_PATTERN_4.finditer(content):
        _add_func_entity(entities, content, match, match.group(1), None)
    
    # 提取 const (CC)
    for match in _CONST_PATTERN.finditer(content):
        const_type = match.group(1)
        name = match.group(2)
        value = match.group(3).strip()
        line = content[:match.start()].count('\n') + 1
        
        kind = KIND_CONST
        if const_type.lower() == 'resourcestring':
            kind = KIND_RESOURCE
        
        entities.append({
            'name': name,
            'kind': kind,
            'parent': None,
            'line': line,
            'definition': value[:100]
        })
    
    # 提取类型标注常量: MyVar: TypeName = Value;
    # _CONST_PATTERN_TYPED 组: 1=name, 2=type, 3=value
    for match in _CONST_PATTERN_TYPED.finditer(content):
        name = match.group(1)
        const_type = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else ''
        value = match.group(3).strip() if match.lastindex and match.lastindex >= 3 else ''
        line = content[:match.start()].count('\n') + 1
        
        entities.append({
            'name': name,
            'kind': KIND_CONST,
            'parent': None,
            'line': line,
            'definition': value[:100]
        })
    
    # 提取简单常量: SIntOverflow = '...'; toInteger = Char(3);
    for match in _CONST_PATTERN_SIMPLE.finditer(content):
        name = match.group(1)
        value = match.group(2).strip()
        line = content[:match.start()].count('\n') + 1
        
        entities.append({
            'name': name,
            'kind': KIND_CONST,
            'parent': None,
            'line': line,
            'definition': value[:100]
        })
    
    # 提取类型定义 (作为独立 type)
    for match in _TYPE_PATTERN_1.finditer(content):
        name = match.group(1)
        type_def = match.group(2) if match.lastindex is not None and match.lastindex >= 2 else ''
        line = content[:match.start()].count('\n') + 1
        
        # 跳过已提取的 class/record/interface
        if name.startswith('T') or name.startswith('I'):
            continue
        
        entities.append({
            'name': name,
            'kind': 'TY',  # type alias
            'parent': None,
            'line': line,
            'definition': type_def[:50]
        })
    
    # 提取指针类型: PPointerList = ^TPointerList;
    # _TYPE_PATTERN_PTR 组: 1=name, 2=指向类型(可选)
    for match in _TYPE_PATTERN_PTR.finditer(content):
        name = match.group(1)
        pointed = match.group(2).strip() if match.lastindex and match.lastindex >= 2 and match.group(2) else ''
        line = content[:match.start()].count('\n') + 1
        entities.append({
            'name': name,
            'kind': 'TY',
            'parent': None,
            'line': line,
            'definition': f'pointer to {pointed}' if pointed else 'pointer'
        })
    
    # 提取 TProc 等类型别名: TProc = procedure; (不带 type 关键字)
    for match in _TYPE_PATTERN_3.finditer(content):
        name = match.group(1)
        ref_to = match.group(2) or ''  # "reference to " or None
        func_type = match.group(3)  # procedure or function
        params = match.group(4) or ''  # parameters or None
        ret_type = match.group(5) or ''  # return type
        of_obj = match.group(6) or ''  # "of object" or None
        
        # 构建定义字符串
        type_def = f"{ref_to}{func_type}{params}{ret_type} {of_obj}".strip()
        line = content[:match.start()].count('\n') + 1
        entities.append({
            'name': name,
            'kind': 'TY',
            'parent': None,
            'line': line,
            'definition': type_def
        })
    
    # ========== .dfm 表单属性提取 ==========
    # Delphi .dfm 中文编码: #ddd(十进制Unicode) / #$xxxx(十六进制) / 'text' 混合
    # 只在文件开头有 object 或 inherited 关键字时才尝试
    first_line = content.lstrip()
    if first_line.startswith('object ') or first_line.startswith('inherited '):
        for match in _DFM_PROP_PATTERN.finditer(content):
            prop_name = match.group(1)
            if prop_name not in _DFM_INTERESTING_PROPS:
                continue
            raw_value = match.group(2).strip()
            if not raw_value:
                continue
            decoded = _decode_dfm_value(raw_value)
            if not decoded.strip():
                continue
            line_num = content[:match.start()].count('\n') + 1
            entities.append({
                'name': f"DFM.{prop_name}",
                'kind': 'DF',
                'parent': None,
                'line': line_num,
                'definition': decoded[:500]
            })

    # ========== 字符串字面量提取 ==========
    entities.extend(_extract_string_literals(content, file_ext))

    return entities


def _decode_dfm_value(raw: str) -> str:
    """
    解码 .dfm 字符串值，处理 #ddd/#$hex/'text' 混合格式。
    Delphi .dfm 用 #23548#20837 表示 Unicode 字符（十进制码位）。
    """
    parts = []
    i = 0
    while i < len(raw):
        if raw[i] == "'":
            j = i + 1
            while j < len(raw):
                if raw[j] == "'":
                    if j + 1 < len(raw) and raw[j + 1] == "'":
                        parts.append("'")
                        j += 2
                    else:
                        j += 1
                        break
                else:
                    parts.append(raw[j])
                    j += 1
            i = j
        elif raw[i] == '#':
            j = i + 1
            if j < len(raw) and raw[j] == '$':
                k = j + 1
                while k < len(raw) and raw[k] in '0123456789ABCDEFabcdef':
                    k += 1
                if k > j + 1:
                    parts.append(chr(int(raw[j+1:k], 16)))
                i = k
            else:
                while j < len(raw) and raw[j].isdigit():
                    j += 1
                if j > i + 1:
                    parts.append(chr(int(raw[i+1:j])))
                i = j
        else:
            if not raw[i].isspace():
                parts.append(raw[i])
            i += 1
    return ''.join(parts)


_DFM_PROP_PATTERN = re.compile(
    r"^\s+([A-Z][a-zA-Z0-9]*)\s*=\s*(.+?)$",
    re.MULTILINE
)
_DFM_INTERESTING_PROPS = {'Caption', 'Hint', 'Text', 'Title',
                          'Prompt', 'HelpKeyword', 'HelpContext'}


# -------- 字符串字面量提取 --------
# Pascal 字符串: 'text' 或 'it''s' ('' 转义单引号)
_STRING_PATTERN = re.compile(
    r"'(?:[^']|'')*'"  # 匹配 '内容' 其中 '' 表示转义的单引号
)

# 最小字符串长度（过滤掉 '' 和单字符）
_MIN_STRING_LEN = 3

# 要跳过的字符串模式（纯格式说明符、纯数字、纯空白等）
_SKIP_STRING_RE = re.compile(
    r'^(%[\w.%\-]*|\d+|[\s,;:|/\\()\[\]{}<>+=*\-\^@#$&!~`"]+)$'
)


def _strip_pascal_comments(content: str) -> str:
    """
    去除 Pascal 注释，用空格替换以保留行号。
    处理: // 行注释, { 块注释 }, (* 块注释 *), {$ 编译器指令 }
    """
    result = list(content)
    i = 0
    while i < len(content):
        ch = content[i]
        # 行注释 //
        if ch == '/' and i + 1 < len(content) and content[i + 1] == '/':
            end = content.find('\n', i)
            if end == -1:
                end = len(content)
            for j in range(i, end):
                result[j] = ' '
            i = end
        # 块注释 { } 或 {$ }
        elif ch == '{':
            end = content.find('}', i)
            if end == -1:
                end = len(content) - 1
            for j in range(i, end + 1):
                result[j] = ' '
            i = end + 1
        # 块注释 (* *)
        elif ch == '(' and i + 1 < len(content) and content[i + 1] == '*':
            end = content.find('*)', i)
            if end == -1:
                end = len(content) - 2
            for j in range(i, end + 2):
                result[j] = ' '
            i = end + 2
        else:
            i += 1
    return ''.join(result)


def _decode_pascal_string(match: re.Match) -> str:
    """
    解码 Pascal 字符串 '内容' → 实际字符串。
    处理 '' → ' 转义。
    """
    s = match.group(0)
    # 去掉首尾单引号
    inner = s[1:-1]
    # '' → '
    return inner.replace("''", "'")


def _extract_string_literals(content: str, file_ext: str) -> List[Dict]:
    """
    从 Pascal 源码中提取有意义的字符串字面量。

    Args:
        content: 文件内容
        file_ext: 文件扩展名 (.pas/.dpr/.dpk/.dfm/.fmx/.inc)

    Returns:
        KS 实体列表
    """
    # DFM 文件的字符串已在 DFM 属性提取中处理
    if file_ext == '.dfm':
        return []

    entities = []
    # 去除注释后提取
    cleaned = _strip_pascal_comments(content)

    found_positions = set()  # 去重
    for match in _STRING_PATTERN.finditer(cleaned):
        decoded = _decode_pascal_string(match)
        stripped = decoded.strip()

        # 过滤过短、无意义字符串
        if len(stripped) < _MIN_STRING_LEN:
            continue
        if _SKIP_STRING_RE.match(stripped):
            continue
        # 跳过纯 ASCII 符号/标点
        if all(c in '.,;:!?-+=*/\\()[]{}<>|&^%$#@~`" \t\r\n' for c in stripped):
            continue

        # 去重：相同字符串相邻位置视为同一实体
        key = f"{stripped}|{match.start()}"
        if key in found_positions:
            continue
        found_positions.add(key)

        line_num = content[:match.start()].count('\n') + 1
        # 字符串本体作为 name（截断到 200 字符用于显示）
        name = stripped[:200]
        # 完整内容放进 definition（无长度限制入库）
        definition = stripped
        entities.append({
            'name': name,
            'kind': KIND_STRING_LITERAL,
            'parent': None,
            'line': line_num,
            'definition': definition,
        })

    return entities


def _find_type_end_line(content: str, start_pos: int) -> int:
    """
    查找类型定义的结束行
    处理嵌套情况：计算 'begin' 和 'end' 的配对
    """
    pos = start_pos
    brace_count = 0
    in_interface = False
    
    search_content = content[pos:]
    
    # 检查是否在 interface 声明后面 (interface 只有 3 行: IXXX = interface; end;)
    if re.match(r'^\s*interface\b', search_content, re.MULTILINE | re.IGNORECASE):
        end_match = re.search(r'^\s*end\s*[;.]', search_content, re.MULTILINE)
        if end_match:
            return content[:pos + end_match.end()].count('\n') + 1
        return content[:pos].count('\n') + 1
    
    # 检查是否有 begin - end 块
    begin_match = re.search(r'^\s*begin', search_content, re.MULTILINE | re.IGNORECASE)
    if begin_match:
        brace_count = 1
        search_content = search_content[begin_match.end():]
        pos = pos + begin_match.end()
        
        # 查找配对的 end
        while search_content and brace_count > 0:
            # 找 begin
            b_match = re.search(r'\bbegin\b', search_content, re.IGNORECASE)
            # 找 end
            e_match = re.search(r'\bend\b', search_content, re.IGNORECASE)
            
            if not e_match:
                break
                
            if b_match and b_match.start() < e_match.start():
                brace_count += 1
                search_content = search_content[b_match.end():]
            else:
                brace_count -= 1
                if brace_count == 0:
                    # 找到匹配的 end，查找其后的 ; 或 .
                    end_content = search_content[e_match.end():e_match.end()+10]
                    semi_match = re.search(r'[;.]', end_content)
                    if semi_match:
                        return content[:pos + e_match.end() + semi_match.end()].count('\n') + 1
                    return content[:pos + e_match.end()].count('\n') + 1
                search_content = search_content[e_match.end():]
    else:
        # 没有 begin 块，查找 end; 或 end.
        end_match = re.search(r'^\s*end\s*[;.]', search_content, re.MULTILINE)
        if end_match:
            return content[:pos + end_match.end()].count('\n') + 1
    
    # 默认返回起始行
    return content[:start_pos].count('\n') + 1


def _extract_units(content: str) -> List[str]:
    """提取 unit 名称"""
    pattern = re.compile(r'^\s*unit\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;', re.MULTILINE | re.IGNORECASE)
    matches = pattern.findall(content)
    return matches


def _extract_uses(content: str) -> List[str]:
    """提取 uses 子句中的单元"""
    pattern = re.compile(r'^\s*uses\s+([^;]+);', re.MULTILINE | re.IGNORECASE)
    matches = pattern.findall(content)
    units = []
    for match in matches:
        items = [item.strip() for item in match.split(',')]
        units.extend(items)
    return units


# ============================================================
# 预编译正则表达式
# ============================================================

# -------- 类型定义 --------
# 支持泛型: TList<T>、TDictionary<TKey, TValue>、TMyClass<T: class>
# class 定义: 排除 class of (metaclass), 父类支持泛型
_CLASS_PATTERN = re.compile(
    r'^\s*'
    r'(T[a-zA-Z_][a-zA-Z0-9_]*(?:<[^>]+(?:<[^>]+>)*>)?)'   # 1: name (支持泛型)
    r'\s*=\s*'
    r'class\b(?!\s+of\b)'                                     # class 但排除 class of (metaclass)
    r'\s*'
    r'(?:\(\s*([a-zA-Z_][a-zA-Z0-9_.<>,\s]*(?:<[^>]+>)?)\s*\))?'  # 2: 父类(支持泛型)
    r'\s*(?:sealed|abstract)?',
    re.MULTILINE | re.IGNORECASE
)
_RECORD_PATTERN = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*(?:<[^>]+>)?)\s*=\s*record\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:<[^>]+>)?)\s*\))?', re.MULTILINE | re.IGNORECASE)
# interface / dispinterface: 支持 GUID ['{...}'], 泛型父接口, 嵌套泛型
_INTERFACE_PATTERN = re.compile(
    r'^\s*'
    r'([a-zA-Z_][a-zA-Z0-9_]*(?:<[^<>]*(?:<[^<>]*>)*>)?)'   # 1: name (支持嵌套泛型)
    r'\s*=\s*'
    r'(interface|dispinterface)\s*'                           # 2: 关键字
    r'(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:<[^<>]*(?:<[^<>]*>)*>)?)\s*\))?'  # 3: 父接口(支持泛型)
    r'(?:\s*\[\s*[a-fA-F0-9\-\{\}"]+\s*\])?',                 # 可选 GUID ['{...}']
    re.MULTILINE | re.IGNORECASE
)
# 匹配 class helper for TSomeClass 和 record helper for TSomeRecord
# class helper for: 可选祖先类, 目标支持泛型
# 语法: identifierName = class helper [(ancestor list)] for TypeIdentifierName
_HELPER_PATTERN = re.compile(
    r'^\s*'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                              # 1: helper name
    r'\s*=\s*class\s+helper\s*'
    r'(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'               # 2: 可选祖先 helper
    r'\s*for\s+'
    r'([a-zA-Z_][a-zA-Z0-9_<>,\s]*(?:<[^<>]*(?:<[^<>]*>)*>)?)',  # 3: 目标类型(支持泛型)
    re.MULTILINE | re.IGNORECASE
)
# record helper for: 目标支持泛型(如 TList<T>), 枚举类型目标
_RECORD_HELPER_PATTERN = re.compile(
    r'^\s*'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                              # 1: helper name
    r'\s*=\s*record\s+helper\s*'
    r'(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'               # 2: 可选祖先 helper
    r'\s*for\s+'
    r'([a-zA-Z_][a-zA-Z0-9_<>,\s]*(?:<[^<>]*(?:<[^<>]*>)*>)?)',  # 3: 目标类型(支持泛型)
    re.MULTILINE | re.IGNORECASE
)
_ENUM_PATTERN = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\(([^)]+)\)\s*;(?!.*\bset\b)', re.MULTILINE | re.IGNORECASE)  # 排除 set of
_SET_PATTERN = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*set\s+of\s+', re.MULTILINE | re.IGNORECASE)

# -------- 函数/过程/构造/析构/运算符 定义 --------
# 一个模式支持多种关键字（通过 group(1)=name, group(2)=return_type 保持兼容）
# 向后兼容: function→KIND_FUNC, procedure→KIND_PROC, constructor→KIND_FUNC, destructor→KIND_PROC
# 所有模式均在提取循环中检查 matched text 确定具体 kind

# Pattern 1 (统一带参模式): 所有带括号参数声明的函数/过程/构造/析构/运算符
# 支持: 可选 class 前缀, 泛型类型参数 <T>, 嵌套括号参数, 可选返回类型
# 匹配如:
#   function Foo(x: Integer): string;
#   procedure Bar(x, y: Integer);
#   class function Create: TObject;
#   class procedure Register;
#   constructor Create(AOwner: TComponent);
#   destructor Destroy; override;
#   class operator Add(a, b: TPoint): TPoint;
#   function ToArray<T>(x: T): TArray<T>;
#   function Foo(a: array of (Integer, String)): Integer;
_FUNC_PATTERN_1 = re.compile(
    r'^\s*(?:'
    r'(?:class\s+)?(?:function|procedure|constructor|destructor)'
    r'|class\s+operator'
    r')\s+'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                             # 1: name
    r'(?:<[^<>]*(?:<[^<>]*>)*>)?'                           # 可选泛型类型参数 <T>
    r'\s*\('
    r'([^()]*(?:\([^()]*\)[^()]*)*)'                         # 2: params (安全: O(n), 支持单层嵌套)
    r'\)'
    r'(?:\s*:\s*([^;]+?))?'                                  # 3: 可选返回类型 (非贪婪到 ;)
    r'\s*;',
    re.MULTILINE | re.IGNORECASE
)

# Pattern 2 (函数无参带返回值): function name: ReturnType;
# 支持: class 前缀, 泛型类型参数
_FUNC_PATTERN_3 = re.compile(
    r'^\s*(?:class\s+)?function\s+'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                             # 1: name
    r'(?:<[^<>]*(?:<[^<>]*>)*>)?'                           # 可选泛型类型参数
    r'\s*:\s*'
    r'([^;]+?)'                                              # 2: return type (非贪婪到 ;)
    r'\s*;',
    re.MULTILINE | re.IGNORECASE
)

# Pattern 3 (过程/构造/析构无参): procedure name; / constructor Create; / destructor Destroy;
# 支持: class 前缀, 泛型类型参数
#   TMyProc = procedure;   ← procedure 不在行首，不匹配 ✓
#   constructor Create;    ← constructor 在行首，匹配 ✓
_FUNC_PATTERN_4 = re.compile(
    r'^\s*(?:'
    r'(?:class\s+)?(?:procedure|constructor|destructor)'
    r')\s+'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                             # 1: name
    r'(?:<[^<>]*(?:<[^<>]*>)*>)?'                           # 可选泛型类型参数
    r'\s*;',
    re.MULTILINE | re.IGNORECASE
)

# -------- 常量定义 --------
# 支持: const X = 值; resourcestring S = '...';
# 支持多行值: const MyStr = 'Hello ' + \n    'World';
_CONST_PATTERN = re.compile(
    r'^\s*(const|resourcestring)\s+'                        # 1: const/resourcestring 关键字
    r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*'                      # 2: name
    r'([^;]+)'                                               # 3: value (允许多行，遇到 ; 结束)
    r';',
    re.MULTILINE | re.IGNORECASE
)

# 支持类型标注常量: X: TypeName = Value;
# 类型名使用 [^;=]+? 非贪婪匹配以支持复杂类型（如 array[0..9] of Integer）
_CONST_PATTERN_TYPED = re.compile(
    r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*'                  # 1: name
    r'([^;=]+?)\s*=\s*'                                      # 2: type (非贪婪到 =)
    r'([^;]+)'                                               # 3: value
    r';',
    re.MULTILINE | re.IGNORECASE
)

# 支持简单常量: SIntOverflow = '...'; 或 toInteger = Char(3);
# 排除类型定义: 右值以 record/class/interface/set/array/^/type/reference to/procedure/function 开头
_CONST_PATTERN_SIMPLE = re.compile(
    r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*'                  # 1: name (支持小写开头)
    r'(?!record\b|class\b|interface\b|set\b|array\b|type\b'
    r'|\^|reference\s+to\b|procedure\b|function\b)'          # 排除类型定义
    r'([^\s;{][^;{]*)'                                       # 2: value
    r';',
    re.MULTILINE | re.IGNORECASE
)

# -------- 类型定义 --------
_TYPE_PATTERN_1 = re.compile(r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*?)(?:;|$)', re.MULTILINE | re.IGNORECASE)
_TYPE_PATTERN_2 = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(array|record|set|file|class|interface)\b', re.MULTILINE | re.IGNORECASE)
# 匹配指针类型: PPointerList = ^TPointerList;
# 匹配指针类型: PPointerList = ^TPointerList; 不再限制 P 前缀
_TYPE_PATTERN_PTR = re.compile(
    r'^\s*'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                              # 1: name (不再强制 PBT 前缀)
    r'\s*=\s*\^'
    r'\s*([a-zA-Z_][a-zA-Z0-9_.<>,\s]*(?:<[^<>]*(?:<[^<>]*>)*>)?)?'  # 2: 可选指向类型(支持泛型)
    r'\s*;',
    re.MULTILINE | re.IGNORECASE
)
# 匹配: TProc = procedure; TNotifyEvent = procedure(Sender) of object; TCallback = reference to procedure(...);
# 匹配函数类型: TListSortCompare = function(Item1, Item2: Pointer): Integer;
# 匹配: TProc = procedure; TNotifyEvent = procedure(Sender) of object;
# TCallback = reference to procedure(...); TCompare = function(...): Integer;
# 支持嵌套括号参数, 可选返回类型, of object, calling conventions
_TYPE_PATTERN_3 = re.compile(
    r'^\s*'
    r'([a-zA-Z_][a-zA-Z0-9_]*)'                              # 1: name (不再限制 T 前缀)
    r'\s*=\s*'
    r'(reference\s+to\s+)?'                                   # 2: reference to
    r'(procedure|function)\s*'                                # 3: procedure/function
    r'(\([^()]*(?:\([^()]*\)[^()]*)*\))?'                     # 4: params (嵌套括号支持)
    r'(?:\s*:\s*([^;]+?))?'                                    # 5: 可选返回类型
    r'(\s+of\s+object)?'                                      # 6: 可选 of object (method pointer)
    r'(?:\s+register|stdcall|cdecl|safecall|fastcall|pascal)?' # 可选 calling convention
    r'\s*;',
    re.MULTILINE | re.IGNORECASE
)


def _extract_classes(content: str) -> List[Dict]:
    """提取类定义"""
    classes = []
    
    # 1. 匹配 class 类型
    for match in _CLASS_PATTERN.finditer(content):
        class_name = match.group(1)
        base_class = match.group(2) if match.group(2) else 'TObject'
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': class_name,
            'base_class': base_class,
            'line': line_num,
            'type_kind': 'class'
        })
    
    # 2. 匹配 record 类型
    for match in _RECORD_PATTERN.finditer(content):
        record_name = match.group(1)
        base_record = match.group(2) if match.group(2) else None
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': record_name,
            'base_class': base_record,
            'line': line_num,
            'type_kind': 'record'
        })
    
    # 3. 匹配 interface 类型
    for match in _INTERFACE_PATTERN.finditer(content):
        interface_name = match.group(1)
        base_interface = match.group(2) if match.group(2) else None
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': interface_name,
            'base_class': base_interface,
            'line': line_num,
            'type_kind': 'interface'
        })
    
    # 4. 匹配 enum 类型
    for match in _ENUM_PATTERN.finditer(content):
        enum_name = match.group(1)
        values = match.group(2).strip()
        if ',' in values:
            line_num = content[:match.start()].count('\n') + 1
            classes.append({
                'name': enum_name,
                'base_class': None,
                'line': line_num,
                'type_kind': 'enum'
            })
    
    return classes


def _extract_functions(content: str) -> List[Dict]:
    """提取函数和过程（兼容新统一模式）"""
    functions = []
    
    for match in _FUNC_PATTERN_1.finditer(content):
        func_name = match.group(1)
        return_type = match.group(3) if match.lastindex and match.lastindex >= 3 else ''
        line_num = content[:match.start()].count('\n') + 1
        mt = match.group(0).lower()
        if 'constructor' in mt:
            kind = 'constructor'
        elif 'destructor' in mt:
            kind = 'destructor'
        elif 'function' in mt or 'operator' in mt:
            kind = 'function'
        else:
            kind = 'procedure'
        functions.append({
            'name': func_name,
            'return_type': return_type,
            'kind': kind,
            'line': line_num
        })
    
    for match in _FUNC_PATTERN_3.finditer(content):
        func_name = match.group(1)
        return_type = match.group(2) if match.lastindex and match.lastindex >= 2 else ''
        line_num = content[:match.start()].count('\n') + 1
        mt = match.group(0).lower()
        if 'constructor' in mt:
            kind = 'constructor'
        elif 'function' in mt or 'operator' in mt:
            kind = 'function'
        else:
            kind = 'procedure'
        functions.append({
            'name': func_name,
            'return_type': return_type,
            'kind': kind,
            'line': line_num
        })
    
    for match in _FUNC_PATTERN_4.finditer(content):
        func_name = match.group(1)
        line_num = content[:match.start()].count('\n') + 1
        mt = match.group(0).lower()
        if 'destructor' in mt:
            kind = 'destructor'
        elif 'constructor' in mt:
            kind = 'constructor'
        elif 'procedure' in mt:
            kind = 'procedure'
        else:
            kind = 'procedure'
        functions.append({
            'name': func_name,
            'return_type': '',
            'kind': kind,
            'line': line_num
        })
    
    return functions


def _extract_constants(content: str) -> List[Dict]:
    """提取常量定义"""
    constants = []
    
    for match in _CONST_PATTERN.finditer(content):
        const_name = match.group(2)
        const_value = match.group(3).strip()
        line_num = content[:match.start()].count('\n') + 1
        
        constants.append({
            'name': const_name,
            'value': const_value,
            'line': line_num
        })
    
    return constants


def _extract_types(content: str) -> List[Dict]:
    """提取类型定义"""
    types = []
    
    for match in _TYPE_PATTERN_1.finditer(content):
        type_name = match.group(1)
        type_def = match.group(2) if match.lastindex is not None and match.lastindex >= 2 else ''
        line_num = content[:match.start()].count('\n') + 1
        
        types.append({
            'name': type_name,
            'definition': type_def,
            'line': line_num
        })
    
    for match in _TYPE_PATTERN_2.finditer(content):
        type_name = match.group(1)
        type_def = match.group(2) if match.lastindex is not None and match.lastindex >= 2 else ''
        line_num = content[:match.start()].count('\n') + 1
        
        types.append({
            'name': type_name,
            'definition': type_def,
            'line': line_num
        })
    
    return types


class DelphiSourceScanner:
    def __init__(self, source_dir: str, output_dir: str, progress_callback: Optional[Callable[[ProgressInfo], None]] = None, force_rebuild: bool = False):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.index_file = self.output_dir / "index" / "source_index.json"
        self.metadata_file = self.output_dir / "index" / "metadata.json"
        self.file_extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.inc'}
        self.progress_callback = progress_callback
        self.force_rebuild = force_rebuild
        self._existing_index: Optional[Dict] = None

        # 创建必要的目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "index").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "data").mkdir(parents=True, exist_ok=True)

    def _load_existing_index(self) -> Optional[Dict]:
        """加载已有的索引文件"""
        if self._existing_index is None:
            if self.index_file.exists():
                try:
                    with open(self.index_file, 'r', encoding='utf-8') as f:
                        self._existing_index = json.load(f)
                    print(f"已加载现有索引: {len(self._existing_index.get('files', []))} 个文件")
                except Exception as e:
                    print(f"加载索引失败: {e}")
                    self._existing_index = None
        return self._existing_index

    def _check_file_changed(self, file_path: Path) -> bool:
        """
        检查文件是否已变更（增量构建核心）
        只检查文件大小和修改时间，不计算哈希
        """
        existing_index = self._load_existing_index()
        if not existing_index:
            return True
        
        # 构建已有文件的快速查找表
        existing_files = {f['full_path']: f for f in existing_index.get('files', [])}
        
        full_path = str(file_path)
        if full_path not in existing_files:
            return True  # 新文件
        
        # 比较大小和修改时间
        existing = existing_files[full_path]
        try:
            stat = file_path.stat()
            if stat.st_size != existing.get('size'):
                return True
            # 比较时间（转换为时间戳）
            current_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            if current_mtime != existing.get('last_modified'):
                return True
        except Exception:
            return True
        
        return False  # 文件未变更

    def scan_directory(self) -> Dict:
        """扫描源码目录,收集文件信息（多进程版本 + 增量构建）"""
        print(f"开始扫描目录: {self.source_dir}")
        
        # 首先收集所有要扫描的文件路径
        file_paths = []
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in self.file_extensions:
                    file_paths.append((str(file_path), str(self.source_dir)))
        
        total_files = len(file_paths)
        print(f"预计扫描 {total_files} 个文件...")
        
        # 增量构建: 检查哪些文件需要重新处理
        changed_files = []
        unchanged_files = {}
        
        if not self.force_rebuild and self._load_existing_index():
            print("检查文件变更...")
            existing_files = {f['full_path']: f for f in self._existing_index.get('files', [])}
            
            for file_path_str, source_dir in file_paths:
                file_path = Path(file_path_str)
                if file_path_str in existing_files:
                    existing = existing_files[file_path_str]
                    try:
                        stat = file_path.stat()
                        if stat.st_size == existing.get('size'):
                            current_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
                            if current_mtime == existing.get('last_modified'):
                                # 文件未变化，直接使用现有数据
                                unchanged_files[file_path_str] = existing
                                continue
                    except Exception:
                        pass
                # 文件已变化或新增
                changed_files.append((file_path_str, source_dir))
            
            print(f"文件状态: {len(unchanged_files)} 个未变化, {len(changed_files)} 个需要重新处理")
        else:
            changed_files = file_paths
        
        # Create progress tracker
        tracker = None
        if self.progress_callback and len(changed_files) > 0:
            tracker = ProgressTracker(len(changed_files), self.progress_callback, update_interval=0.5)
        
        # 计算worker数量
        # 对于I/O密集型任务（磁盘读取），应限制worker数量避免磁盘争用
        # 公式: max(2, cpu_count - 1)
        cpu_cores = cpu_count()
        max_needed = max(2, cpu_cores - 1)
        max_workers = max(1, min(max_needed, total_files // 50))
        
        print(f"Processing: files={len(changed_files)}, workers={max_workers} (cpu_cores={cpu_cores})")
        
        import time
        from concurrent.futures import ProcessPoolExecutor
        
        source_files = []
        file_count = 0
        total_lines = 0
        
        # 先添加未变化的文件
        for unchanged_file in unchanged_files.values():
            source_files.append(unchanged_file)
            file_count += 1
            total_lines += unchanged_file.get('line_count', 0)
        
        # 只处理变化的文件
        if changed_files:
            # Calculate optimal chunk size for IPC efficiency
            chunk_size = max(50, len(changed_files) // (max_workers * 4))
            
            # Use ProcessPoolExecutor with larger chunksize to reduce IPC overhead
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                results = executor.map(_analyze_file_worker, changed_files, chunksize=chunk_size)
                
                for file_info in results:
                    if file_info:
                        source_files.append(file_info)
                        file_count += 1
                        total_lines += file_info.get('line_count', 0)
                        
                        if tracker and file_count % 100 == 0:
                            tracker.update(file_count, f"Scanning: {file_count}/{len(changed_files)}")
        
        if tracker:
            tracker.update(len(changed_files), f"Scanning completed: {file_count} files")
        
        print(f"Scanning completed! Found {file_count} source files, {total_lines} lines of code")

        return {
            'files': source_files,
            'statistics': {
                'total_files': file_count,
                'total_lines': total_lines,
                'scan_time': datetime.now().isoformat()
            }
        }

    def analyze_file(self, file_path: Path) -> Dict:
        """分析单个文件"""
        try:
            # 一次 stat 获取所有元数据
            stat = file_path.stat()
            file_hash = f"{stat.st_mtime}:{stat.st_size}"

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                line_count = len(lines)

            # 相对路径
            rel_path = file_path.relative_to(self.source_dir)

            # 提取文件信息
            file_info = {
                'path': str(rel_path).replace('\\', '/'),
                'full_path': str(file_path),
                'extension': file_path.suffix.lower(),
                'size': stat.st_size,
                'line_count': line_count,
                'hash': file_hash,
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'units': self.extract_units(content),
                'uses': self.extract_uses(content),
                'classes': self.extract_classes(content),
                'functions': self.extract_functions(content),
                'constants': self.extract_constants(content),
                'types': self.extract_types(content)
            }

            return file_info

        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return None

    def extract_units(self, content: str) -> List[str]:
        """提取 unit 名称"""
        # 匹配 unit UnitName;
        pattern = r'^\s*unit\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        return matches

    def extract_uses(self, content: str) -> List[str]:
        """提取 uses 子句中的单元"""
        # 匹配 uses Unit1, Unit2, ...;
        pattern = r'^\s*uses\s+([^;]+);'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        units = []
        for match in matches:
            # 分割逗号分隔的单元名
            items = [item.strip() for item in match.split(',')]
            units.extend(items)
        return units

    def extract_classes(self, content: str) -> List[Dict]:
        """提取类定义（包含 class、record、interface 等类型）"""
        classes = []

        # 1. 匹配 class 类型: TClassName = class(TBaseClass)
        class_pattern = r'^\s*(T[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*class\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?\s*(?:sealed|abstract)?'
        matches = re.finditer(class_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            class_name = match.group(1)
            base_class = match.group(2) if match.group(2) else 'TObject'
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': class_name,
                'base_class': base_class,
                'line': line_num,
                'type_kind': 'class'
            })

        # 2. 匹配 record 类型: TRecordName = record 或 TRecordName = record(TBaseRecord)
        record_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*record\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
        matches = re.finditer(record_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            record_name = match.group(1)
            base_record = match.group(2) if match.group(2) else None
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': record_name,
                'base_class': base_record,
                'line': line_num,
                'type_kind': 'record'
            })

        # 3. 匹配 interface 类型: IInterfaceName = interface(IBaseInterface)
        interface_pattern = r'^\s*(I[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*interface\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
        matches = re.finditer(interface_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            interface_name = match.group(1)
            base_interface = match.group(2) if match.group(2) else None
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': interface_name,
                'base_class': base_interface,
                'line': line_num,
                'type_kind': 'interface'
            })

        # 4. 匹配 enum 类型: TEnumName = (value1, value2, ...)
        enum_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\(([^)]+)\)\s*;'
        matches = re.finditer(enum_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            enum_name = match.group(1)
            values = match.group(2).strip()
            # 检查是否是枚举类型（包含逗号分隔的值）
            if ',' in values:
                line_num = content[:match.start()].count('\n') + 1
                classes.append({
                    'name': enum_name,
                    'base_class': None,
                    'line': line_num,
                    'type_kind': 'enum'
                })

        return classes

    def extract_functions(self, content: str) -> List[Dict]:
        """提取函数/过程/构造/析构/运算符定义"""
        functions = []

        # 使用模块级统一模式（支持 class/constructor/destructor/operator/泛型/嵌套括号）
        # Pattern 1: 带括号参数的声明
        for match in _FUNC_PATTERN_1.finditer(content):
            func_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            mt = match.group(0).lower()
            if 'destructor' in mt:
                ftype = 'destructor'
            elif 'constructor' in mt:
                ftype = 'constructor'
            elif 'function' in mt or 'operator' in mt:
                ftype = 'function'
            else:
                ftype = 'procedure'
            functions.append({
                'name': func_name,
                'line': line_num,
                'type': ftype
            })

        # Pattern 3: function (无参) name: ReturnType;
        for match in _FUNC_PATTERN_3.finditer(content):
            func_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            functions.append({
                'name': func_name,
                'line': line_num,
                'type': 'function'
            })

        # Pattern 4: procedure/constructor/destructor (无参) name;
        for match in _FUNC_PATTERN_4.finditer(content):
            func_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            mt = match.group(0).lower()
            if 'destructor' in mt:
                ftype = 'destructor'
            elif 'constructor' in mt:
                ftype = 'constructor'
            else:
                ftype = 'procedure'
            functions.append({
                'name': func_name,
                'line': line_num,
                'type': ftype
            })

        return functions

    def extract_constants(self, content: str) -> List[Dict]:
        """提取常量定义"""
        constants = []

        # 匹配 const 块中的常量
        const_pattern = r'^\s*const\s*$'
        const_start = None

        for match in re.finditer(const_pattern, content, re.MULTILINE | re.IGNORECASE):
            const_start = match.end()
            break

        if const_start:
            # 提取 const 块后的内容 (直到下一个关键字)
            const_content = content[const_start:]
            const_end = re.search(r'^(?:type|var|begin|implementation|initialization|finalization)\s*$',
                                 const_content, re.MULTILINE | re.IGNORECASE)
            if const_end:
                const_content = const_content[:const_end.start()]

            # 匹配常量定义
            pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);'
            matches = re.finditer(pattern, const_content, re.MULTILINE)

            for match in matches:
                const_name = match.group(1)
                const_value = match.group(2).strip()
                line_num = const_content[:match.start()].count('\n') + 1

                constants.append({
                    'name': const_name,
                    'value': const_value,
                    'line': line_num
                })

        return constants

    def extract_types(self, content: str) -> List[Dict]:
        """提取类型定义"""
        types = []

        # 匹配 type 块中的类型定义
        type_pattern = r'^\s*type\s*$'
        type_start = None

        for match in re.finditer(type_pattern, content, re.MULTILINE | re.IGNORECASE):
            type_start = match.end()
            break

        if type_start:
            # 提取 type 块后的内容 (直到下一个关键字)
            type_content = content[type_start:]
            type_end = re.search(r'^(?:var|begin|implementation|initialization|finalization)\s*$',
                                type_content, re.MULTILINE | re.IGNORECASE)
            if type_end:
                type_content = type_content[:type_end.start()]

            # 匹配简单的类型定义
            pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);'
            matches = re.finditer(pattern, type_content, re.MULTILINE)

            for match in matches:
                type_name = match.group(1)
                type_def = match.group(2).strip()
                line_num = type_content[:match.start()].count('\n') + 1

                types.append({
                    'name': type_name,
                    'definition': type_def,
                    'line': line_num
                })

        return types

    def save_index(self, scan_result: Dict):
        """保存索引到文件"""
        # 保存详细索引
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(scan_result, f, ensure_ascii=False, indent=2)

        # 保存元数据
        metadata = {
            'version': '1.0',
            'source_directory': str(self.source_dir),
            'scan_date': datetime.now().isoformat(),
            'statistics': scan_result['statistics']
        }

        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"索引已保存到: {self.index_file}")
        print(f"元数据已保存到: {self.metadata_file}")

    def create_category_index(self, scan_result: Dict):
        """创建分类索引"""
        categories = {}

        for file_info in scan_result['files']:
            # 按目录分类
            path_parts = file_info['path'].split('/')
            if len(path_parts) > 1:
                category = path_parts[0]
            else:
                category = 'root'

            if category not in categories:
                categories[category] = []

            categories[category].append({
                'path': file_info['path'],
                'unit': file_info['units'][0] if file_info['units'] else None,
                'classes': file_info['classes'],
                'functions': file_info['functions']
            })

        # 保存分类索引
        category_file = self.output_dir / "index" / "category_index.json"
        with open(category_file, 'w', encoding='utf-8') as f:
            json.dump(categories, f, ensure_ascii=False, indent=2)

        print(f"分类索引已保存到: {category_file}")

    def run(self):
        """执行扫描"""
        print("=" * 60)
        print("Delphi 源码知识库扫描器")
        print("=" * 60)

        # 扫描目录
        scan_result = self.scan_directory()

        # 保存索引
        self.save_index(scan_result)

        # 创建分类索引
        self.create_category_index(scan_result)

        print("=" * 60)
        print("扫描完成!")
        print("=" * 60)
        print(f"总计文件: {scan_result['statistics']['total_files']}")
        print(f"总代码行数: {scan_result['statistics']['total_lines']}")
        print(f"索引文件: {self.index_file}")


def main():
    # 配置
    DELPHI_SOURCE_DIR = r"C:\Program Files (x86)\Embarcadero\Studio\22.0\source"
    OUTPUT_DIR = r"c:\User\diandaxia\delphi-knowledge-base"

    # 执行扫描
    scanner = DelphiSourceScanner(DELPHI_SOURCE_DIR, OUTPUT_DIR)
    scanner.run()


if __name__ == "__main__":
    main()
