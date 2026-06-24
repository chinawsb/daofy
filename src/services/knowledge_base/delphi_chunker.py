"""
Delphi 源码 Chunker — 将 .pas 文件切割为语义块

不依赖 ZVec 或其他外部库，纯文本处理。
输入: .pas 文件路径
输出: chunk 字典列表

Chunk 策略:
  - class / record / interface / object → 独立结构 chunk（含完整 body）
  - 其余内容（const、type alias、enum、function 等）→ 一个文件级兜底 chunk
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 常量 ──
STRUCTURED_TYPES = {'class', 'record', 'interface', 'object'}
"""需要独立结构 chunk 的类型"""


# ═══════════════════════════════════════════
# 文本预处理
# ═══════════════════════════════════════════

def _strip_comments(text: str) -> str:
    """移除 Delphi 注释，保留行结构不变"""
    # 花括号注释 { ... }
    text = re.sub(r'\{[^}]*\}', ' ', text)
    # 星号括号注释 (* ... *)
    text = re.sub(r'\(\*[^*]*\*\)', ' ', text)
    # 双斜杠注释 //（需要避开字符串内的 //）
    lines = text.split('\n')
    result = []
    for line in lines:
        in_string = False
        for i, c in enumerate(line):
            if c == "'" and (i == 0 or line[i - 1] != '\\'):
                in_string = not in_string
            elif c == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_string:
                line = line[:i] + ' '
                break
        result.append(line)
    return '\n'.join(result)


# ── 声明行正则（一行搞定） ──
_RE_CLASS_DECL = re.compile(
    r'^\s*(\w[\w.]*)\s*=\s*'
    r'(class|record|interface|object)\s*'
    r'(?:\(\s*([\w.,\s]+?)\s*\))?'      # 基类（可选）
    r'(?:\s+class\s+)?'                  # class helper / class of
    r'(?:of\s+\w[\w.]*)?'                # 枚举基类型
    r'(?:\s*;)?',
    re.IGNORECASE
)

_RE_UNIT = re.compile(r'^\s*unit\s+(\w+(?:\.\w+)*)\s*;')
_RE_USES = re.compile(r'uses\s+(.+?);', re.IGNORECASE | re.DOTALL)
_RE_USES_IN = re.compile(r'\s+in\s+[\'"][^\'"]+[\'"]')


# ═══════════════════════════════════════════
# 核心 chunker
# ═══════════════════════════════════════════

def chunk_delphi_file(file_path: str) -> List[Dict]:
    """
    将单个 .pas 文件切割为语义块。

    Args:
        file_path: .pas 文件路径

    Returns:
        chunk 字典列表，每个 chunk 包含:
          - entity_name: 实体名
          - chunk_type: class/record/interface/object/unit
          - base_class: 基类名（仅结构化 chunk）
          - unit_name: 单元名
          - uses_list: uses 列表
          - chunk_text: 代码文本
          - start_line: 起始行号（1-indexed）
          - end_line: 结束行号
          - file_path: 原始文件路径
    """
    # ── 读取文件 ──
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            raw_text = f.read()
    except Exception as e:
        logger.warning(f"读取文件失败: {file_path}: {e}")
        return []

    lines = raw_text.split('\n')
    text = _strip_comments(raw_text)
    tlines = text.split('\n')

    # ── 提取单元名 ──
    unit_name = ''
    for line in tlines:
        m = _RE_UNIT.match(line)
        if m:
            unit_name = m.group(1)
            break

    # ── 提取 uses 列表 ──
    uses_list: List[str] = []
    in_uses = False
    ubuf = ''
    for line in tlines:
        if re.match(r'^\s*uses\s+', line, re.IGNORECASE):
            in_uses = True
            ubuf = line
        elif in_uses:
            ubuf += ' ' + line
            if ';' in line:
                u = _RE_USES.search(ubuf)
                if u:
                    for p in u.group(1).split(','):
                        p = p.strip()
                        p = _RE_USES_IN.sub('', p)  # 去掉 'in filename' 部分
                        p = p.split()[0] if p.split() else p
                        if p and not p.startswith('//'):
                            uses_list.append(p)
                in_uses = False
                ubuf = ''

    # ── 解析 type 段 ──
    chunks: List[Dict] = []
    section: Optional[str] = None  # 'interface' | 'implementation' | None
    type_start = -1  # 'type' 关键字所在行

    i = 0
    while i < len(tlines):
        s = tlines[i].strip()

        # 段落标记
        if re.match(r'^\s*interface\s*$', s, re.IGNORECASE) and section is None:
            section = 'interface'
            i += 1
            continue
        if re.match(r'^\s*implementation\s*$', s, re.IGNORECASE) and section == 'interface':
            section = 'implementation'
            i += 1
            continue

        # interface 段内：识别 type/var/const 边界
        if section == 'interface' and type_start < 0:
            if re.match(r'^\s*type\s*$', s, re.IGNORECASE):
                type_start = i
                i += 1
                continue
            if re.match(r'^\s*(var|const|resourcestring|threadvar)\s*$', s, re.IGNORECASE):
                i += 1
                continue

        # type 段内：识别结构化声明
        if type_start >= 0 and i >= type_start:
            m = _RE_CLASS_DECL.match(s)
            if m:
                name = m.group(1)
                kind = m.group(2).lower()
                base = (m.group(3) or '').split(',')[0].strip()

                # 捕获 body（匹配 begin/end 深度）
                body: List[str] = []
                depth = 0
                j = i
                while j < len(tlines):
                    body.append(lines[j])  # 用原文本保留格式
                    tl = tlines[j].strip()
                    if tl.startswith('begin'):
                        depth += 1
                    elif tl.startswith('end'):
                        if depth > 0:
                            depth -= 1
                        elif tl.rstrip().endswith(';'):
                            j += 1
                            break
                    j += 1

                chunks.append({
                    'entity_name': name,
                    'chunk_type': kind,
                    'base_class': base,
                    'unit_name': unit_name,
                    'uses_list': uses_list,
                    'chunk_text': '\n'.join(body),
                    'start_line': i + 1,
                    'end_line': j + 1,
                    'file_path': str(Path(file_path).as_posix()),
                })
                i = j
                continue

        i += 1

    # ── 兜底：无结构化 chunk 时建文件级 chunk ──
    if not chunks:
        name = unit_name or Path(file_path).stem
        chunks.append({
            'entity_name': name,
            'chunk_type': 'unit',
            'base_class': '',
            'unit_name': unit_name,
            'uses_list': uses_list,
            'chunk_text': raw_text,
            'start_line': 1,
            'end_line': len(lines),
            'file_path': str(Path(file_path).as_posix()),
        })

    return chunks


def chunk_directory(source_dir: str,
                    extensions: set = None,
                    progress_callback=None) -> List[Dict]:
    """
    批量 chunk 一个目录下的所有源文件。

    Args:
        source_dir: 源码目录
        extensions: 文件扩展名集合（默认 {'.pas'}）
        progress_callback: 进度回调 (percent, message, extra_dict)

    Returns:
        所有 chunk 的列表
    """
    if extensions is None:
        extensions = {'.pas'}

    src = Path(source_dir)
    files = sorted(src.rglob('*'))
    files = [f for f in files if f.is_file() and f.suffix.lower() in extensions]

    all_chunks: List[Dict] = []
    for i, f in enumerate(files):
        try:
            chunks = chunk_delphi_file(str(f))
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"Chunk 失败: {f}: {e}")

        if progress_callback and (i + 1) % 100 == 0:
            pct = ((i + 1) / len(files) * 100) if files else 0
            progress_callback(pct, f.name, {"current": i + 1, "total": len(files)})

    return all_chunks


def chunk_file_list(file_paths: List[str],
                    progress_callback=None) -> List[Dict]:
    """
    批量 chunk 一个文件列表。

    Args:
        file_paths: 文件路径列表
        progress_callback: 进度回调 (percent, message, extra_dict)

    Returns:
        所有 chunk 的列表
    """
    all_chunks: List[Dict] = []
    for i, fp in enumerate(file_paths):
        try:
            chunks = chunk_delphi_file(fp)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"Chunk 失败: {fp}: {e}")

        if progress_callback and (i + 1) % 100 == 0:
            pct = ((i + 1) / len(file_paths) * 100) if file_paths else 0
            progress_callback(pct, Path(fp).name, {"current": i + 1, "total": len(file_paths)})

    return all_chunks
