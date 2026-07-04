<!-- @when: 确保控件定位在各种 DPI/分辨率下稳定可靠，避免硬编码像素坐标 -->
<!-- @part-of: ui-testing -->

#### M. 控件定位策略 — 文本优先、坐标校准、DPI 缩放系数

| 要素 | 内容 |
|------|------|
| **目标** | 确保控件定位在各种 DPI/分辨率下稳定可靠，避免硬编码像素坐标带来的脆弱性 |
| **策略** | ①文本定位优先 → ②名称+偏移校准定位 → ③坐标+DPI系数动态计算 |
| **关键概念** | `@文本`, `@x,y`, `coord_scale`, 校准脚本 |

**背景**：DaofyAutomation 支持三种控件定位方式，优先级如下：

| 定位方式 | 语法 | 适用场景 | 稳定性 |
|---------|------|---------|--------|
| 控件名 | `BtnSave` | 按钮、编辑框、下拉框等标准 VCL 控件 | 🟢 最高（不依赖坐标/文本） |
| 文本匹配 | `cbCity@北京` / `TreeView1@客户管理` | 下拉框选项、树节点、菜单项 | 🟢 高（依赖文本不变） |
| 像素坐标 | `cbMenus@50,43` / `vstProject@25,10` | 无独立 HWND 的自绘控件、VirtualStringTree | 🟡 低（DPI 变化即偏移） |

##### M1. 定位优先级规则（强制）

```
遇到需要定位的控件
├─ 有唯一控件名（如 BtnSave、EditName）→ 直接用控件名，不加 @
├─ 是列表项/树节点/下拉选项/菜单项
│  ├─ 显示文本稳定 → ControlName@显示文本（如 cbCity@北京）
│  ├─ 显示文本动态 → ControlName@0-based索引（如 cbCity@2）
│  └─ 不支持文本匹配 → ControlName@x,y（最后手段）
└─ 是自绘控件的内部区域（无 HWND）
   ├─ 配合 goto 先定位控件 → @x,y 相对于控件客户区
   └─ **必须**在 00-calibration 中验证坐标有效性
```

##### M2. 坐标校准脚本（强制）

每个测试套件必须包含 `00-calibration.json`，在运行其他测试前验证坐标定位的有效性：

```json
[
  {"cmd":"goto","target":"TfrmMain","note":"确认主窗体可打开"},

  {"cmd":"rget","target":"frmMain.ClientWidth","note":"记录当前窗口宽度，用于 DPI 推断"},
  {"cmd":"rget","target":"frmMain.ClientHeight","note":"记录当前窗口高度"},

  {"cmd":"rget","target":"BtnSave.Enabled","note":"验证标准控件可访问","assert_expr":"actual in ('True','False')"},
  {"cmd":"rget","target":"StatusBar.Panels[0].Text","note":"验证状态栏可读"},
  {"cmd":"capture","target":"calibration_main","note":"基线截图"},

  {"cmd":"exit"}
]
```

校准脚本执行后，Python 侧应计算预期 DPI 缩放系数：
```python
# 假设基线在 96 DPI (100%) 下的 ClientWidth 已知为 baseline_width
baseline_width = 832    # 100% DPI 基线值
actual_width = result["frmMain.ClientWidth"]     # 当前运行值
coord_scale = actual_width / baseline_width       # 缩放系数

# 后续所有 @x,y 坐标乘以该系数
def scaled(coord_str: str, scale: float) -> str:
    """将 @x,y 按缩放系数调整。"""
    x, y = map(int, coord_str.lstrip("@").split(","))
    return f"@{int(x * scale)},{int(y * scale)}"

# 使用例
target = scaled("@50,43", coord_scale)  # → "@50,43" 或 "@75,64" (150% DPI)
```

##### M3. 菜单项定位 — 优先文本，次选坐标

菜单（`TMainMenu`、`TPopupMenu`）的菜单项没有独立控件名，定位方式：

```json
[
  {"cmd":"click","target":"cbMenus@50,43","note":"菜单整体坐标点击（脆弱的）"},
  {"cmd":"exit"}
]
```

**建议改为**（若 DaofyAutomation 支持文本匹配菜单）：
```json
[
  {"cmd":"click","target":"@文件(&F)","note":"点击菜单标题"},
  {"cmd":"click","target":"@打开(&O)...","note":"点击打开菜单项"},
  {"cmd":"exit"}
]
```

**若不支持文本匹配**，必须用坐标时：
- 在校准脚本中记录菜单各菜单项的实际坐标偏移量
- 动态计算偏移量 = 基线偏移 × `coord_scale`
- 在校准报告中输出各菜单项的坐标对照表

##### M4. 虚拟树节点定位 — VirtualStringTree

`TVirtualStringTree` 节点通常无独立 HWND，只能靠坐标点击定位。规则：

```json
[
  {"cmd":"goto","target":"TfrmMain"},
  {"cmd":"dblclick","target":"vstProject@25,10","note":"展开根节点（相对于树控件客户区的偏移）"},
  {"cmd":"wait","ms":300},
  {"cmd":"click","target":"vstProject@65,64","note":"选中叶子节点"},
  {"cmd":"exit"}
]
```

**最佳实践**：
- 树节点坐标相对于 `vstProject` 控件客户区（0,0 在控件左上角）
- 先在校准脚本中验证树节点位置（读 `vstProject.RootNodeCount` + `GetNodeAt`）
- 不同 DPI 下树节点行高会缩放，坐标偏移量应乘以 `coord_scale`
- 树节点文本可能被截断，优先用索引坐标（第 N 行）而非像素值

**陷阱**：`@x,y` 坐标系相对控件而非常见坐标系 → 确认树控件不在 scrollbox/panel 内嵌套（嵌套会改变相对坐标原点）；菜单栏弹出后坐标偏移量变化 → 先打开菜单再 `capture`，通过 OCR 定位菜单项。
