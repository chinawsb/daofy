"""
.dproj 项目文件管理工具

支持创建、查看、修改 .dproj 文件配置和源文件引用。
自动备份到 __history 目录。
"""

import uuid
import re
import shutil
from pathlib import Path
from typing import Optional, List, Any, Tuple
import xml.etree.ElementTree as ET
from datetime import datetime

from mcp.types import CallToolResult, TextContent
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger

logger = get_logger(__name__)

# MSBuild 命名空间
MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def _ns(tag: str) -> str:
    """给标签添加 MSBuild 命名空间前缀"""
    if tag.startswith("{"):
        return tag
    return f"{{{MSBUILD_NS}}}{tag}"


def _require(val: Optional[str], name: str = "param") -> str:
    """将 Optional[str] 断言为非 None，用于 entry 到 handler 的类型窄化"""
    if val is None:
        raise ValueError(f"{name} is required")
    return val


def _backup_file(file_path: str) -> Optional[str]:
    """备份文件到 __history 目录，返回备份路径"""
    src = Path(file_path)
    if not src.exists():
        return None

    history_dir = src.parent / "__history"
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{src.stem}_{timestamp}{src.suffix}"
    backup_path = history_dir / backup_name

    try:
        shutil.copy2(str(src), str(backup_path))
        logger.info(f"已备份 {file_path} → {backup_path}")
        return str(backup_path)
    except Exception as e:
        logger.error(f"备份失败: {e}")
        return None


def _parse(file_path: str) -> Any:
    """解析 .dproj 文件，返回 ElementTree 或 None"""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        if root is None:
            logger.error(f"XML 根元素为空: {file_path}")
            return None
        if root.tag != _ns("Project"):
            logger.error(f"根标签不是 Project: {root.tag}")
            return None
        return tree
    except ET.ParseError as e:
        logger.error(f"解析 .dproj XML 失败: {e}")
        return None
    except FileNotFoundError:
        logger.error(f".dproj 文件不存在: {file_path}")
        return None
    except PermissionError:
        logger.error(f"无权限读取 .dproj 文件: {file_path}")
        return None
    except OSError as e:
        logger.error(f"读取 .dproj 文件 I/O 错误: {e}")
        return None
    except Exception as e:
        logger.error(f"解析 .dproj 文件时发生意外错误: {e}")
        return None


def _parse_tree(file_path: str) -> Any:
    """解析 .dproj 文件，返回 (tree, root) 或 None"""
    tree = _parse(file_path)
    if tree is None:
        return None
    root = tree.getroot()
    if root is None:
        return None
    return tree, root


def _find_pg(root: ET.Element, config: Optional[str] = None, platform: Optional[str] = None) -> List[ET.Element]:
    """查找匹配条件的 PropertyGroup。config/platform=None 时返回无条件组。"""
    groups = root.findall(_ns("PropertyGroup"))
    if config is None and platform is None:
        # 返回第一个无条件 PropertyGroup
        return [g for g in groups if not g.get("Condition")]

    result = []
    for group in groups:
        condition = group.get("Condition", "")
        match = True
        if config and f"'$(Config)'=='{config}'" not in condition:
            match = False
        if platform and f"'$(Platform)'=='{platform}'" not in condition:
            match = False
        if match:
            result.append(group)
    return result


def _find_or_create(parent: ET.Element, tag: str) -> ET.Element:
    """查找子元素，不存在则创建"""
    full = _ns(tag)
    elem = parent.find(full)
    if elem is None:
        elem = ET.SubElement(parent, full)
    return elem


def _find_or_create_item_group(root: ET.Element) -> ET.Element:
    """查找第一个 ItemGroup，不存在则追加"""
    groups = root.findall(_ns("ItemGroup"))
    if groups:
        return groups[0]
    # 追加到 Project 末尾（Import 之前）
    elem = ET.SubElement(root, _ns("ItemGroup"))
    return elem


def _find_dcc_ref(item_group: ET.Element, file_name: str) -> Optional[ET.Element]:
    """在 ItemGroup 中按文件名查找 DCCReference"""
    target = file_name.lower()
    for ref in item_group.findall(_ns("DCCReference")):
        inc = ref.get("Include", "")
        if inc and Path(inc).name.lower() == target:
            return ref
    return None


# ──────────────────────────────────────────────
# .dpk 同步工具（contains / requires）
# ──────────────────────────────────────────────

def _get_dpk_path_from_dproj(dproj_path: str) -> Optional[str]:
    """从 .dproj 文件获取对应的 .dpk 文件路径（仅 Package 项目）"""
    try:
        tree = ET.parse(dproj_path)
        root = tree.getroot()
    except Exception:
        return None

    # 检查 AppType 是否为 Package
    for pg in root.findall(_ns("PropertyGroup")):
        cond = pg.get("Condition", "")
        if cond:  # 跳过有条件 PropertyGroup
            continue
        app = pg.find(_ns("AppType"))
        if app is not None and app.text and app.text.lower() == "package":
            ms = pg.find(_ns("MainSource"))
            if ms is not None and ms.text:
                dpk_path = str(Path(dproj_path).parent / ms.text)
                if Path(dpk_path).exists():
                    return dpk_path
    return None


def _dpk_parse_entries(dpk_path: str, section: str = "contains") -> List[str]:
    """解析 .dpk 中 contains/requires 节的每一条文本

    Args:
        dpk_path: .dpk 文件路径
        section: 节名 "contains" 或 "requires"

    Returns:
        原始文本行列表（保留原始缩进），不含节头、节尾、注释、空行

    Note:
        停止条件因 section 不同而异：
        - section="requires" 时遇到 "contains" 或 "end" 停止
        - section="contains" 时遇到 "requires"（不会出现）或 "end" 停止
        两种情况下空行也会触发停止判断（仅当上一条以 ";" 结束时真正 break）
    """
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk 文件不存在或无法读取: {dpk_path}")
        return []
    lines = content.splitlines()
    section_lower = section.lower()

    in_section = False
    entries: List[str] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if in_section:
            # 遇到 requires / end / 空行时尝试终止
            # section="contains" 时 requires 不会出现（contains 在 requires 之后），
            # 但通用解析器保留此条件以应对逆向排列的罕见情况
            if lower.startswith("requires") or lower.startswith("end") or lower == "":
                if entries and entries[-1].rstrip().endswith(";"):
                    break  # 完整条目结束
                continue
            # 跳过纯注释
            if lower.startswith("{"):
                continue
            entries.append(line)

        if lower.startswith(section_lower):
            in_section = True

    return entries


