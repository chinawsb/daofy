# Manage Component — DFM 组件管理

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Create — 生成组件 DFM](#3-create--生成组件-dfm)
4. [Add — 添加组件](#4-add--添加组件)
5. [Remove — 删除组件](#5-remove--删除组件)
6. [Modify — 修改组件属性](#6-modify--修改组件属性)
7. [PAS 自动同步机制](#7-pas-自动同步机制)
8. [技术架构](#8-技术架构)
9. [故障排除](#9-故障排除)

---

## 1. 概述

`manage_component` 是 Delphi DFM 组件管理的**一体化工具**，支持组件的创建、添加、删除和属性修改，并**自动同步 PAS 文件**中的字段声明和事件方法代码。

合并自原有的 `generate_component_dfm` 功能，并在此基础上增加了 `add`/`remove`/`modify` 三个操作。

| 功能 | 说明 |
|------|------|
| 创建组件 DFM | 编译运行 Pascal 代码，序列化为 DFM 文本 |
| 添加子组件 | 向现有 DFM 添加组件，自动同步 PAS |
| 删除组件 | 从 DFM 删除组件树，自动清理 PAS |
| 修改属性 | 修改组件属性，事件变更时同步 PAS |

---

## 2. Action 速查

| Action | 用途 | 必需参数 |
|--------|------|---------|
| `create` | 生成组件 DFM（编译+运行序列化） | `code` |
| `add` | 向现有 DFM 添加子组件 | `target_dfm`, `new_component_class` |
| `remove` | 从 DFM 删除组件 | `target_dfm`, `component_name` |
| `modify` | 修改组件属性 | `target_dfm`, `component_name`, `properties` |

---

## 3. Create — 生成组件 DFM

编译一段 Pascal 代码并运行，将其创建的可视组件序列化为 DFM 文本。适用于需要精确控制组件布局的场景。

```python
# 生成一个带 OK 按钮的面板
manage_component(action="create",
    code="""
function CreateComponent(AOwner: TComponent): TComponent;
var
  Panel: TPanel;
  Btn: TButton;
begin
  Panel := TPanel.Create(AOwner);
  Panel.Caption := '';
  Panel.Width := 300;
  Panel.Height := 200;

  Btn := TButton.Create(Panel);
  Btn.Parent := Panel;
  Btn.Caption := 'OK';
  Btn.Left := 100;
  Btn.Top := 80;
  Btn.Width := 100;
  Btn.Height := 30;

  Result := Panel;
end;
""",
    uses=["Vcl.ExtCtrls", "Vcl.StdCtrls"],
    compile_timeout=60,
    exec_timeout=15)
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `code` | ✅ | — | Pascal 代码，必须包含 `function CreateComponent(AOwner: TComponent): TComponent;` |
| `uses` | ❌ | — | 需要引用的单元列表 |
| `type_decl` | ❌ | — | 类型声明段（如 Form 类声明、事件桩等） |
| `init_code` | ❌ | — | 初始化代码，在 CreateComponent 前执行。自定义 Form 类需 `RegisterClass` |
| `compile_timeout` | ❌ | 60 | 编译超时秒数 |
| `exec_timeout` | ❌ | 15 | 执行超时秒数 |

---

## 4. Add — 添加组件

向现有的 DFM 文件添加子组件，自动同步到对应的 PAS 文件。

```python
# 添加按钮到根组件
manage_component(action="add",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    new_component_class="TButton",
    new_component_name="BtnOK",
    properties={
        "Caption": "确定",
        "Left": "100",
        "Top": "80",
        "Width": "100",
        "Height": "30",
        "OnClick": "BtnOKClick"   # 自动生成事件桩
    })

# 添加到指定父组件
manage_component(action="add",
    target_dfm="Unit1.dfm",
    parent_name="Panel1",
    new_component_class="TEdit",
    new_component_name="EditName",
    properties={"Text": "", "Left": "10", "Top": "10"})

# 使用 DFM 文本片段
manage_component(action="add",
    target_dfm="Unit1.dfm",
    dfm_text="object BtnOK: TButton\n  Caption = 'OK'\n  Left = 100\n  Top = 80\nend")
```

**参数说明**：

| 参数 | 必需 | 说明 |
|------|------|------|
| `target_dfm` | ✅ | 目标 DFM 文件路径 |
| `target_pas` | ❌ | PAS 文件路径，用于自动同步声明 |
| `parent_name` | ❌ | 父组件名称，不传则添加到根组件 |
| `new_component_class` | ❌ | 组件类名（如 TButton） |
| `new_component_name` | ❌ | 实例名，不传则自动生成 |
| `properties` | ❌ | 属性字典 |
| `dfm_text` | ❌ | DFM 文本片段（替代 class+properties） |

---

## 5. Remove — 删除组件

从 DFM 删除组件及其子树，自动清理 PAS 中的字段声明和事件方法。

```python
# 删除组件
manage_component(action="remove",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnCancel")
```

**删除时自动同步**：
| PAS 中的内容 | 处理方式 |
|-------------|---------|
| 字段声明（`BtnCancel: TButton;`） | 删除 |
| 事件方法声明（`procedure BtnCancelClick(Sender: TObject);`） | 删除 |
| 事件方法实现 | 删除 |
| 空引用的 uses 单元 | 清理 |

---

## 6. Modify — 修改组件属性

修改 DFM 中现有组件的属性。当涉及事件属性变更时（如修改 `OnClick` 事件绑定），自动同步 PAS 中的事件方法声明。

```python
# 修改 Caption 和字体
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={
        "Caption": "确认",
        "Font.Size": "12",
        "OnClick": "BtnOKClick"  # 自动生成/更新事件桩
    })
```

**PAS 同步规则**：

| 事件变更 | PAS 处理 |
|---------|---------|
| 新增事件绑定 | 自动生成方法声明 + 实现桩 |
| 修改事件绑定 | 保留原方法，生成新方法 |
| 移除事件绑定 | 保留方法代码（需人工确认是否删除） |

---

## 7. PAS 自动同步机制

这是 `manage_component` 的核心能力——DFM 和 PAS 双向同步。

### 同步规则

| 操作 | DFM | PAS |
|------|-----|-----|
| **add** | 插入组件定义 | + 字段声明 + 事件方法桩 + 所需 uses 单元 |
| **remove** | 删除组件（含子树） | - 字段声明 - 事件方法(声明+实现) - 空引用的 uses |
| **modify** 事件变更 | 修改事件属性 | +/— 事件方法声明 |

### 同步工作流

```
manage_component(action="add", target_dfm="Unit1.dfm", ...)
    │
    ├─ ① 读取 DFM → 解析组件树
    ├─ ② 插入新组件定义
    ├─ ③ 更新 DFM 文件（自动备份到 __history）
    │
    ├─ ④ 读取 PAS → 解析字段/方法区
    ├─ ⑤ 添加字段声明（FComponentName: TComponentClass;）
    ├─ ⑥ 添加事件方法声明（procedure ComponentNameEvent(Sender: TObject);）
    ├─ ⑦ 添加事件方法实现桩
    ├─ ⑧ 补充缺失的 uses 单元
    └─ ⑨ 更新 PAS 文件（自动备份到 __history）
```

---

## 8. 技术架构

```
AI Agent
    │
    ▼
manage_component(action="create"|"add"|"remove"|"modify")
    │
    ▼
┌───────────────────────────────────────────────┐
│         src/tools/manage_component.py           │
│  · 组件操作 + PAS 同步 核心逻辑                  │
│  · DFM 解析/生成                               │
│  · 事件签名匹配（借助 KB 服务）                  │
└──────┬──────────┬──────────┬───────────────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│  DFM     │ │  PAS     │ │ 编译器   │
│  解析    │ │  同步    │ │  (create)│
├──────────┤ ├──────────┤ ├──────────┤
│· 组件树  │ │· 字段    │ │· dcc32  │
│· 属性解析│ │· 方法    │ │· 运行   │
│· 序列化  │ │· 事件    │ │· 序列化 │
└──────────┘ └──────────┘ └──────────┘
       │
       ▼
┌──────────────────────┐
│  KB 服务（事件签名）  │
│  · 查 Delphi API      │
│  · 匹配事件签名       │
│  · 生成正确的方法声明 │
└──────────────────────┘
```

---

## 9. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| `create` 编译失败 | code 有语法错误 | 检查 Pascal 代码，确保 `CreateComponent` 函数签名正确 |
| `create` 运行超时 | 组件创建代码死循环 | 增加 `exec_timeout` 或检查代码 |
| `add` 后 PAS 未同步 | 未传 `target_pas` | 添加 `target_pas` 参数 |
| DFM 解析失败 | DFM 文件格式错误 | 用 `delphi_file(action="read")` 查看 DFM 状态 |
| 事件签名不匹配 | 事件名拼写错误 | 检查 `OnClick`/`OnChange` 等事件名的大小写 |
| 删除后残留方法 | 方法被其他组件引用 | 手动检查残留的事件方法 |
