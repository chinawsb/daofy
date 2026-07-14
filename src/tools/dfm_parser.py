"""
DFM 文本解析器 — 将文本格式 DFM 解析为组件树结构

支持标准 DFM 文本格式:
  object Button1: TButton
    Left = 10
    Top = 20
    OnClick = BtnClick
    object Panel1: TPanel
      ...
    end
  end

解析结果为 DfmComponent 树，支持:
  - 属性读取（普通属性 + 事件属性）
  - 子组件遍历
  - 增删改操作
  - 序列化回 DFM 文本

事件判断 / 单元解析:
  - 事件属性: 从 KB 查属性定义，判断类型是否为 method pointer (TNotifyEvent 等)
  - 组件单元: 从 KB 查类定义所在文件，提取单元名 (Vcl.StdCtrls 等)
  - KB 不可用时 fallback 到 On* 前缀启发式
"""

import os
import re
import logging

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple


@dataclass
class DfmProperty:
    name: str
    raw_value: str
    is_event: bool = False

    @property
    def value(self) -> str:
        if self.raw_value.startswith('='):
            return self.raw_value[1:].strip()
        return self.raw_value


@dataclass
class DfmComponent:
    name: str
    class_name: str
    properties: List[DfmProperty] = field(default_factory=list)
    children: List['DfmComponent'] = field(default_factory=list)
    prefix: str = "object"
    raw_indent: str = ""

    def find_child(self, name: str) -> Optional['DfmComponent']:
        for c in self.children:
            if c.name == name:
                return c
            found = c.find_child(name)
            if found:
                return found
        return None

    def find_all_by_class(self, class_name: str) -> List['DfmComponent']:
        result = []
        if self.class_name == class_name:
            result.append(self)
        for c in self.children:
            result.extend(c.find_all_by_class(class_name))
        return result

    def get_events(self) -> List[DfmProperty]:
        return [p for p in self.properties if p.is_event]

    def get_property(self, name: str) -> Optional[DfmProperty]:
        for p in self.properties:
            if p.name == name:
                return p
        return None

    def remove_child(self, name: str) -> bool:
        for i, c in enumerate(self.children):
            if c.name == name:
                self.children.pop(i)
                return True
            if c.remove_child(name):
                return True
        return False

    def all_components(self) -> List['DfmComponent']:
        result = [self]
        for c in self.children:
            result.extend(c.all_components())
        return result


# ============================================================
# KB 服务引用 + 缓存
# ============================================================

_KB_SERVICE = None
_THIRDPARTY_KB_SERVICE = None

_IS_EVENT_CACHE: Dict[str, bool] = {}
_EVENT_TYPE_CACHE: Dict[str, Optional[str]] = {}
_EVENT_PARAMS_CACHE: Dict[str, Optional[str]] = {}
_UNIT_CACHE: Dict[str, Optional[str]] = {}

_DEFAULT_EVENT_PARAMS = "Sender: TObject"


def set_kb_services(delphi_kb=None, thirdparty_kb=None):
    global _KB_SERVICE, _THIRDPARTY_KB_SERVICE
    _KB_SERVICE = delphi_kb
    _THIRDPARTY_KB_SERVICE = thirdparty_kb
    _IS_EVENT_CACHE.clear()
    _EVENT_TYPE_CACHE.clear()
    _EVENT_PARAMS_CACHE.clear()
    _UNIT_CACHE.clear()


# ============================================================
# 事件判断 — 从 KB 查属性类型，不猜 On* 前缀
# ============================================================

def is_event_property(class_name: str, prop_name: str) -> bool:
    cache_key = "{}.{}".format(class_name, prop_name)
    if cache_key in _IS_EVENT_CACHE:
        return _IS_EVENT_CACHE[cache_key]

    event_type = _resolve_event_type(class_name, prop_name)
    if event_type is not None:
        _IS_EVENT_CACHE[cache_key] = True
        return True

    if prop_name.startswith('On') and len(prop_name) > 2 and prop_name[2].isupper():
        _IS_EVENT_CACHE[cache_key] = True
        return True

    _IS_EVENT_CACHE[cache_key] = False
    return False