def _dpk_contains_entries(dpk_path: str) -> List[Tuple[str, str, str]]:
    """解析 .dpk contains 条目

    Args:
        dpk_path: .dpk 文件路径

    Returns:
        列表，每项为 (原始行, 单元名, 文件路径)
        文件路径中的 "/" 被统一替换为 "\\"
    """
    raw = _dpk_parse_entries(dpk_path, "contains")
    pattern = re.compile(r"^\s*(\w+)\s+in\s+'([^']+)'\s*,?\s*;?\s*$", re.IGNORECASE)
    result: List[Tuple[str, str, str]] = []
    for line in raw:
        m = pattern.match(line)
        if m:
            result.append((line, m.group(1), m.group(2).replace("/", "\\")))
    return result


def _dpk_requires_entries(dpk_path: str) -> List[Tuple[str, str]]:
    """解析 .dpk requires 条目

    Args:
        dpk_path: .dpk 文件路径

    Returns:
        列表，每项为 (原始行, 包名)
    """
    raw = _dpk_parse_entries(dpk_path, "requires")
    pattern = re.compile(r"^\s*(\w[\w.]*)\s*,?\s*;?\s*$")
    result: List[Tuple[str, str]] = []
    for line in raw:
        m = pattern.match(line)
        if m:
            result.append((line, m.group(1)))
    return result


