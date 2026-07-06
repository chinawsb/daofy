"""
manage_component — 组件管理工具（增/删/改/生成 DFM + PAS 同步）

操作模式:
  create  生成组件 DFM（原 generate_component_dfm 功能，编译+运行序列化）
  add     向现有 DFM 添加子组件，同步 PAS 字段+事件+uses
  remove  从 DFM 删除组件（含子树），同步删除 PAS 字段+事件方法
  modify  修改 DFM 中组件属性，同步变更事件绑定时更新 PAS 声明

DFM↔PAS 同步规则:
  - add 时: 新字段声明 + 事件方法桩 + uses 单元
  - remove 时: 字段声明 + 事件方法(声明+实现) + 空引用的 uses
  - modify 时: 事件属性变更 → 增/删/改事件方法声明
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from ..utils.file_backup import detect_encoding

from .dfm_parser import (
    DfmComponent,
    DfmProperty,
    parse_dfm_text,
    serialize_component,
    collect_all_events,
    collect_all_units,
    resolve_event_params,
    is_event_property,
)
from .pas_decl_parser import (
    PasFieldDecl,
    PasMethodDecl,
    parse_pas_class,
    sync_pas_declarations,
)
from . import dfm_utils
from . import create_component_dfm as _gen_mod
from . import file_tool
from ..services.delphi_edit_guard import record_authorized_write
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def manage_component(
    action: str = "create",
    target_dfm: Optional[str] = None,
    target_pas: Optional[str] = None,
    component_name: Optional[str] = None,
    parent_name: Optional[str] = None,
    new_component_class: Optional[str] = None,
    new_component_name: Optional[str] = None,
    properties: Optional[Dict[str, str]] = None,
    dfm_text: Optional[str] = None,
    code: Optional[str] = None,
    uses: Optional[List[str]] = None,
    type_decl: str = "",
    init_code: str = "",
    compile_timeout: int = 60,
    exec_timeout: int = 15,
) -> Dict[str, Any]:
    if action == "create":
        return await _action_create(
            code=code or "", uses=uses, type_decl=type_decl,
            init_code=init_code, compile_timeout=compile_timeout,
            exec_timeout=exec_timeout,
        )
    elif action == "add":
        return await _action_add(
            target_dfm=target_dfm, target_pas=target_pas,
            parent_name=parent_name, new_component_class=new_component_class,
            new_component_name=new_component_name, properties=properties,
            dfm_text=dfm_text,
        )
    elif action == "remove":
        return await _action_remove(
            target_dfm=target_dfm, target_pas=target_pas,
            component_name=component_name,
        )
    elif action == "modify":
        return await _action_modify(
            target_dfm=target_dfm, target_pas=target_pas,
            component_name=component_name, properties=properties,
        )
    else:
        return {"status": "failed", "message": f"未知 action: {action}，支持 create/add/remove/modify"}


async def _action_create(
    code: str,
    uses: Optional[List[str]] = None,
    type_decl: str = "",
    init_code: str = "",
    compile_timeout: int = 60,
    exec_timeout: int = 15,
) -> Dict[str, Any]:
    result = await _gen_mod.generate_component_dfm(
        code=code, uses=uses, type_decl=type_decl,
        init_code=init_code, compile_timeout=compile_timeout,
        exec_timeout=exec_timeout,
    )
    if result.get("success"):
        return {
            "status": "success",
            "message": "组件 DFM 生成成功",
            "action": "create",
            "dfm_text": result["dfm_text"],
            "component_name": result.get("component_name", ""),
        }
    return {
        "status": "failed",
        "message": result.get("error", "生成失败"),
        "action": "create",
        "stage": result.get("stage", ""),
    }


async def _action_add(
    target_dfm: Optional[str],
    target_pas: Optional[str],
    parent_name: Optional[str],
    new_component_class: Optional[str],
    new_component_name: Optional[str],
    properties: Optional[Dict[str, str]],
    dfm_text: Optional[str],
) -> Dict[str, Any]:
    if not target_dfm:
        return {"status": "failed", "message": "add 操作需要 target_dfm 参数"}
    if not new_component_class and not dfm_text:
        return {"status": "failed", "message": "add 操作需要 new_component_class 或 dfm_text 参数"}

    existing_dfm = await _read_dfm_file(target_dfm)
    if existing_dfm is None:
        return {"status": "failed", "message": f"无法读取 DFM 文件: {target_dfm}"}

    root = parse_dfm_text(existing_dfm)
    if root is None:
        return {"status": "failed", "message": "DFM 解析失败"}

    if dfm_text:
        new_comp = parse_dfm_text(dfm_text)
        if new_comp is None:
            return {"status": "failed", "message": "dfm_text 解析失败"}
    else:
        comp_name = new_component_name or _generate_default_name(root, new_component_class)
        new_comp = DfmComponent(
            name=comp_name,
            class_name=new_component_class or "TComponent",
        )
        if properties:
            comp_class = new_component_class or "TComponent"
            for k, v in properties.items():
                new_comp.properties.append(DfmProperty(
                    name=k, raw_value=v, is_event=is_event_property(comp_class, k),
                ))

    if parent_name:
        parent = root.find_child(parent_name)
        if parent is None:
            return {"status": "failed", "message": f"未找到父组件: {parent_name}"}
    else:
        parent = root

    if parent.find_child(new_comp.name):
        return {"status": "failed", "message": f"组件名已存在: {new_comp.name}"}

    parent.children.append(new_comp)

    new_dfm_text = serialize_component(root)
    dfm_before = existing_dfm.count('\n')
    dfm_after = new_dfm_text.count('\n')

    pas_result = None
    if target_pas:
        pas_result = await _sync_pas_for_add(target_pas, new_comp, root)

    await _write_dfm_file(target_dfm, new_dfm_text, existing_dfm)

    return {
        "status": "success",
        "message": f"组件 {new_comp.name}({new_comp.class_name}) 已添加到 {parent.name}",
        "action": "add",
        "component_name": new_comp.name,
        "component_class": new_comp.class_name,
        "parent_name": parent.name,
        "dfm_text": new_dfm_text,
        "pas_sync": pas_result,
        "dfm_offset": dfm_after - dfm_before,
    }


async def _action_remove(
    target_dfm: Optional[str],
    target_pas: Optional[str],
    component_name: Optional[str],
) -> Dict[str, Any]:
    if not target_dfm:
        return {"status": "failed", "message": "remove 操作需要 target_dfm 参数"}
    if not component_name:
        return {"status": "failed", "message": "remove 操作需要 component_name 参数"}

    existing_dfm = await _read_dfm_file(target_dfm)
    if existing_dfm is None:
        return {"status": "failed", "message": f"无法读取 DFM 文件: {target_dfm}"}

    root = parse_dfm_text(existing_dfm)
    if root is None:
        return {"status": "failed", "message": "DFM 解析失败"}

    target = root.find_child(component_name)
    if target is None:
        if root.name == component_name:
            return {"status": "failed", "message": "不能删除根组件，请使用其他工具替换整个 DFM"}
        return {"status": "failed", "message": f"未找到组件: {component_name}"}

    removed_events = collect_all_events(target)
    removed_class = target.class_name
    removed_children = [c.name for c in target.all_components()[1:]]

    if not root.remove_child(component_name):
        return {"status": "failed", "message": f"删除组件失败: {component_name}"}

    new_dfm_text = serialize_component(root)
    dfm_before = existing_dfm.count('\n')
    dfm_after = new_dfm_text.count('\n')

    pas_result = None
    if target_pas:
        pas_result = _sync_pas_for_remove(target_pas, component_name, removed_events)

    await _write_dfm_file(target_dfm, new_dfm_text, existing_dfm)

    return {
        "status": "success",
        "message": f"组件 {component_name}({removed_class}) 已删除",
        "action": "remove",
        "component_name": component_name,
        "component_class": removed_class,
        "removed_children": removed_children,
        "removed_events": [(comp, evt, handler) for comp, evt, handler in removed_events],
        "dfm_text": new_dfm_text,
        "pas_sync": pas_result,
        "dfm_offset": dfm_after - dfm_before,
    }


async def _action_modify(
    target_dfm: Optional[str],
    target_pas: Optional[str],
    component_name: Optional[str],
    properties: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    if not target_dfm:
        return {"status": "failed", "message": "modify 操作需要 target_dfm 参数"}
    if not component_name:
        return {"status": "failed", "message": "modify 操作需要 component_name 参数"}
    if not properties:
        return {"status": "failed", "message": "modify 操作需要 properties 参数"}

    existing_dfm = await _read_dfm_file(target_dfm)
    if existing_dfm is None:
        return {"status": "failed", "message": f"无法读取 DFM 文件: {target_dfm}"}

    root = parse_dfm_text(existing_dfm)
    if root is None:
        return {"status": "failed", "message": "DFM 解析失败"}

    target = root.find_child(component_name)
    if target is None:
        if root.name == component_name:
            target = root
        else:
            return {"status": "failed", "message": f"未找到组件: {component_name}"}

    old_events = {p.name: p.value for p in target.get_events()}
    modified_props = []

    for prop_name, prop_value in properties.items():
        existing = target.get_property(prop_name)
        if existing:
            old_val = existing.raw_value
            existing.raw_value = prop_value
            existing.is_event = is_event_property(target.class_name, prop_name)
            modified_props.append({"name": prop_name, "old": old_val, "new": prop_value})
        else:
            new_prop = DfmProperty(
                name=prop_name, raw_value=prop_value,
                is_event=is_event_property(target.class_name, prop_name),
            )
            target.properties.append(new_prop)
            modified_props.append({"name": prop_name, "old": None, "new": prop_value})

    new_events = {p.name: p.value for p in target.get_events()}

    new_dfm_text = serialize_component(root)
    dfm_before = existing_dfm.count('\n')
    dfm_after = new_dfm_text.count('\n')

    pas_result = None
    if target_pas:
        pas_result = _sync_pas_for_modify(target_pas, old_events, new_events, component_name, target.class_name)

    await _write_dfm_file(target_dfm, new_dfm_text, existing_dfm)

    return {
        "status": "success",
        "message": f"组件 {component_name} 属性已修改",
        "action": "modify",
        "component_name": component_name,
        "modified_properties": modified_props,
        "dfm_text": new_dfm_text,
        "pas_sync": pas_result,
        "dfm_offset": dfm_after - dfm_before,
    }


async def _sync_pas_for_add(
    target_pas: str,
    new_comp: DfmComponent,
    root: DfmComponent,
) -> Optional[Dict[str, Any]]:
    enc = detect_encoding(target_pas)
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_text = f.read()
    except OSError as e:
        logger.warning("读取 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    add_fields = [PasFieldDecl(name=new_comp.name, type_name=new_comp.class_name)]
    for child in new_comp.children:
        add_fields.append(PasFieldDecl(name=child.name, type_name=child.class_name))

    add_methods = []
    for evt in new_comp.get_events():
        handler = evt.value
        if handler:
            params = resolve_event_params(new_comp.class_name, evt.name)
            add_methods.append(PasMethodDecl(
                name=handler, params=params, method_type="procedure",
            ))
    for child in new_comp.all_components()[1:]:
        for evt in child.get_events():
            handler = evt.value
            if handler:
                params = resolve_event_params(child.class_name, evt.name)
                add_methods.append(PasMethodDecl(
                    name=handler, params=params, method_type="procedure",
                ))

    new_pas = sync_pas_declarations(
        pas_text,
        add_fields=add_fields,
        add_methods=add_methods,
    )

    # 写入前行数，用于计算偏移量
    pas_before = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_before = sum(1 for _ in f)
    except OSError:
        pass

    try:
        record_authorized_write(
            target_pas,
            tool="manage_component",
            operation="sync_pas_add",
        )
        with open(target_pas, 'w', encoding=enc, newline='') as f:
            f.write(new_pas)
    except OSError as e:
        logger.warning("写入 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    # 重新计算 uses 添加后的行数（handle_uses 也会改变行数）
    pas_final = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_final = sum(1 for _ in f)
    except OSError:
        pass

    return {
        "status": "success",
        "message": "PAS 同步完成",
        "added_fields": [f.name for f in add_fields],
        "added_methods": [m.name for m in add_methods],
        "added_uses": added_units,
        "offset": pas_final - pas_before,
    }


def _sync_pas_for_remove(
    target_pas: str,
    component_name: str,
    removed_events: List[tuple],
) -> Optional[Dict[str, Any]]:
    enc = detect_encoding(target_pas)
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_text = f.read()
    except OSError as e:
        logger.warning("读取 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    remove_fields = [component_name]
    remove_methods = [handler for _, _, handler in removed_events]

    new_pas = sync_pas_declarations(
        pas_text,
        remove_fields=remove_fields,
        remove_methods=remove_methods if remove_methods else None,
    )

    pas_before = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_before = sum(1 for _ in f)
    except OSError:
        pass

    try:
        record_authorized_write(
            target_pas,
            tool="manage_component",
            operation="sync_pas_remove",
        )
        with open(target_pas, 'w', encoding=enc, newline='') as f:
            f.write(new_pas)
    except OSError as e:
        logger.warning("写入 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    pas_after = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_after = sum(1 for _ in f)
    except OSError:
        pass

    return {
        "status": "success",
        "message": "PAS 同步完成",
        "removed_fields": remove_fields,
        "removed_methods": remove_methods,
        "offset": pas_after - pas_before,
    }


def _sync_pas_for_modify(
    target_pas: str,
    old_events: Dict[str, str],
    new_events: Dict[str, str],
    component_name: str,
    class_name: str = "",
) -> Optional[Dict[str, Any]]:
    enc = detect_encoding(target_pas)
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_text = f.read()
    except OSError as e:
        logger.warning("读取 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    add_methods = []
    remove_methods = []

    for evt_name, new_handler in new_events.items():
        old_handler = old_events.get(evt_name)
        if old_handler != new_handler:
            if old_handler:
                remove_methods.append(old_handler)
            if new_handler:
                params = resolve_event_params(class_name, evt_name) if class_name else "Sender: TObject"
                add_methods.append(PasMethodDecl(
                    name=new_handler, params=params, method_type="procedure",
                ))

    for evt_name, old_handler in old_events.items():
        if evt_name not in new_events and old_handler:
            remove_methods.append(old_handler)

    if not add_methods and not remove_methods:
        return {"status": "success", "message": "无事件变更，PAS 无需同步"}

    new_pas = sync_pas_declarations(
        pas_text,
        add_methods=add_methods,
        remove_methods=remove_methods if remove_methods else None,
    )

    pas_before = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_before = sum(1 for _ in f)
    except OSError:
        pass

    try:
        record_authorized_write(
            target_pas,
            tool="manage_component",
            operation="sync_pas_modify",
        )
        with open(target_pas, 'w', encoding=enc, newline='') as f:
            f.write(new_pas)
    except OSError as e:
        logger.warning("写入 PAS 文件失败: %s", e)
        return {"status": "failed", "message": str(e)}

    pas_after = 0
    try:
        with open(target_pas, 'r', encoding=enc, newline='') as f:
            pas_after = sum(1 for _ in f)
    except OSError:
        pass

    return {
        "status": "success",
        "message": "PAS 同步完成",
        "added_methods": [m.name for m in add_methods],
        "removed_methods": remove_methods,
        "offset": pas_after - pas_before,
    }



def _generate_default_name(root: DfmComponent, class_name: str) -> str:
    prefix = class_name[1:] if class_name.startswith('T') else class_name
    existing_names = {c.name for c in root.all_components()}
    idx = 1
    while True:
        name = f"{prefix}{idx}"
        if name not in existing_names:
            return name
        idx += 1


async def _read_dfm_file(file_path: str) -> Optional[str]:
    try:
        text_path = await dfm_utils.ensure_dfm_text(file_path)
        if text_path is None:
            return None
        with open(text_path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        logger.warning("读取 DFM 文件失败: %s", e)
        return None


async def _write_dfm_file(file_path: str, new_text: str, original_text: str) -> None:
    try:
        fmt = dfm_utils._detect_dfm_format(file_path)
        if fmt == "binary":
            tmp_dir = os.path.dirname(file_path)
            tmp_text = os.path.join(tmp_dir, "_manage_tmp.dfmx")
            try:
                with open(tmp_text, 'w', encoding='utf-8') as f:
                    f.write(new_text)
                record_authorized_write(
                    file_path,
                    tool="manage_component",
                    operation="write_dfm",
                )
                await dfm_utils.convert_dfm(tmp_text, file_path, to_text=False)
            finally:
                if os.path.isfile(tmp_text):
                    os.remove(tmp_text)
        else:
            record_authorized_write(
                file_path,
                tool="manage_component",
                operation="write_dfm",
            )
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_text)
    except OSError as e:
        logger.error("写入 DFM 文件失败: %s", e)
