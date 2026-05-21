"""
PAS 声明解析器 — 解析 Delphi .pas 文件中的字段声明和事件方法

支持:
  - 从 class 声明中提取 published 字段（DFM 组件对应的字段）
  - 从 class 声明中提取事件方法声明
  - 同步增删字段和方法声明（保持 class 结构完整）
  - 解析 uses 子句，支持增删单元
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Set


@dataclass
class PasFieldDecl:
    name: str
    type_name: str
    visibility: str = "published"


@dataclass
class PasMethodDecl:
    name: str
    params: str
    method_type: str = "procedure"
    visibility: str = "published"


@dataclass
class PasClassInfo:
    class_name: str
    ancestor: str
    fields: List[PasFieldDecl] = field(default_factory=list)
    methods: List[PasMethodDecl] = field(default_factory=list)
    class_line_start: int = 0
    class_line_end: int = 0
    published_section_start: int = 0
    published_section_end: int = 0


def parse_pas_class(text: str, class_name: Optional[str] = None) -> Optional[PasClassInfo]:
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    class_start = _find_class_declaration(lines, class_name)
    if class_start < 0:
        return None

    class_name_found, ancestor = _parse_class_header(lines[class_start])
    class_end = _find_class_end(lines, class_start)

    info = PasClassInfo(
        class_name=class_name_found,
        ancestor=ancestor,
        class_line_start=class_start,
        class_line_end=class_end,
    )

    current_visibility = "published"
    published_start = -1
    published_end = class_end

    for i in range(class_start + 1, class_end):
        line = lines[i].strip()

        vis_m = re.match(r'^(strict\s+)?(private|protected|public|published)\b', line, re.IGNORECASE)
        if vis_m:
            vis = vis_m.group(2).lower()
            if vis_m.group(1):
                current_visibility = "strict " + vis
            else:
                current_visibility = vis
            if vis == 'published' and published_start < 0:
                published_start = i
            continue

        if current_visibility in ('published', 'public'):
            field = _parse_field_line(line)
            if field:
                field.visibility = current_visibility
                info.fields.append(field)
                continue

            method = _parse_method_line(line)
            if method:
                method.visibility = current_visibility
                info.methods.append(method)
                continue

    if published_start >= 0:
        info.published_section_start = published_start
        info.published_section_end = published_end
    else:
        info.published_section_start = class_start + 1
        info.published_section_end = class_end

    return info


def _find_class_declaration(lines: List[str], class_name: Optional[str]) -> int:
    for i, line in enumerate(lines):
        m = re.match(r'^\s*(\w+)\s*=\s*class\s*\(\s*(\w+)\s*\)', line)
        if not m:
            m = re.match(r'^\s*(\w+)\s*=\s*class\b', line)
        if m:
            if class_name is None or m.group(1) == class_name:
                return i
    return -1


def _parse_class_header(line: str) -> Tuple[str, str]:
    m = re.match(r'^\s*(\w+)\s*=\s*class\s*\(\s*(\w+)\s*\)', line)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r'^\s*(\w+)\s*=\s*class\b', line)
    if m:
        return m.group(1), "TObject"
    return "Unknown", "TObject"


def _find_class_end(lines: List[str], class_start: int) -> int:
    for i in range(class_start + 1, len(lines)):
        if re.match(r'^\s*end\s*;', lines[i]):
            return i
    return len(lines) - 1


def _parse_field_line(line: str) -> Optional[PasFieldDecl]:
    m = re.match(r'^(\w+)\s*:\s*(\w+)\s*;', line)
    if m:
        return PasFieldDecl(name=m.group(1), type_name=m.group(2))
    return None


def _parse_method_line(line: str) -> Optional[PasMethodDecl]:
    m = re.match(r'^(procedure|function)\s+(\w+)\s*\(([^)]*)\)\s*;', line, re.IGNORECASE)
    if m:
        return PasMethodDecl(
            method_type=m.group(1).lower(),
            name=m.group(2),
            params=m.group(3).strip(),
        )
    m = re.match(r'^(procedure|function)\s+(\w+)\s*;', line, re.IGNORECASE)
    if m:
        return PasMethodDecl(
            method_type=m.group(1).lower(),
            name=m.group(2),
            params="",
        )
    return None


def sync_pas_declarations(
    pas_text: str,
    class_name: Optional[str] = None,
    add_fields: Optional[List[PasFieldDecl]] = None,
    remove_fields: Optional[List[str]] = None,
    add_methods: Optional[List[PasMethodDecl]] = None,
    remove_methods: Optional[List[str]] = None,
    add_uses: Optional[List[str]] = None,
    remove_uses: Optional[List[str]] = None,
) -> str:
    lines = pas_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    line_ending = '\r\n' if '\r\n' in pas_text else '\n'

    add_fields = add_fields or []
    remove_fields = remove_fields or []
    add_methods = add_methods or []
    remove_methods = remove_methods or []
    add_uses = add_uses or []
    remove_uses = remove_uses or []

    if add_uses or remove_uses:
        lines = _sync_uses(lines, add_uses, remove_uses)

    info = parse_pas_class('\n'.join(lines), class_name)
    if not info:
        return line_ending.join(lines)

    existing_field_names = {f.name for f in info.fields}
    existing_method_names = {m.name for m in info.methods}

    new_field_lines = []
    for f in add_fields:
        if f.name not in existing_field_names and f.name not in remove_fields:
            new_field_lines.append(f"    {f.name}: {f.type_name};")

    new_method_lines = []
    for m in add_methods:
        if m.name not in existing_method_names and m.name not in remove_methods:
            if m.params:
                new_method_lines.append(f"    {m.method_type} {m.name}({m.params});")
            else:
                new_method_lines.append(f"    {m.method_type} {m.name};")

    lines_to_remove = set()
    for fname in remove_fields:
        for i in range(info.class_line_start + 1, info.class_line_end):
            stripped = lines[i].strip()
            if re.match(r'^' + re.escape(fname) + r'\s*:\s*\w+\s*;', stripped):
                lines_to_remove.add(i)

    for mname in remove_methods:
        for i in range(info.class_line_start + 1, info.class_line_end):
            stripped = lines[i].strip()
            if re.match(r'^(procedure|function)\s+' + re.escape(mname) + r'\b', stripped, re.IGNORECASE):
                lines_to_remove.add(i)

    impl_lines_to_remove = set()
    for mname in remove_methods:
        for i in range(len(lines)):
            stripped = lines[i].strip()
            if re.match(r'^(procedure|function)\s+\w+\.' + re.escape(mname) + r'\b', stripped, re.IGNORECASE):
                impl_lines_to_remove.add(i)
                for j in range(i + 1, len(lines)):
                    impl_lines_to_remove.add(j)
                    if re.match(r'^end\s*;', lines[j].strip()):
                        break

    impl_lines_to_add = []
    for m in add_methods:
        if m.name not in existing_method_names and m.name not in remove_methods:
            impl_class = info.class_name
            if m.params:
                impl_lines_to_add.append(f"{{TODO: Implement {m.name}}}")
                impl_lines_to_add.append(f"{m.method_type} {impl_class}.{m.name}({m.params});")
            else:
                impl_lines_to_add.append(f"{{TODO: Implement {m.name}}}")
                impl_lines_to_add.append(f"{m.method_type} {impl_class}.{m.name};")
            impl_lines_to_add.append("begin")
            impl_lines_to_add.append("")
            impl_lines_to_add.append("end;")
            impl_lines_to_add.append("")

    insert_pos = info.published_section_end
    for new_line in reversed(new_method_lines + new_field_lines):
        lines.insert(insert_pos, new_line)

    if impl_lines_to_add:
        impl_insert = _find_implementation_end(lines)
        if impl_insert < 0:
            impl_insert = len(lines)
        for new_line in reversed(impl_lines_to_add):
            lines.insert(impl_insert, new_line)

    for idx in sorted(lines_to_remove | impl_lines_to_remove, reverse=True):
        if 0 <= idx < len(lines):
            lines.pop(idx)

    return line_ending.join(lines)


def _sync_uses(lines: List[str], add_units: List[str], remove_units: List[str]) -> List[str]:
    uses_start = -1
    uses_end = -1
    for i, line in enumerate(lines):
        if re.match(r'^\s*uses\b', line, re.IGNORECASE):
            uses_start = i
        if uses_start >= 0 and i >= uses_start:
            if ';' in line:
                uses_end = i
                break

    if uses_start < 0 or uses_end < 0:
        return lines

    uses_text = ""
    for i in range(uses_start, uses_end + 1):
        uses_text += lines[i]

    unit_pattern = re.compile(r'(\w+(?:\.\w+)*)\s*(?:in\s+[^,;]+)?')
    existing_units = []
    for m in unit_pattern.finditer(uses_text):
        unit = m.group(1)
        if unit.lower() != 'uses':
            existing_units.append(unit)

    existing_set = {u.lower() for u in existing_units}
    for u in add_units:
        if u.lower() not in existing_set:
            existing_units.append(u)
            existing_set.add(u.lower())

    for u in remove_units:
        existing_units = [eu for eu in existing_units if eu.lower() != u.lower()]

    existing_units.sort(key=lambda u: u.lower())

    if existing_units:
        new_uses = "uses\n  " + ",\n  ".join(existing_units) + ";"
    else:
        new_uses = "uses"

    new_lines = lines[:uses_start] + new_uses.split('\n') + lines[uses_end + 1:]
    return new_lines


def _find_implementation_end(lines: List[str]) -> int:
    in_impl = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*implementation\b', line, re.IGNORECASE):
            in_impl = True
            continue
        if in_impl and re.match(r'^\s*end\s*\.\s*$', line.strip()):
            return i
    return -1


def extract_event_handlers(pas_text: str, class_name: Optional[str] = None) -> Dict[str, str]:
    result = {}
    pattern = re.compile(
        r'(procedure|function)\s+(\w+)\.(\w+)\s*\(([^)]*)\)\s*;',
        re.IGNORECASE,
    )
    for m in pattern.finditer(pas_text):
        cls = m.group(2)
        method = m.group(3)
        if class_name is None or cls == class_name:
            result[method] = m.group(0).strip()
    return result