def _dpk_add_contains(dpk_path: str, source_file: str, unit_name: str) -> Optional[str]:
    """向 .dpk contains 添加一条 '单元名 in '源文件路径',''

    如果已存在（路径匹配）则返回 None。新条目始终到最后。

    Args:
        dpk_path: .dpk 文件路径
        source_file: 源文件路径（如 Source\\Unit1.pas）
        unit_name: 单元名（如 Unit1）

    Returns:
        备份路径（成功时），None（已存在或失败时）
    """
    # 检查是否已存在
    existing = _dpk_contains_entries(dpk_path)
    norm_path = source_file.replace("/", "\\")
    for _, _, fp in existing:
        if fp.lower() == norm_path.lower():
            return None

    backup_path = _backup_file(dpk_path)

    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk 文件不存在或无法读取: {dpk_path}")
        return None

    lines = content.splitlines()
    insert_idx = -1
    in_contains = False
    has_trailing_semicolon = False
    last_entry_idx = -1  # 跟踪最后一条类似条目的行号（即使没有分隔符）

    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                # 如果有 contains 条目但没有分隔符，退回到 end. 前插入
                if insert_idx == -1 and last_entry_idx >= 0:
                    insert_idx = i
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("{"):
                continue
            # 即使没有分号/逗号，也追踪条目的位置
            if re.match(r"^\s*(\w+)\s+in\s+'([^']+)'", line, re.IGNORECASE):
                last_entry_idx = i
            if stripped.endswith(";"):
                has_trailing_semicolon = True
                insert_idx = i + 1
            elif stripped.endswith(","):
                has_trailing_semicolon = False
                insert_idx = i + 1
        if lower.startswith("contains"):
            in_contains = True

    if insert_idx == -1:
        # 没有 contains 节，追加
        # 找到 end. 前面插入
        for i, line in enumerate(lines):
            if line.strip().lower() == "end.":
                # 在 end. 前插入 requires 和 contains
                indent = "  "
                new_lines = [
                    "",
                    "requires",
                    "  rtl;",
                    "",
                    "contains",
                    f"  {unit_name} in '{source_file}';",
                ]
                for j, nl in enumerate(reversed(new_lines)):
                    lines.insert(i, nl)
                break
        else:
            return backup_path  # 无法解析
    else:
        indent = "  "
        suffix = ";"
        if has_trailing_semicolon:
            # 把前一条的分号改逗号
            prev_line = lines[insert_idx - 1].rstrip()
            if prev_line.endswith(";"):
                lines[insert_idx - 1] = prev_line[:-1] + ","
            suffix = ";"
        elif insert_idx > 0:
            # 在前一条末尾加逗号
            prev_line = lines[insert_idx - 1].rstrip()
            if not prev_line.endswith(",") and not prev_line.endswith(";"):
                lines[insert_idx - 1] = prev_line + ","
            suffix = ";"
        new_line = f"{indent}{unit_name} in '{source_file}'{suffix}"
        lines.insert(insert_idx, new_line)

    Path(dpk_path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_remove_contains(dpk_path: str, source_file: str) -> Optional[str]:
    """从 .dpk contains 移除匹配源文件的条目，并修复末尾逗号/分号

    Args:
        dpk_path: .dpk 文件路径
        source_file: 源文件名（如 Unit1.pas）或完整路径

    Returns:
        备份路径（成功时），None（未找到或失败时）
    """
    norm_path = source_file.replace("/", "\\").lower()
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk 文件不存在或无法读取: {dpk_path}")
        return None
    lines = content.splitlines()

    # 用解析匹配定位要删除的行，避免字符串全等问题
    remove_indices: set[int] = set()
    in_contains = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        lower = stripped.lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                break
            if not stripped or lower.startswith("{"):
                continue
            m = re.match(r"^\s*(\w+)\s+in\s+'([^']+)'\s*,?\s*;?\s*$", line, re.IGNORECASE)
            if m and m.group(2).replace("/", "\\").lower() == norm_path:
                remove_indices.add(i)
        if lower.startswith("contains"):
            in_contains = True

    if not remove_indices:
        return None

    backup_path = _backup_file(dpk_path)

    # 删除行
    new_lines = [line for i, line in enumerate(lines) if i not in remove_indices]

    # 修复分隔符：查找 contains 中剩余的最后一个条目，确保其以 ";" 结尾
    in_contains = False
    last_contains_idx = -1
    for i, line in enumerate(new_lines):
        stripped = line.strip()
        lower = stripped.lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                break
            if not stripped or lower.startswith("{"):
                continue
            m = re.match(r"^\s*(\w+)\s+in\s+'([^']+)'", line, re.IGNORECASE)
            if m:
                last_contains_idx = i
        if lower.startswith("contains"):
            in_contains = True

    if last_contains_idx >= 0:
        last_line = new_lines[last_contains_idx].rstrip()
        if last_line.endswith(","):
            new_lines[last_contains_idx] = last_line[:-1] + ";"

    Path(dpk_path).write_text("\n".join(new_lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_add_requires(dpk_path: str, package_name: str) -> Optional[str]:
    """向 .dpk requires 添加包依赖

    自动检测新条目是否是最后一条（下一行为 contains/end），
    是则用 ";" 结尾，否则用 ","。
    #2 已存在（同名匹配）则返回 None。

    Args:
        dpk_path: .dpk 文件路径
        package_name: 包名（如 vcl、rtl）

    Returns:
        备份路径（成功时），None（已存在时）
    """
    existing = _dpk_requires_entries(dpk_path)
    for _, name in existing:
        if name.lower() == package_name.lower():
            return None

    backup_path = _backup_file(dpk_path)
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk 文件不存在或无法读取: {dpk_path}")
        return None
    lines = content.splitlines()
    insert_idx = -1
    in_requires = False

    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if in_requires:
            if lower.startswith("contains") or lower.startswith("end"):
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.endswith(","):
                insert_idx = i + 1
            elif stripped.endswith(";"):
                insert_idx = i + 1
        if lower.startswith("requires"):
            in_requires = True

    if insert_idx == -1:
        # 没有 requires 节，在 end. 前插入
        for i, line in enumerate(lines):
            if line.strip().lower() == "end.":
                new_lines = ["", "requires", f"  {package_name};"]
                for j, nl in enumerate(reversed(new_lines)):
                    lines.insert(i, nl)
                break
    else:
        # 判断新条目是否是最后一条（下一行为 contains/end）
        is_last = True
        if insert_idx < len(lines):
            next_line = lines[insert_idx].strip().lower()
            if not (next_line.startswith("contains") or next_line.startswith("end") or next_line == ""):
                is_last = False
        # 前一条改逗号（只有前一条以分号结束时需要）
        if insert_idx > 0:
            prev = lines[insert_idx - 1].rstrip()
            if prev.endswith(";"):
                lines[insert_idx - 1] = prev[:-1] + ","
            elif not prev.endswith(",") and prev.strip():
                lines[insert_idx - 1] = prev + ","
        suffix = ";" if is_last else ","
        lines.insert(insert_idx, f"  {package_name}{suffix}")

    Path(dpk_path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_remove_requires(dpk_path: str, package_name: str) -> Optional[str]:
    """从 .dpk requires 移除包依赖

    工具函数，当前未在 handler 中自动调用（requires 由用户手动管理，
    不随源码文件增删自动变化）。供脚本/手动调用使用。

    Args:
        dpk_path: .dpk 文件路径
        package_name: 包名

    Returns:
        备份路径（成功时），None（未找到时）
    """
    existing = _dpk_requires_entries(dpk_path)
    to_remove = [line for line, name in existing if name.lower() == package_name.lower()]
    if not to_remove:
        return None

    backup_path = _backup_file(dpk_path)
    content = Path(dpk_path).read_text(encoding="utf-8-sig")
    lines = content.splitlines()
    remove_set = set()
    for rm_line in to_remove:
        for i, line in enumerate(lines):
            if line.rstrip() == rm_line.rstrip():
                remove_set.add(i)
                break

    new_lines = [line for i, line in enumerate(lines) if i not in remove_set]
    Path(dpk_path).write_text("\n".join(new_lines) + "\n", encoding="utf-8-sig")
    return backup_path


# ──────────────────────────────────────────────
# 各 action handler
# ──────────────────────────────────────────────

def _infer_app_type(framework_type: str, app_type: Optional[str] = None) -> str:
    """推断 AppType，默认 Application"""
    if app_type:
        return app_type
    if framework_type == "None":
        return "Console"
    return "Application"


def _sanitized_project_name(main_source: str) -> str:
    """从主源文件名中提取项目名（去除扩展名）"""
    return Path(main_source).stem


def _default_namespace(framework_type: str) -> str:
    """根据框架类型返回默认命名空间"""
    if framework_type == "VCL":
        return "System;System.Win;Winapi;Vcl;Vcl.Forms"
    elif framework_type == "FMX":
        return "System;System.Win;Winapi;FMX;FMX.Forms"
    else:
        # None (Console / Library / Package) — 无 GUI 引用
        return "System;Xml;Data;Datasnap;Web;Soap"


def _is_package(app_type: str) -> bool:
    """判断是否为组件包"""
    return app_type.lower() == "package"


def _add_property_group_hierarchy(
    root: ET.Element,
    project_name: str,
    configs: List[str],
    namespace: str,
    framework_type: str,
    app_type: str,
    platforms: List[str],
    unit_search_paths: Optional[List[str]] = None,
    old_format: bool = False,
) -> None:
    """构建 Delphi .dproj 的 PropertyGroup 继承层次结构

    old_format=True 时跳过所有平台子 PG（适用于 ProjectVersion < 17.0 的早期项目）。

    输出 PropertyGroup 顺序：
      1. Base config PG
      2. Base + platform PGs (skip if old_format)
      3. Cfg_1 config PG
      4. Cfg_1 + platform PGs (skip if old_format)
      5. Cfg_2 config PG
      6. Cfg_2 + platform PGs (skip if old_format)
      7. '$(Base)'!='' — 共享项目属性
      8. '$(Base_{platform})'!='' — 各平台专属共享属性 (skip if old_format)
      9. '$(Cfg_1)'!='' — Cfg_1 编译属性
      10. '$(Cfg_2)'!='' — Cfg_2 编译属性
    """

    is_pkg = _is_package(app_type)
    is_console = app_type == "Console"

    def _cfg_is_debug(name: str) -> bool:
        return name.lower() in ("debug", "debug_", "dbg")

    def _cfg_is_release(name: str) -> bool:
        return name.lower() in ("release", "release_", "rel")

    def _cfg_bt_buildtype(name: str) -> str:
        return "Debug" if _cfg_is_debug(name) else "Release"

    # ── 1. Base config PropertyGroup ──
    pg_base = ET.SubElement(root, _ns("PropertyGroup"))
    pg_base.set("Condition", "'$(Config)'=='Base' or '$(Base)'!=''")
    ET.SubElement(pg_base, _ns("Base")).text = "true"

    # ── 2. Base + platform PropertyGroups (iterates all platforms) ──
    if not old_format:
        for plat in platforms:
            plat_cond = (
                f"('$(Platform)'=='{plat}' and '$(Base)'=='true')"
                f" or '$(Base_{plat})'!=''"
            )
            pg_bp = ET.SubElement(root, _ns("PropertyGroup"))
            pg_bp.set("Condition", plat_cond)
            ET.SubElement(pg_bp, _ns(f"Base_{plat}")).text = "true"
            ET.SubElement(pg_bp, _ns("CfgParent")).text = "Base"
            ET.SubElement(pg_bp, _ns("Base")).text = "true"

    # ── 3-4. Config-specific PropertyGroups (Cfg_1 = configs[0]) ──
    cfg1_name = configs[0]
    pg_cfg1 = ET.SubElement(root, _ns("PropertyGroup"))
    pg_cfg1.set("Condition", f"'$(Config)'=='{cfg1_name}' or '$(Cfg_1)'!=''")
    ET.SubElement(pg_cfg1, _ns("Cfg_1")).text = "true"
    ET.SubElement(pg_cfg1, _ns("CfgParent")).text = "Base"
    ET.SubElement(pg_cfg1, _ns("Base")).text = "true"

    # Cfg_1 + platform PGs
    if not old_format:
        for plat in platforms:
            plat_cond = (
                f"('$(Platform)'=='{plat}' and '$(Cfg_1)'=='true')"
                f" or '$(Cfg_1_{plat})'!=''"
            )
            pg_cfg1p = ET.SubElement(root, _ns("PropertyGroup"))
            pg_cfg1p.set("Condition", plat_cond)
            ET.SubElement(pg_cfg1p, _ns(f"Cfg_1_{plat}")).text = "true"
            ET.SubElement(pg_cfg1p, _ns("CfgParent")).text = "Cfg_1"
            ET.SubElement(pg_cfg1p, _ns("Cfg_1")).text = "true"
            ET.SubElement(pg_cfg1p, _ns("Base")).text = "true"

    # ── 5-6. Config-specific PropertyGroups (Cfg_2 = configs[1], if exists) ──
    if len(configs) > 1:
        cfg2_name = configs[1]
        pg_cfg2 = ET.SubElement(root, _ns("PropertyGroup"))
        pg_cfg2.set("Condition", f"'$(Config)'=='{cfg2_name}' or '$(Cfg_2)'!=''")
        ET.SubElement(pg_cfg2, _ns("Cfg_2")).text = "true"
        ET.SubElement(pg_cfg2, _ns("CfgParent")).text = "Base"
        ET.SubElement(pg_cfg2, _ns("Base")).text = "true"

        # Cfg_2 + platform PGs
        if not old_format:
            for plat in platforms:
                plat_cond = (
                    f"('$(Platform)'=='{plat}' and '$(Cfg_2)'=='true')"
                    f" or '$(Cfg_2_{plat})'!=''"
                )
                pg_cfg2p = ET.SubElement(root, _ns("PropertyGroup"))
                pg_cfg2p.set("Condition", plat_cond)
                ET.SubElement(pg_cfg2p, _ns(f"Cfg_2_{plat}")).text = "true"
                ET.SubElement(pg_cfg2p, _ns("CfgParent")).text = "Cfg_2"
                ET.SubElement(pg_cfg2p, _ns("Cfg_2")).text = "true"
                ET.SubElement(pg_cfg2p, _ns("Base")).text = "true"

    # ── 7. '$(Base)'!='' — 共享项目属性 ──
    pg_base_shared = ET.SubElement(root, _ns("PropertyGroup"))
    pg_base_shared.set("Condition", "'$(Base)'!=''")
    ET.SubElement(pg_base_shared, _ns("SanitizedProjectName")).text = project_name
    ET.SubElement(pg_base_shared, _ns("DCC_Namespace")).text = namespace
    ET.SubElement(pg_base_shared, _ns("DCC_DcuOutput")).text = ".\\$(Platform)\\$(Config)"
    ET.SubElement(pg_base_shared, _ns("DCC_ExeOutput")).text = ".\\$(Platform)\\$(Config)"

    # DCC_E/N/S/F/K — Package 与 App 不同
    if is_pkg:
        ET.SubElement(pg_base_shared, _ns("DCC_E")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_N")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_S")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_F")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_K")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_BRCC")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_Bsc")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_UseDesignIde")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_SymbolReferenceInfo")).text = "0"
        ET.SubElement(pg_base_shared, _ns("DCC_Define")).text = "DEBUG"
        ET.SubElement(
            pg_base_shared, _ns("DCC_DcuPackage")
        ).text = f"{project_name}.dcp"
        ET.SubElement(
            pg_base_shared, _ns("DCC_BplOutput")
        ).text = "..\\..\\$(Platform)\\$(Config)"
        ET.SubElement(
            pg_base_shared, _ns("DCC_DcpOutput")
        ).text = ".\\$(Platform)\\$(Config)"
        # 包签名元素
        ET.SubElement(pg_base_shared, _ns("GenPackage")).text = "true"
        ET.SubElement(pg_base_shared, _ns("RuntimeOnlyPackage")).text = "true"
        ET.SubElement(pg_base_shared, _ns("GenDll")).text = "true"
    else:
        ET.SubElement(pg_base_shared, _ns("DCC_E")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_N")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_S")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_F")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_K")).text = "false"

    if unit_search_paths:
        ET.SubElement(
            pg_base_shared, _ns("DCC_UnitSearchPath")
        ).text = ";".join(unit_search_paths)

    # ── 8. '$(Base_{platform})'!='' — 各平台专属共享属性 ──
    if not old_format:
        for plat in platforms:
            pg_bp_shared = ET.SubElement(root, _ns("PropertyGroup"))
            pg_bp_shared.set("Condition", f"'$(Base_{plat})'!=''")

            if plat == "Win32":
                win32_ns = "Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win;Bde"
            else:
                win32_ns = "Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win"
            ET.SubElement(
                pg_bp_shared, _ns("DCC_Namespace")
            ).text = f"{win32_ns};$(DCC_Namespace)"

            if framework_type in ("VCL", "FMX") and not is_pkg:
                ET.SubElement(pg_bp_shared, _ns("AppEnableRuntimeThemes")).text = "true"
                ET.SubElement(
                    pg_bp_shared, _ns("Manifest_File")
                ).text = "$(BDS)\\bin\\default_app.manifest"
            elif app_type == "Library":
                pass  # DLL 通常没有 manifest

            if app_type == "Library":
                ET.SubElement(pg_bp_shared, _ns("GenDll")).text = "true"

            # BT_BuildType: IDE 调试辅助
            ET.SubElement(pg_bp_shared, _ns("BT_BuildType")).text = "Debug"

            # DCC_ConsoleTarget: Console 应用
            if is_console:
                ET.SubElement(pg_bp_shared, _ns("DCC_ConsoleTarget")).text = "true"

    # ── 9. Cfg_1 专属编译属性 (configs[0]) ──
    cfg1_debug = _cfg_is_debug(cfg1_name)
    cfg1_release = _cfg_is_release(cfg1_name)
    pg_cfg1_props = ET.SubElement(root, _ns("PropertyGroup"))
    pg_cfg1_props.set("Condition", "'$(Cfg_1)'!=''")
    if cfg1_debug:
        ET.SubElement(pg_cfg1_props, _ns("BT_BuildType")).text = "Debug"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = "DEBUG;$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugDCUs")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "false"
        ET.SubElement(pg_cfg1_props, _ns("DCC_GenerateStackFrames")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"
    elif cfg1_release:
        ET.SubElement(pg_cfg1_props, _ns("BT_BuildType")).text = "Release"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = f"{cfg1_name.upper()};$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_LocalDebugSymbols")).text = "false"
        ET.SubElement(pg_cfg1_props, _ns("DCC_SymbolReferenceInfo")).text = "0"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInformation")).text = "0"
    else:
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = f"{cfg1_name.upper()};$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"

    # ── 10. Cfg_2 专属编译属性 (configs[1], if exists) ──
    if len(configs) > 1:
        cfg2_name = configs[1]
        cfg2_debug = _cfg_is_debug(cfg2_name)
        cfg2_release = _cfg_is_release(cfg2_name)
        pg_cfg2_props = ET.SubElement(root, _ns("PropertyGroup"))
        pg_cfg2_props.set("Condition", "'$(Cfg_2)'!=''")
        if cfg2_debug:
            ET.SubElement(pg_cfg2_props, _ns("BT_BuildType")).text = "Debug"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = "DEBUG;$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugDCUs")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Optimize")).text = "false"
            ET.SubElement(pg_cfg2_props, _ns("DCC_GenerateStackFrames")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInfoInExe")).text = "true"
        elif cfg2_release:
            ET.SubElement(pg_cfg2_props, _ns("BT_BuildType")).text = "Release"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = "RELEASE;$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_LocalDebugSymbols")).text = "false"
            ET.SubElement(pg_cfg2_props, _ns("DCC_SymbolReferenceInfo")).text = "0"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInformation")).text = "0"
        else:
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = f"{cfg2_name.upper()};$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Optimize")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInfoInExe")).text = "false"


