"""Static DFM layout audit helpers.

The audit is intentionally conservative: it only inspects design-time
coordinates and reports structural layout risks that are visible in DFM data.
Runtime DPI validation still belongs to automate_delphi + OCR/UIA checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Optional

from mcp.types import CallToolResult, TextContent

from .dfm_parser import DfmComponent, parse_dfm_text
from .dfm_utils import ensure_dfm_text


ALIGN_TOLERANCE = 3
GAP_TOLERANCE = 4
OVERLAP_TOLERANCE = 2
LABEL_FIELD_MIN_GAP = 4
LABEL_FIELD_MAX_GAP = 16
FIXED_BORDER_STYLES = {
    "bsdialog",
    "bsnone",
    "bssingle",
    "bstoolwindow",
    "dialog",
    "none",
    "single",
    "toolwindow",
}
HORIZONTAL_ALIGNMENTS = {
    "albottom",
    "alclient",
    "alcontents",
    "alcustom",
    "alscale",
    "altop",
    "bottom",
    "client",
    "contents",
    "custom",
    "scale",
    "top",
}
VERTICAL_ALIGNMENTS = {
    "alclient",
    "alcontents",
    "alcustom",
    "alleft",
    "alright",
    "alscale",
    "client",
    "contents",
    "custom",
    "left",
    "right",
    "scale",
}


@dataclass(frozen=True)
class LayoutRect:
    """Control bounds in parent-client coordinates."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2)


@dataclass(frozen=True)
class LayoutControl:
    """Flattened visual control from a DFM component tree."""

    name: str
    class_name: str
    rect: LayoutRect
    parent_name: str
    parent_class: str
    depth: int
    tab_order: Optional[int]
    tab_stop: Optional[bool]
    anchors: set[str]
    align: str
    has_display_text: bool
    has_visual_children: bool


@dataclass(frozen=True)
class LayoutFinding:
    """One static layout finding."""

    severity: str
    rule_id: str
    file: str
    component: str
    message: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "file": self.file,
            "component": self.component,
            "message": self.message,
            "recommendation": self.recommendation,
        }


def _property_value(component: DfmComponent, name: str) -> Optional[str]:
    prop = component.get_property(name)
    if prop is None:
        return None
    return prop.value.strip()