def _resolve_event_type(class_name: str, prop_name: str) -> Optional[str]:
    for service in (_KB_SERVICE, _THIRDPARTY_KB_SERVICE):
        if service is None:
            continue
        try:
            results = service.search_by_name(class_name)
            for r in results:
                kind = r.get('kind_code', '')
                if kind == 'TC':
                    file_path = r.get('file', {}).get('full_path', '')
                    if file_path:
                        event_type = _scan_event_type_from_source(file_path, prop_name)
                        if event_type:
                            return event_type
        except Exception as e:
            logger.debug("解析事件类型失败: %s", str(e))

    for service in (_KB_SERVICE, _THIRDPARTY_KB_SERVICE):
        if service is None:
            continue
        try:
            results = service.search_by_name(prop_name)
            for r in results:
                kind = r.get('kind_code', '')
                definition = r.get('definition', '')
                if kind == 'MP' and definition:
                    m = re.search(r'Event\s+' + re.escape(prop_name) + r'\s*:\s*(\w+)', definition)
                    if m:
                        return m.group(1)
        except Exception as e:
            logger.debug("解析事件类型失败: %s", str(e))

    return None


def _scan_event_type_from_source(file_path: str, prop_name: str) -> Optional[str]:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return None

    pattern = r'property\s+' + re.escape(prop_name) + r'\s*:\s*(\w+)'
    m = re.search(pattern, content)
    if m:
        return m.group(1)
    return None


# ============================================================
# 事件参数签名 — 从 KB 查 method pointer 定义
# ============================================================

def resolve_event_params(class_name: str, event_name: str) -> str:
    cache_key = "{}.{}".format(class_name, event_name)
    if cache_key in _EVENT_PARAMS_CACHE:
        return _EVENT_PARAMS_CACHE[cache_key] or _DEFAULT_EVENT_PARAMS

    event_type_name = _resolve_event_type(class_name, event_name)
    if event_type_name:
        params = _find_event_type_params(event_type_name)
        if params:
            _EVENT_PARAMS_CACHE[cache_key] = params
            return params

    _EVENT_PARAMS_CACHE[cache_key] = None
    return _DEFAULT_EVENT_PARAMS


def _find_event_type_params(event_type_name: str) -> Optional[str]:
    if event_type_name in _EVENT_TYPE_CACHE:
        return _EVENT_TYPE_CACHE[event_type_name]

    for service in (_KB_SERVICE, _THIRDPARTY_KB_SERVICE):
        if service is None:
            continue
        try:
            results = service.search_by_name(event_type_name)
            for r in results:
                file_path = r.get('file', {}).get('full_path', '')
                if file_path:
                    params = _scan_method_pointer_params(file_path, event_type_name)
                    if params is not None:
                        _EVENT_TYPE_CACHE[event_type_name] = params
                        return params
        except Exception as e:
            logger.debug("解析事件类型失败: %s", str(e))

    return None


def _scan_method_pointer_params(file_path: str, type_name: str) -> Optional[str]:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return None

    pattern = re.escape(type_name) + r'\s*=\s*procedure\s*\(([^)]*)\)\s*of\s*object'
    m = re.search(pattern, content)
    if m:
        return m.group(1).strip()

    pattern2 = re.escape(type_name) + r'\s*=\s*procedure\s+of\s*object'
    if re.search(pattern2, content):
        return ""

    return None


# ============================================================
# 组件单元解析 — 从 KB 查类所在文件，提取单元名
# ============================================================

def resolve_component_unit(class_name: str) -> Optional[str]:
    if class_name in _UNIT_CACHE:
        return _UNIT_CACHE[class_name]

    for service in (_KB_SERVICE, _THIRDPARTY_KB_SERVICE):
        if service is None:
            continue
        try:
            results = service.search_by_name(class_name)
            for r in results:
                kind = r.get('kind_code', '')
                if kind != 'TC':
                    continue
                file_path = r.get('file', {}).get('full_path', '')
                unit_name = _extract_unit_name(file_path)
                if unit_name:
                    _UNIT_CACHE[class_name] = unit_name
                    return unit_name
        except Exception as e:
            logger.debug("解析事件类型失败: %s", str(e))

    _UNIT_CACHE[class_name] = None
    return None