async def _handle_create(
    project_path: str,
    main_source: str,
    project_guid: Optional[str] = None,
    project_version: str = "18.2",
    framework_type: str = "VCL",
    app_type: Optional[str] = None,
    unit_search_paths: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    configs: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
) -> CallToolResult:
    """创建新的 .dproj 文件（IDE 兼容格式）"""
    if Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件已存在: {project_path}")],
            isError=True,
        )

    Path(project_path).parent.mkdir(parents=True, exist_ok=True)

    if not project_guid:
        project_guid = "{" + str(uuid.uuid4()).upper() + "}"
    else:
        if not project_guid.startswith("{"):
            project_guid = "{" + project_guid
        if not project_guid.endswith("}"):
            project_guid = project_guid + "}"

    if not configs:
        configs = ["Debug", "Release"]
    if not platforms:
        platforms = ["Win32"]
    if namespace is None:
        namespace = _default_namespace(framework_type)

    resolved_app_type = _infer_app_type(framework_type, app_type)
    project_name = _sanitized_project_name(main_source)
    is_pkg = _is_package(resolved_app_type)

    # 根据 ProjectVersion 判断是否使用旧格式（< 17.0 = pre-XE3 简化格式）
    try:
        project_ver = float(project_version)
    except ValueError:
        project_ver = 18.2
    old_format = project_ver < 17.0

    ET.register_namespace("", MSBUILD_NS)
    root = ET.Element(_ns("Project"))

    # ── Header PropertyGroup（项目基本信息） ──
    pg = ET.SubElement(root, _ns("PropertyGroup"))
    ET.SubElement(pg, _ns("ProjectGuid")).text = project_guid
    ET.SubElement(pg, _ns("MainSource")).text = main_source
    config_cond = ET.SubElement(pg, _ns("Config"))
    config_cond.set("Condition", "'$(Config)'==''")
    config_cond.text = configs[0]
    ET.SubElement(pg, _ns("ProjectVersion")).text = project_version
    ET.SubElement(pg, _ns("Base")).text = "True"
    ET.SubElement(pg, _ns("AppType")).text = resolved_app_type
    ET.SubElement(pg, _ns("FrameworkType")).text = framework_type

    primary_plat = platforms[0]
    plat_elem = ET.SubElement(pg, _ns("Platform"))
    plat_elem.set("Condition", "'$(Platform)'==''")
    plat_elem.text = primary_plat

    if old_format:
        # 旧格式：无 TargetedPlatforms，带 DCC_DCCCompiler
        if primary_plat == "Win32":
            ET.SubElement(pg, _ns("DCC_DCCCompiler")).text = "DCC32"
    else:
        # 现代格式：位掩码 — 1=Win32, 2=Win64, 4=OSX64, 8=iOSDevice64, ...
        targeted_mask = _compute_targeted_platforms_mask(platforms)
        ET.SubElement(pg, _ns("TargetedPlatforms")).text = str(targeted_mask)
        if primary_plat == "Win32" and resolved_app_type in ("Console", "Library"):
            ET.SubElement(pg, _ns("DCC_DCCCompiler")).text = "DCC32"

    # ── PropertyGroup 继承层次 ──
    _add_property_group_hierarchy(
        root=root,
        project_name=project_name,
        configs=configs,
        namespace=namespace,
        framework_type=framework_type,
        app_type=resolved_app_type,
        platforms=platforms,
        unit_search_paths=unit_search_paths,
        old_format=old_format,
    )

    # ── ItemGroup（源文件引用 + BuildConfiguration） ──
    ig = ET.SubElement(root, _ns("ItemGroup"))

    # DelphiCompile（Package 项目也需要，参考 GR32_R.dproj）
    dc = ET.SubElement(ig, _ns("DelphiCompile"))
    if old_format:
        # 旧格式使用字面量文件名（参考 HCL D2010, FlexCel D2007）
        dc.set("Include", main_source)
    else:
        dc.set("Include", "$(MainSource)")
    ET.SubElement(dc, _ns("MainSource")).text = "MainSource"

    if sources:
        for src in sources:
            ref = ET.SubElement(ig, _ns("DCCReference"))
            ref.set("Include", src)

    # BuildConfiguration 条目（先 Base，然后各 config）
    bc_base = ET.SubElement(ig, _ns("BuildConfiguration"))
    bc_base.set("Include", "Base")
    ET.SubElement(bc_base, _ns("Key")).text = "Base"

    cfg_keys = {configs[0]: "Cfg_1"}
    if len(configs) > 1:
        cfg_keys[configs[1]] = "Cfg_2"

    for cfg_name, cfg_key in cfg_keys.items():
        bc = ET.SubElement(ig, _ns("BuildConfiguration"))
        bc.set("Include", cfg_name)
        ET.SubElement(bc, _ns("Key")).text = cfg_key
        ET.SubElement(bc, _ns("CfgParent")).text = "Base"

    # ── ProjectExtensions ──
    pe = ET.SubElement(root, _ns("ProjectExtensions"))

    if is_pkg:
        # Package ProjectExtensions（参考 EurekaLogCore, VirtualTreesR）
        bp = ET.SubElement(pe, _ns("Borland.Personality"))
        bp.text = "Delphi.Personality.12"
        bpt = ET.SubElement(pe, _ns("Borland.ProjectType"))
        bpt.text = "Package"
        bproj = ET.SubElement(pe, _ns("BorlandProject"))
        dp = ET.SubElement(bproj, _ns("Delphi.Personality"))
        src_elem = ET.SubElement(dp, _ns("Source"))
        src_item = ET.SubElement(src_elem, _ns("Source"))
        src_item.set("Name", "MainSource")
        src_item.text = main_source
        if not old_format:
            deployment = ET.SubElement(bproj, _ns("Deployment"))
            plat_section = ET.SubElement(bproj, _ns("Platforms"))
            for p in platforms:
                p_node = ET.SubElement(plat_section, _ns("Platform"))
                p_node.set("value", p)
                p_node.text = "True"
        pe_version = ET.SubElement(pe, _ns("ProjectFileVersion"))
        pe_version.text = "12"

    # ── Import ──
    imp = ET.SubElement(root, _ns("Import"))
    imp.set("Project", "$(BDS)\\Bin\\CodeGear.Delphi.Targets")
    imp.set("Condition", "Exists('$(BDS)\\Bin\\CodeGear.Delphi.Targets')")

    imp_ut = ET.SubElement(root, _ns("Import"))
    imp_ut.set(
        "Project",
        "$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj",
    )
    imp_ut.set(
        "Condition",
        "Exists('$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj')",
    )

    if not is_pkg:
        imp_dp = ET.SubElement(root, _ns("Import"))
        imp_dp.set("Project", "$(MSBuildProjectName).deployproj")
        imp_dp.set("Condition", "Exists('$(MSBuildProjectName).deployproj')")

    tree = ET.ElementTree(root)
    tree.write(project_path, encoding="utf-8", xml_declaration=True)

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已创建 .dproj 文件: {project_path}\n"
                f"主源文件: {main_source}\n"
                f"项目类型: {resolved_app_type}\n"
                f"框架: {framework_type}\n"
                f"配置: {', '.join(configs)}\n"
                f"平台: {', '.join(platforms)}\n"
                f"源文件引用 ({len(sources or [])} 个): {', '.join(sources or [])}",
            )
        ],
        isError=False,
    )