def _int_property(component: DfmComponent, name: str) -> Optional[int]:
    value = _property_value(component, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _bool_property(component: DfmComponent, name: str, default: bool = True) -> bool:
    value = _property_value(component, name)
    if value is None:
        return default
    return value.lower() not in {"false", "0"}


def _optional_bool_property(component: DfmComponent, name: str) -> Optional[bool]:
    value = _property_value(component, name)
    if value is None:
        return None
    return value.lower() not in {"false", "0"}


def _set_property(component: DfmComponent, name: str) -> set[str]:
    value = _property_value(component, name)
    if not value:
        return set()
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return set()
    return {item.strip() for item in value[1:-1].split(",") if item.strip()}


def _align_property(component: DfmComponent) -> str:
    return (_property_value(component, "Align") or "alNone").strip()


def _normalized_enum(value: str) -> str:
    return value.rsplit(".", 1)[-1].strip().lower()


def _component_rect(component: DfmComponent, is_root: bool = False) -> Optional[LayoutRect]:
    left = _int_property(component, "Left")
    top = _int_property(component, "Top")
    width = _int_property(component, "Width")
    height = _int_property(component, "Height")

    if width is None:
        width = _int_property(component, "ClientWidth")
    if height is None:
        height = _int_property(component, "ClientHeight")
    if left is None:
        left = 0 if is_root else None
    if top is None:
        top = 0 if is_root else None

    if left is None or top is None or width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    return LayoutRect(left=left, top=top, width=width, height=height)


def _is_visual_component(component: DfmComponent) -> bool:
    return _component_rect(component) is not None


def _has_display_text(component: DfmComponent) -> bool:
    for prop_name in ("Caption", "Text", "Title", "Hint"):
        value = _property_value(component, prop_name)
        if value and value not in {"''", '""'}:
            return True
    return False


def _has_visual_children(component: DfmComponent) -> bool:
    return any(_is_visual_component(child) for child in component.children)


def _is_manual_layout(control: LayoutControl) -> bool:
    return _normalized_enum(control.align) in {"", "alnone", "none"}


def _axis_is_fixed_by_constraints(component: DfmComponent, dimension: str) -> bool:
    minimum = _int_property(component, f"Constraints.Min{dimension}")
    maximum = _int_property(component, f"Constraints.Max{dimension}")
    return minimum is not None and minimum > 0 and maximum == minimum


def _root_resize_axes(root: DfmComponent) -> tuple[bool, bool]:
    border_style = _normalized_enum(_property_value(root, "BorderStyle") or "bsSizeable")
    if border_style in FIXED_BORDER_STYLES:
        return False, False
    return (
        not _axis_is_fixed_by_constraints(root, "Width"),
        not _axis_is_fixed_by_constraints(root, "Height"),
    )


def _child_resize_axes(
    component: DfmComponent,
    parent_axes: tuple[bool, bool],
) -> tuple[bool, bool]:
    align = _normalized_enum(_align_property(component))
    anchors = {_normalized_enum(item) for item in _set_property(component, "Anchors")}
    stretches_horizontally = align in HORIZONTAL_ALIGNMENTS or (
        bool({"akleft", "left"} & anchors) and bool({"akright", "right"} & anchors)
    )
    stretches_vertically = align in VERTICAL_ALIGNMENTS or (
        bool({"aktop", "top"} & anchors) and bool({"akbottom", "bottom"} & anchors)
    )
    return (
        parent_axes[0]
        and stretches_horizontally
        and not _axis_is_fixed_by_constraints(component, "Width"),
        parent_axes[1]
        and stretches_vertically
        and not _axis_is_fixed_by_constraints(component, "Height"),
    )


def _resize_axes_by_parent(root: DfmComponent) -> dict[str, tuple[bool, bool]]:
    axes_by_parent: dict[str, tuple[bool, bool]] = {}

    def visit(component: DfmComponent, axes: tuple[bool, bool]) -> None:
        axes_by_parent[component.name] = axes
        for child in component.children:
            visit(child, _child_resize_axes(child, axes))

    visit(root, _root_resize_axes(root))
    return axes_by_parent


def _is_passive_text(control: LayoutControl) -> bool:
    """Return True for visual text that behaves like a label.

    This is property-driven rather than class-name-driven. A control with text
    and no focus order is treated as a label candidate, including custom label
    controls and framework-specific static text widgets.
    """
    if control.has_visual_children:
        return False
    if control.tab_stop is False:
        return True
    if control.tab_order is not None:
        return False
    return control.has_display_text or (control.rect.height <= 32 and control.rect.width <= 240)


def _is_content_control(control: LayoutControl) -> bool:
    """Return True for a geometry-relevant leaf control.

    The check intentionally avoids fixed class names. If a control has design
    bounds and is not passive text or a container, it participates in column,
    spacing, field-pairing, and tab-order analysis.
    """
    if control.has_visual_children or _is_passive_text(control):
        return False
    if control.rect.width <= OVERLAP_TOLERANCE or control.rect.height <= OVERLAP_TOLERANCE:
        return False
    return True


def _children_by_parent(root: DfmComponent) -> dict[str, list[LayoutControl]]:
    groups: dict[str, list[LayoutControl]] = {}

    def visit(component: DfmComponent, depth: int) -> None:
        children: list[LayoutControl] = []
        for child in component.children:
            if _bool_property(child, "Visible", default=True) and _is_visual_component(child):
                rect = _component_rect(child)
                if rect is not None:
                    children.append(
                        LayoutControl(
                            name=child.name,
                            class_name=child.class_name,
                            rect=rect,
                            parent_name=component.name,
                            parent_class=component.class_name,
                            depth=depth + 1,
                            tab_order=_int_property(child, "TabOrder"),
                            tab_stop=_optional_bool_property(child, "TabStop"),
                            anchors=_set_property(child, "Anchors"),
                            align=_align_property(child),
                            has_display_text=_has_display_text(child),
                            has_visual_children=_has_visual_children(child),
                        )
                    )
            visit(child, depth + 1)
        if children:
            groups[component.name] = children

    visit(root, 0)
    return groups


def _intersects(a: LayoutRect, b: LayoutRect) -> bool:
    overlap_x = min(a.right, b.right) - max(a.left, b.left)
    overlap_y = min(a.bottom, b.bottom) - max(a.top, b.top)
    return overlap_x > OVERLAP_TOLERANCE and overlap_y > OVERLAP_TOLERANCE


def _cluster_by_left(controls: Iterable[LayoutControl]) -> list[list[LayoutControl]]:
    sorted_controls = sorted(controls, key=lambda item: item.rect.left)
    clusters: list[list[LayoutControl]] = []
    for control in sorted_controls:
        if not clusters:
            clusters.append([control])
            continue
        current = clusters[-1]
        current_left = median([item.rect.left for item in current])
        if abs(control.rect.left - current_left) <= 24:
            current.append(control)
        else:
            clusters.append([control])
    return clusters


def _format_control(control: LayoutControl) -> str:
    r = control.rect
    return (
        f"{control.name}({control.class_name}) "
        f"[Left={r.left}, Top={r.top}, Width={r.width}, Height={r.height}]"
    )


def _audit_overlap(file_path: str, siblings: list[LayoutControl]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    manual = [item for item in siblings if _is_manual_layout(item)]
    for index, first in enumerate(manual):
        for second in manual[index + 1:]:
            if _intersects(first.rect, second.rect):
                findings.append(
                    LayoutFinding(
                        severity="critical",
                        rule_id="LAYOUT-001",
                        file=file_path,
                        component=f"{first.parent_name}/{first.name},{second.name}",
                        message=f"同一容器内控件重叠: {_format_control(first)} 与 {_format_control(second)}。",
                        recommendation="调整 Left/Top/Width/Height，或使用 Panel/Align 将两个区域分开。",
                    )
                )
    return findings


def _audit_parent_bounds(
    file_path: str,
    parent: DfmComponent,
    siblings: list[LayoutControl],
) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    parent_rect = _component_rect(parent, is_root=True)
    if parent_rect is None:
        return findings
    for control in siblings:
        if not _is_manual_layout(control):
            continue
        r = control.rect
        outside = (
            r.left < -OVERLAP_TOLERANCE
            or r.top < -OVERLAP_TOLERANCE
            or r.right > parent_rect.width + OVERLAP_TOLERANCE
            or r.bottom > parent_rect.height + OVERLAP_TOLERANCE
        )
        if outside:
            findings.append(
                LayoutFinding(
                    severity="critical",
                    rule_id="LAYOUT-002",
                    file=file_path,
                    component=f"{parent.name}/{control.name}",
                    message=(
                        f"控件超出父容器边界: {_format_control(control)}，"
                        f"父容器大小 Width={parent_rect.width}, Height={parent_rect.height}。"
                    ),
                    recommendation="缩小控件、调整边距，或启用合适的 Align/Anchors/ScrollBox。",
                )
            )
    return findings


def _audit_column_alignment(file_path: str, siblings: list[LayoutControl]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    content_controls = [item for item in siblings if _is_content_control(item) and _is_manual_layout(item)]
    for cluster in _cluster_by_left(content_controls):
        if len(cluster) < 3:
            continue
        lefts = [item.rect.left for item in cluster]
        spread = max(lefts) - min(lefts)
        if spread > ALIGN_TOLERANCE:
            names = ", ".join(item.name for item in sorted(cluster, key=lambda item: item.rect.top))
            findings.append(
                LayoutFinding(
                    severity="warning",
                    rule_id="LAYOUT-003",
                    file=file_path,
                    component=cluster[0].parent_name,
                    message=f"同列内容控件 Left 不一致，偏差 {spread}px: {names}。",
                    recommendation=f"将同列内容控件 Left 统一到同一值，建议偏差不超过 {ALIGN_TOLERANCE}px。",
                )
            )
    return findings


def _audit_vertical_gaps(file_path: str, siblings: list[LayoutControl]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    content_controls = [item for item in siblings if _is_content_control(item) and _is_manual_layout(item)]
    for cluster in _cluster_by_left(content_controls):
        ordered = sorted(cluster, key=lambda item: item.rect.top)
        if len(ordered) < 4:
            continue
        gaps: list[int] = []
        for first, second in zip(ordered, ordered[1:]):
            gap = second.rect.top - first.rect.bottom
            if 0 <= gap <= 48:
                gaps.append(gap)
        if len(gaps) < 3:
            continue
        spread = max(gaps) - min(gaps)
        if spread > GAP_TOLERANCE:
            findings.append(
                LayoutFinding(
                    severity="suggestion",
                    rule_id="LAYOUT-004",
                    file=file_path,
                    component=ordered[0].parent_name,
                    message=f"同列内容控件垂直间距不一致: {gaps}，偏差 {spread}px。",
                    recommendation=f"使用统一间距，建议按 8px 基准网格组织，偏差不超过 {GAP_TOLERANCE}px。",
                )
            )
    return findings


def _nearest_field(label: LayoutControl, candidates: list[LayoutControl]) -> Optional[LayoutControl]:
    right_side = [
        item
        for item in candidates
        if item.rect.left >= label.rect.right - OVERLAP_TOLERANCE
        and abs(item.rect.center_y - label.rect.center_y) <= max(label.rect.height, item.rect.height)
    ]
    if not right_side:
        return None
    return min(
        right_side,
        key=lambda item: (
            abs(item.rect.center_y - label.rect.center_y),
            item.rect.left - label.rect.right,
        ),
    )


def _audit_label_fields(file_path: str, siblings: list[LayoutControl]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    labels = [item for item in siblings if _is_passive_text(item) and _is_manual_layout(item)]
    fields = [item for item in siblings if _is_content_control(item) and _is_manual_layout(item)]
    for label in labels:
        field = _nearest_field(label, fields)
        if field is None:
            continue
        center_delta = abs(field.rect.center_y - label.rect.center_y)
        gap = field.rect.left - label.rect.right
        if center_delta > ALIGN_TOLERANCE:
            findings.append(
                LayoutFinding(
                    severity="warning",
                    rule_id="LAYOUT-005",
                    file=file_path,
                    component=f"{label.parent_name}/{label.name},{field.name}",
                    message=f"文本标签与字段垂直中心未对齐，偏差 {center_delta:.1f}px。",
                    recommendation=f"调整文本标签 Top 或字段 Top，使中心线偏差不超过 {ALIGN_TOLERANCE}px。",
                )
            )
        if gap < LABEL_FIELD_MIN_GAP or gap > LABEL_FIELD_MAX_GAP:
            findings.append(
                LayoutFinding(
                    severity="suggestion",
                    rule_id="LAYOUT-006",
                    file=file_path,
                    component=f"{label.parent_name}/{label.name},{field.name}",
                    message=f"文本标签与字段水平间距为 {gap}px，建议范围 {LABEL_FIELD_MIN_GAP}~{LABEL_FIELD_MAX_GAP}px。",
                    recommendation="统一文本标签右边缘到字段左边缘的间距，避免过挤或断裂。",
                )
            )
    return findings


def _visual_order_key(control: LayoutControl) -> tuple[int, int, str]:
    row = round(control.rect.top / 8)
    return row, control.rect.left, control.name


def _audit_tab_order(file_path: str, siblings: list[LayoutControl]) -> list[LayoutFinding]:
    tab_controls = [
        item
        for item in siblings
        if item.tab_order is not None and _is_manual_layout(item) and _is_content_control(item)
    ]
    if len(tab_controls) < 3:
        return []
    by_visual = [item.name for item in sorted(tab_controls, key=_visual_order_key)]
    by_tab = [item.name for item in sorted(tab_controls, key=lambda item: item.tab_order or 0)]
    if by_visual == by_tab:
        return []
    return [
        LayoutFinding(
            severity="suggestion",
            rule_id="LAYOUT-007",
            file=file_path,
            component=tab_controls[0].parent_name,
            message=f"TabOrder 与视觉阅读顺序不一致。视觉顺序: {by_visual}; Tab 顺序: {by_tab}。",
            recommendation="按从上到下、从左到右的视觉顺序重新设置 TabOrder。",
        )
    ]


def _audit_resizable_manual_layout(
    file_path: str,
    parent: DfmComponent,
    siblings: list[LayoutControl],
    resize_axes: tuple[bool, bool],
) -> list[LayoutFinding]:
    manual = [item for item in siblings if _is_manual_layout(item)]
    if not manual or not any(resize_axes):
        return []

    required_width = max(item.rect.right for item in manual)
    required_height = max(item.rect.bottom for item in manual)
    min_width = _int_property(parent, "Constraints.MinWidth") or 0
    min_height = _int_property(parent, "Constraints.MinHeight") or 0

    missing_constraints: list[str] = []
    if resize_axes[0] and min_width < required_width:
        missing_constraints.append(f"MinWidth={min_width}（至少需要 {required_width}）")
    if resize_axes[1] and min_height < required_height:
        missing_constraints.append(f"MinHeight={min_height}（至少需要 {required_height}）")
    if not missing_constraints:
        return []

    control_names = ", ".join(item.name for item in manual[:8])
    if len(manual) > 8:
        control_names += f" 等 {len(manual)} 个控件"
    constraint_text = "，".join(missing_constraints)
    return [
        LayoutFinding(
            severity="warning",
            rule_id="LAYOUT-008",
            file=file_path,
            component=parent.name,
            message=(
                f"可调整大小的父容器内使用了绝对坐标布局: {control_names}；"
                f"父容器最小尺寸不足，{constraint_text}，缩小窗口时内容可能溢出。"
            ),
            recommendation=(
                "优先使用 Align 和分区容器组织布局；若必须保留绝对坐标，"
                "请按手工布局内容边界设置父容器的 Constraints.MinWidth/MinHeight。"
            ),
        )
    ]


def _find_component(root: DfmComponent, name: str) -> Optional[DfmComponent]:
    if root.name == name:
        return root
    return root.find_child(name)


def audit_dfm_layout_text(text: str, file_path: str = "<memory>") -> list[LayoutFinding]:
    """Audit one textual DFM payload and return static layout findings."""
    root = parse_dfm_text(text)
    if root is None:
        return [
            LayoutFinding(
                severity="critical",
                rule_id="LAYOUT-000",
                file=file_path,
                component="DFM",
                message="无法解析 DFM 文本。",
                recommendation="确认 DFM 为 Delphi 文本格式，或先转换二进制 DFM。",
            )
        ]

    findings: list[LayoutFinding] = []
    children_by_parent = _children_by_parent(root)
    resize_axes_by_parent = _resize_axes_by_parent(root)
    for parent_name, siblings in children_by_parent.items():
        parent = _find_component(root, parent_name)
        if parent is None:
            continue
        findings.extend(_audit_overlap(file_path, siblings))
        findings.extend(_audit_parent_bounds(file_path, parent, siblings))
        findings.extend(_audit_column_alignment(file_path, siblings))
        findings.extend(_audit_vertical_gaps(file_path, siblings))
        findings.extend(_audit_label_fields(file_path, siblings))
        findings.extend(_audit_tab_order(file_path, siblings))
        findings.extend(
            _audit_resizable_manual_layout(
                file_path,
                parent,
                siblings,
                resize_axes_by_parent.get(parent_name, (False, False)),
            )
        )

    return findings


async def _audit_dfm_file(path: Path) -> list[LayoutFinding]:
    text_path = await ensure_dfm_text(str(path))
    if text_path is None:
        return [
            LayoutFinding(
                severity="critical",
                rule_id="LAYOUT-000",
                file=str(path),
                component="DFM",
                message="无法读取或转换 DFM 文件。",
                recommendation="确认文件存在且 Delphi 编译器可用于二进制 DFM 转换。",
            )
        ]
    text = Path(text_path).read_text(encoding="utf-8-sig", errors="replace")
    return audit_dfm_layout_text(text, str(path))


def _severity_counts(findings: list[LayoutFinding]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "suggestion": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def _format_layout_report(findings: list[LayoutFinding], scanned_files: list[str]) -> str:
    counts = _severity_counts(findings)
    lines = ["# UI 布局审计报告", ""]
    lines.append(f"**扫描 DFM 文件数**: {len(scanned_files)}")
    lines.append(f"**发现总数**: {len(findings)}")
    lines.append("")
    lines.append("| 级别 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 严重 | {counts.get('critical', 0)} |")
    lines.append(f"| 一般 | {counts.get('warning', 0)} |")
    lines.append(f"| 建议 | {counts.get('suggestion', 0)} |")
    lines.append("")

    if not findings:
        lines.append("## 结果")
        lines.append("")
        lines.append("未发现明显的静态布局问题。建议继续用 `automate_delphi` 采集运行时 BoundsRect，并在 100%/125%/150% DPI 下做截图或 OCR 验证。")
        return "\n".join(lines)

    labels = {
        "critical": "严重",
        "warning": "一般",
        "suggestion": "建议",
    }
    for severity in ("critical", "warning", "suggestion"):
        items = [item for item in findings if item.severity == severity]
        if not items:
            continue
        lines.append(f"## {labels[severity]}问题 ({len(items)} 项)")
        lines.append("")
        for item in items:
            lines.append(f"- **[{item.rule_id}] `{item.file}` `{item.component}`**")
            lines.append(f"  - 问题: {item.message}")
            lines.append(f"  - 建议: {item.recommendation}")
            lines.append("")

    return "\n".join(lines)


async def run_layout_audit(arguments: dict[str, Any]) -> CallToolResult:
    """Run static UI layout audit over DFM files."""
    base_dir = str(arguments.get("base_dir", "") or "").strip()
    file_path = str(arguments.get("file_path", "") or "").strip()
    output_format = str(arguments.get("output_format", "report") or "report")

    if not base_dir and not file_path:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        "# 参数错误\n\n"
                        "layout 模式需要 `base_dir` 或 `file_path` 参数。\n\n"
                        '示例: `delphi_project(action="layout", base_dir="src")`'
                    ),
                )
            ],
            isError=True,
        )

    paths: list[Path] = []
    if file_path:
        candidate = Path(file_path)
        if not candidate.exists():
            return CallToolResult(
                content=[TextContent(type="text", text=f"# 文件不存在\n\n`{file_path}` 不存在，请检查路径。")],
                isError=True,
            )
        paths.append(candidate)
    else:
        base = Path(base_dir)
        if not base.exists():
            return CallToolResult(
                content=[TextContent(type="text", text=f"# 路径不存在\n\n`{base_dir}` 不存在，请检查路径。")],
                isError=True,
            )
        paths.extend(sorted(base.rglob("*.dfm")))

    if not paths:
        return CallToolResult(
            content=[TextContent(type="text", text=f"# UI 布局审计报告\n\n在 `{base_dir or file_path}` 中未找到 .dfm 文件。")]
        )

    findings: list[LayoutFinding] = []
    scanned_files: list[str] = []
    for path in paths:
        scanned_files.append(str(path))
        findings.extend(await _audit_dfm_file(path))

    if output_format == "json":
        payload = {
            "scanned_files": scanned_files,
            "summary": {
                "total": len(findings),
                **_severity_counts(findings),
            },
            "findings": [item.to_dict() for item in findings],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = _format_layout_report(findings, scanned_files)
    return CallToolResult(content=[TextContent(type="text", text=text)])