def _extract_unit_name(file_path: str) -> Optional[str]:
    if not file_path:
        return None
    basename = os.path.basename(file_path)
    name, ext = os.path.splitext(basename)
    if ext.lower() in ('.pas', '.dcu', '.dpu'):
        return name
    return None


def collect_all_units(root: DfmComponent) -> List[str]:
    units = []
    seen = set()
    for comp in root.all_components():
        unit = resolve_component_unit(comp.class_name)
        if unit and unit not in seen:
            seen.add(unit)
            units.append(unit)
    return units


# ============================================================
# DFM 文本解析
# ============================================================

def parse_dfm_text(text: str, root_class_name: str = "") -> Optional[DfmComponent]:
    # 移除 UTF-8 BOM（\ufeff），否则首行 object/inherited 因 \s* 不匹配 BOM 而被跳过
    text = text.lstrip('\ufeff')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    root = _parse_dfm_lines(lines, root_class_name)
    return root


def _parse_dfm_lines(lines: List[str], root_class_name: str = "") -> Optional[DfmComponent]:
    stack: List[Tuple[DfmComponent, int]] = []
    root = None

    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            continue

        m = re.match(r'^(\s*)(object|inherited)\s+(\w+)\s*:\s*(\w+)', line)
        if m:
            indent = len(m.group(1))
            comp = DfmComponent(
                name=m.group(3),
                class_name=m.group(4),
                prefix=m.group(2),
                raw_indent=m.group(1),
            )
            while stack and stack[-1][1] >= indent:
                stack.pop()
            if stack:
                stack[-1][0].children.append(comp)
            else:
                root = comp
            stack.append((comp, indent))
            continue

        if stripped == 'end':
            if stack:
                stack.pop()
            continue

        if stack:
            prop = _parse_property_line(stripped, stack[-1][0].class_name)
            if prop:
                stack[-1][0].properties.append(prop)

    return root


def _parse_property_line(line: str, class_name: str = "") -> Optional[DfmProperty]:
    m = re.match(r'^([\w.]+)\s*=\s*(.+)$', line)
    if m:
        name = m.group(1)
        raw_value = m.group(2).strip()
        return DfmProperty(
            name=name,
            raw_value=raw_value,
            is_event=is_event_property(class_name, name) if class_name else _fallback_is_event(name),
        )

    m = re.match(r'^([\w.]+)\s*=\s*$', line)
    if m:
        name = m.group(1)
        return DfmProperty(
            name=name,
            raw_value='',
            is_event=is_event_property(class_name, name) if class_name else _fallback_is_event(name),
        )
    return None


def _fallback_is_event(name: str) -> bool:
    if name.startswith('On') and len(name) > 2 and name[2].isupper():
        return True
    return False


# ============================================================
# 序列化
# ============================================================

def serialize_component(comp: DfmComponent, indent: int = 0, indent_str: str = "  ") -> str:
    lines = []
    prefix = indent_str * indent
    lines.append("{}{} {}: {}".format(prefix, comp.prefix, comp.name, comp.class_name))

    for prop in comp.properties:
        lines.append("{}{}{} = {}".format(prefix, indent_str, prop.name, prop.raw_value))

    for child in comp.children:
        lines.append(serialize_component(child, indent + 1, indent_str))

    lines.append("{}end".format(prefix))
    return "\n".join(lines)


# ============================================================
# 事件收集
# ============================================================

def collect_all_events(root: DfmComponent) -> List[Tuple[str, str, str]]:
    result = []
    for comp in root.all_components():
        for evt in comp.get_events():
            handler = evt.value
            if handler:
                result.append((comp.name, evt.name, handler))
    return result