def _compute_targeted_platforms_mask(platforms: List[str]) -> int:
    """计算 TargetedPlatforms 位掩码

    Delphi/MSBuild 定义：
      1=Win32, 2=Win64, 4=OSX32, 8=OSX64/arm64,
      16=iOSDevice32, 32=iOSDevice64, 64=iOSSimulator,
      128=Android, 256=Linux64
    """
    platform_bits = {
        "Win32": 1,
        "Win64": 2,
        "OSX32": 4,
        "OSX64": 8,
        "OSXarm64": 8,
        "iOSDevice32": 16,
        "iOSDevice64": 32,
        "iOSSimulator": 64,
        "Android": 128,
        "Android64": 128,
        "Linux64": 256,
    }
    mask = 0
    for p in platforms:
        bit = platform_bits.get(p, 1)
        mask |= bit
    return mask if mask else 1


async def _handle_info(project_path: str) -> CallToolResult:
    """读取 .dproj 文件完整信息"""
    parser = DprojParser(project_path)
    if not parser.parse():
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析 .dproj 失败: {project_path}")],
            isError=True,
        )

    info = parser.get_project_info()
    main_source = parser.get_main_source()
    platform = parser.get_target_platform()
    project_version = parser.get_project_version()
    search_paths = parser.get_unit_search_paths()
    conditional_defines = parser.get_conditional_defines()
    namespaces = parser.get_namespace()
    debugger_params = parser.get_debugger_run_params()
    build_events = parser.get_build_events()
    resources = parser.get_resource_items()

    # 读原始 XML 获取源文件列表
    tree = _parse(project_path)
    sources: List[str] = []
    if tree is not None:
        root = tree.getroot()
        for ig in root.findall(_ns("ItemGroup")):
            for ref in ig.findall(_ns("DCCReference")):
                inc = ref.get("Include", "")
                if inc:
                    sources.append(inc)
            for dc in ig.findall(_ns("DelphiCompile")):
                inc = dc.get("Include", "")
                if inc:
                    ms = dc.find(_ns("MainSource"))
                    tag = " [DelphiCompile]" + (f" → {ms.text}" if ms is not None else "")
                    sources.append(f"{inc}{tag}")

    # 每个配置有哪些 PropertyGroup
    tree2 = _parse(project_path)
    config_props: List[str] = []
    if tree2 is not None:
        for pg in tree2.getroot().findall(_ns("PropertyGroup")):
            cond = pg.get("Condition", "")
            if not cond:
                continue
            props = []
            for child in pg:
                tag = child.tag.split("}")[-1]
                props.append(f"{tag}={child.text or ''}")
            config_props.append(f"  [{cond}]")
            for p in props:
                config_props.append(f"    {p}")

    lines = [
        f"📄 项目文件: {project_path}",
        f"主源文件: {main_source or 'N/A'}",
        f"项目 GUID: {info.get('project_guid', 'N/A')}",
        f"项目版本: {project_version or 'N/A'}",
        f"框架类型: {info.get('framework_type', 'N/A')}",
        f"目标平台: {platform or 'N/A'}",
        "",
        "── 编译配置 ──",
    ]
    if config_props:
        lines.extend(config_props)
    else:
        lines.append("  (无条件编译配置)")

    lines.append("")
    lines.append(f"条件编译符号: {'; '.join(conditional_defines) if conditional_defines else '(无)'}")

    if search_paths:
        lines.append(f"单元搜索路径 ({len(search_paths)} 个):")
        for p in search_paths:
            lines.append(f"  - {p}")

    lines.append(f"命名空间: {namespaces or '(无)'}")
    lines.append(f"调试器参数: {debugger_params or '(无)'}")

    if build_events and any(v for v in build_events.values()):
        lines.append("")
        lines.append("── 编译事件 ──")
        event_labels = {
            "pre_build": "PreBuildEvent",
            "pre_link": "PreLinkEvent",
            "post_build": "PostBuildEvent",
        }
        for key, label in event_labels.items():
            val = build_events.get(key)
            if val:
                lines.append(f"  {label}: {val}")

    lines.append("")
    lines.append(f"── 源文件 ({len(sources)} 个) ──")
    for s in sources:
        lines.append(f"  {s}")

    if resources:
        lines.append("")
        lines.append(f"── 资源文件 ({len(resources)} 个) ──")
        for r in resources:
            lines.append(f"  {r.get('include')} → ID={r.get('resource_id')}, Type={r.get('resource_type')}")

    return CallToolResult(
        content=[TextContent(type="text", text="\n".join(lines))],
        isError=False,
    )


async def _handle_set(
    project_path: str,
    property_name: str,
    value: str,
    config: Optional[str] = None,
    platform: Optional[str] = None,
) -> CallToolResult:
    """设置 .dproj 属性值（创建元素或更新现有元素）"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件不存在: {project_path}")],
            isError=True,
        )

    result = _parse_tree(project_path)
    if result is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析失败: {project_path}")],
            isError=True,
        )
    tree, root = result

    backup_path = _backup_file(project_path)

    groups = _find_pg(root, config=config, platform=platform)

    changed = False
    if groups:
        for group in groups:
            elem = _find_or_create(group, property_name)
            elem.text = value
            changed = True
    else:
        # 匹配不到现有 PropertyGroup，创建一个新的
        cond_parts = []
        if config:
            cond_parts.append(f"'$(Config)'=='{config}'")
        if platform:
            cond_parts.append(f"'$(Platform)'=='{platform}'")
        new_pg = ET.SubElement(root, _ns("PropertyGroup"))
        new_pg.set("Condition", " and ".join(cond_parts))
        ET.SubElement(new_pg, _ns(property_name)).text = value
        changed = True

    if not changed:
        return CallToolResult(
            content=[TextContent(type="text", text="未做任何修改")],
            isError=False,
        )

    tree.write(project_path, encoding="utf-8", xml_declaration=True)

    loc = ""
    if config or platform:
        loc = f" (Config={config}, Platform={platform})"
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已设置 {property_name}={value}{loc}\n备份: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_add_config(
    project_path: str,
    config_name: str,
    base_config: Optional[str] = None,
    defines: Optional[str] = None,
    optimize: Optional[bool] = None,
    debug_info: Optional[bool] = None,
) -> CallToolResult:
    """添加编译配置"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件不存在: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析失败: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    if _find_pg(root, config=config_name):
        return CallToolResult(
            content=[TextContent(type="text", text=f"配置已存在: {config_name}")],
            isError=True,
        )

    backup_path = _backup_file(project_path)

    new_pg = ET.SubElement(root, _ns("PropertyGroup"))
    new_pg.set("Condition", f"'$(Config)'=='{config_name}'")

    set_count = 0

    # 如果有 base_config，复制其属性
    if base_config:
        base_groups = _find_pg(root, config=base_config)
        if base_groups:
            for child in base_groups[0]:
                tag_local = child.tag.split("}")[-1]
                ET.SubElement(new_pg, child.tag).text = child.text
                set_count += 1

    # 显式参数覆盖 base_config 的值
    if defines is not None:
        _find_or_create(new_pg, "DCC_Define").text = defines
        set_count += 1
    if optimize is not None:
        _find_or_create(new_pg, "DCC_Optimize").text = "true" if optimize else "false"
        set_count += 1
    if debug_info is not None:
        _find_or_create(new_pg, "DCC_DebugInfoInExe").text = "true" if debug_info else "false"
        set_count += 1

    tree.write(project_path, encoding="utf-8", xml_declaration=True)

    detail = f"从 {base_config} 复制" if base_config else f"默认设置"
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已添加配置: {config_name} ({detail}, {set_count} 个属性)\n备份: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_remove_config(project_path: str, config_name: str) -> CallToolResult:
    """删除编译配置"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件不存在: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析失败: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    groups = _find_pg(root, config=config_name)
    if not groups:
        return CallToolResult(
            content=[TextContent(type="text", text=f"未找到配置: {config_name}")],
            isError=True,
        )

    backup_path = _backup_file(project_path)
    for group in groups:
        root.remove(group)

    tree.write(project_path, encoding="utf-8", xml_declaration=True)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已删除配置: {config_name}\n备份: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_add_source(
    project_path: str,
    source_file: str,
    main_source: bool = False,
) -> CallToolResult:
    """添加源文件引用到 ItemGroup

    .dpr/.dpk 文件自动添加为 DelphiCompile，其他文件添加为 DCCReference。
    可通过 main_source=True 强制添加为 DelphiCompile。
    """
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件不存在: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析失败: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    ig = _find_or_create_item_group(root)
    backup_path = _backup_file(project_path)

    # 自动判断：.dpr/.dpk → DelphiCompile，其他 → DCCReference
    ext = Path(source_file).suffix.lower()
    is_delphi_main = main_source or ext in (".dpr", ".dpk")

    if is_delphi_main:
        # 检查是否已有 DelphiCompile
        existing_dc = ig.findall(_ns("DelphiCompile"))
        if existing_dc:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ 已存在 DelphiCompile 引用。一个项目只能有一个主源文件（.dpr/.dpk）。\n现有: {existing_dc[0].get('Include', '')}")],
                isError=True,
            )
        dc = ET.SubElement(ig, _ns("DelphiCompile"))
        dc.set("Include", source_file)
        ET.SubElement(dc, _ns("MainSource")).text = "MainSource"
        kind = "DelphiCompile"
        dpk_result = ""
    else:
        # 检查 DCCReference 是否已存在
        existing = _find_dcc_ref(ig, source_file)
        if existing:
            return CallToolResult(
                content=[TextContent(type="text", text=f"源文件已存在引用: {source_file}")],
                isError=True,
            )
        ref = ET.SubElement(ig, _ns("DCCReference"))
        ref.set("Include", source_file)
        kind = "DCCReference"

        # 同步 .dpk contains（如果是 Package 项目且添加的是 .pas）
        dpk_result = ""
        if ext == ".pas":
            try:
                dpk_path = _get_dpk_path_from_dproj(project_path)
                if dpk_path:
                    unit_name = Path(source_file).stem
                    dpk_backup = _dpk_add_contains(dpk_path, source_file, unit_name)
                    if dpk_backup:
                        dpk_result = f"\n✅ .dpk contains 已同步: {unit_name} in '{source_file}'"
                    else:
                        dpk_result = f"\nℹ️ .dpk contains 已存在该条目，跳过"
            except Exception as e:
                dpk_result = f"\n⚠️ .dpk contains 同步失败: {e}"

    tree.write(project_path, encoding="utf-8", xml_declaration=True)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已添加源文件引用 ({kind}): {source_file}\n备份: {backup_path}{dpk_result}",
            )
        ],
        isError=False,
    )


async def _handle_remove_source(project_path: str, source_file: str) -> CallToolResult:
    """从 ItemGroup 删除源文件引用"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"文件不存在: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"解析失败: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    backup_path = _backup_file(project_path)

    removed = False
    for ig in root.findall(_ns("ItemGroup")):
        ref = _find_dcc_ref(ig, source_file)
        if ref is not None:
            ig.remove(ref)
            removed = True

        # 也检查 DelphiCompile
        for dc in ig.findall(_ns("DelphiCompile")):
            inc = dc.get("Include", "")
            if inc and Path(inc).name.lower() == source_file.lower():
                ig.remove(dc)
                removed = True

    if not removed:
        return CallToolResult(
            content=[TextContent(type="text", text=f"未找到源文件引用: {source_file}")],
            isError=True,
        )

    tree.write(project_path, encoding="utf-8", xml_declaration=True)

    # 同步 .dpk contains（如果是 Package 项目）
    dpk_result = ""
    ext = Path(source_file).suffix.lower()
    if ext == ".pas":
        try:
            dpk_path = _get_dpk_path_from_dproj(project_path)
            if dpk_path:
                dpk_backup = _dpk_remove_contains(dpk_path, source_file)
                if dpk_backup:
                    dpk_result = f"\n✅ .dpk contains 已同步移除"
        except Exception as e:
            dpk_result = f"\n⚠️ .dpk contains 同步失败: {e}"

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ 已删除源文件引用: {source_file}\n备份: {backup_path}{dpk_result}",
            )
        ],
        isError=False,
    )


# ──────────────────────────────────────────────
# 公开入口
# ──────────────────────────────────────────────

async def dproj_tool(
    action: str = "info",
    project_path: Optional[str] = None,
    main_source: Optional[str] = None,
    project_guid: Optional[str] = None,
    project_version: str = "18.2",
    framework_type: str = "VCL",
    app_type: Optional[str] = None,
    unit_search_paths: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    configs: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    property_name: Optional[str] = None,
    value: Optional[str] = None,
    config: Optional[str] = None,
    platform: Optional[str] = None,
    config_name: Optional[str] = None,
    base_config: Optional[str] = None,
    defines: Optional[str] = None,
    optimize: Optional[bool] = None,
    debug_info: Optional[bool] = None,
    source_file: Optional[str] = None,
    main_source_flag: bool = False,
) -> CallToolResult:
    """.dproj 项目文件管理工具入口"""

    if not project_path and action in ("set", "add_config", "remove_config", "add_source", "remove_source"):
        return CallToolResult(
            content=[TextContent(type="text", text="❌ project_path 参数为必需")],
            isError=True,
        )
    if action == "create" and not project_path:
        return CallToolResult(
            content=[TextContent(type="text", text="❌ create 需要 project_path 参数")],
            isError=True,
        )

    handler_map = {
        "create": lambda: _handle_create(
            project_path=_require(project_path, "project_path"),
            main_source=_require(main_source, "main_source"),
            project_guid=project_guid,
            project_version=project_version,
            framework_type=framework_type,
            app_type=app_type,
            unit_search_paths=unit_search_paths,
            namespace=namespace,
            configs=configs,
            sources=sources,
            platforms=platforms,
        ),
        "info": lambda: _handle_info(project_path=project_path or ""),
        "set": lambda: _handle_set(
            project_path=_require(project_path, "project_path"),
            property_name=_require(property_name, "property_name"),
            value=_require(value, "value"),
            config=config,
            platform=platform,
        ),
        "add_config": lambda: _handle_add_config(
            project_path=_require(project_path, "project_path"),
            config_name=_require(config_name or config, "config_name"),
            base_config=base_config,
            defines=defines,
            optimize=optimize,
            debug_info=debug_info,
        ),
        "remove_config": lambda: _handle_remove_config(
            project_path=_require(project_path, "project_path"),
            config_name=_require(config_name or config, "config_name"),
        ),
        "add_source": lambda: _handle_add_source(
            project_path=_require(project_path, "project_path"),
            source_file=_require(source_file, "source_file"),
            main_source=main_source_flag,
        ),
        "remove_source": lambda: _handle_remove_source(
            project_path=_require(project_path, "project_path"),
            source_file=_require(source_file, "source_file"),
        ),
    }

    handler = handler_map.get(action)
    if handler:
        return await handler()

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"❌ 未知 action: {action}。可选: create, info, set, add_config, remove_config, add_source, remove_source",
            )
        ],
        isError=True,
    )
