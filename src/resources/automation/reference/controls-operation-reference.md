<!-- @when: 选择对 Delphi 控件执行哪个自动化命令时（click/type/textbounds/rget/rset/rcall/uia.*/capture） -->
<!-- @chain: after=capability-matrix.md; before=script-schema.md -->

# 控件操作参考手册

按控件类型给出**推荐命令 + 后备方案 + RTTI 可用属性/方法 + textbounds 适用性 + 常见陷阱**。覆盖：
- VCL 标准控件（System.Classes / Vcl.StdCtrls / Vcl.ComCtrls / Vcl.ExtCtrls / Vcl.Mask / Vcl.Buttons / Vcl.Grids / Vcl.Samples.Calendar 等）
- Thirdpart 目录下的 UI 控件库：jvcl / SynEdit / VirtualTreeView / cnvcl / RxLib / IOComp / picshow / Image32 / RVMedia
- FMX 同名控件（FMX.TButton/TLabel/TMemo/TListView/TTreeView/TStringGrid 等）的操作建议与对应 VCL 控件一致，但 **FMX 无 type-bound 实现**（[Fmx.DaofyAutomation.pas:780](file:///c:/user/daofy-agent/daofy/tools/auto/Fmx.DaofyAutomation.pas#L780) 显式返回 UNSUP），FMX 控件必须用 mode=auto 或 mode=paint。

MCP resource URI: `delphi://automation/controls-reference`。

---

## 0. 必读：渲染栈决定命令选择

`textbounds` 的 paint-hook 只拦截 **GDI（gdi32.dll）和 GDI+（gdiplus.dll）** 的文本绘制函数。**不覆盖 Direct2D / DirectWrite / MIL / Skia / Blink / Qt RHI 等其他渲染栈。**

| 渲染栈 | 典型控件 | textbounds | 推荐命令 |
|--------|---------|:---:|---------|
| **GDI** | VCL 标准控件、jvcl、cnvcl、RxLib、SynEdit（默认）、SynEdit 默认渲染 | ✅ | textbounds / rget / click |
| **GDI+** | FMX Windows 默认、IOComp、VirtualTreeView GDI+ 后端 | ✅ | textbounds / rget / click |
| **Direct2D / DirectWrite** | VirtualTreeView Direct2D 后端、SynDWrite 启用时、WPF/UWP | ❌ | uia.* / rget（仅 RTTI） |
| **自绘 + API 混合** | Image32 实验控件、自定义 TGraphicControl | ⚠️ 视实现而定 | rget + capture + OCR 兜底 |
| **Skia / Blink / RHI** | WebView2 / Electron / Qt Quick | ❌ | uia.* / capture + daofy_ocr |

**判断控件渲染栈的方法**：
1. 看 uses 是否引入 `Vcl.Graphics`（GDI）/ `System.Drawing` 或 GDI+ 单元（GDI+）/ `D2D1` / `Winapi.D2D1` / `DWDirect2D` / `Vcl.Direct2D`（Direct2D）
2. 调 `rinspect` 查看控件祖先类是否继承自 `TGraphicControl`/`TWinControl`（GDI）还是用了自定义 Canvas
3. 试 `textbounds` 失败回退 `uia.*` 或 `capture + OCR`

---

## 0.1 操作命令分级（重要）

下表所有"推荐命令"默认只列**黑盒命令**，"后备"列的 `rset`/`rcall` 仅用于灰盒/白盒测试场景。

| 级别 | 命令 | 说明 |
|------|------|------|
| **黑盒**（用户视角）| `click` / `type` / `key` / `drag` / `hover` / `move` / `textbounds` / `capture` / `waitfor` / `wait` / `msgscan` / `msgclick` / `dlgfile` / `uia.*` / `rget`（只读验证）| 模拟真实用户操作或读取可见状态，**黑盒测试默认只用这一类** |
| **灰盒**（RTTI 介入）| `rset` / `rcall` / `rinspect` / `dumpstate` / `formsum` | 绕过 UI 直接改属性/调方法，**黑盒禁用**，仅用于灰盒/白盒测试或夹具初始化 |
| **白盒**（深度 RTTI）| `delphi_rtti(action=call)` | 直接调内部方法，**黑盒禁用**，仅白盒诊断 |

**核心原则**：
- 黑盒脚本中出现 `rset` / `rcall` 即视为越级，必须改为对应的 `click` / `type` / `key` 操作
- `rget` 是只读，**黑盒可用**（用于读状态做断言验证）
- 测试级别（`test_level`）为 `black-box` 时，Daofy 会对 `rcall`/`rset` 报合规警告

---

## 1. 命令选择决策树

```
要做什么？
├─ 读控件的文本/标题/值
│   ├─ 是 published 属性（Caption/Text/Items/Cells[...]）→ rget（黑盒只读可用）
│   ├─ 控件是 TCollection 派生（列表/树/页签）→ rget ControlName.Items.Text 或 rget ControlName.Items[I].Caption
│   └─ 非 published（自绘/网格内容）→ textbounds 或 dumpstate
├─ 修改控件文本
│   ├─ 黑盒 → type（输入框）/ click ControlName@ItemCaption（列表/树选中）/ click 日期单元格（日历）/ click 页签标题（页签切换）
│   └─ 灰盒后备 → rset Text/Caption/Cells/ItemIndex/ActivePageIndex（仅灰盒/白盒测试或夹具初始化）
├─ 调用方法（滚动/选中/自定义）
│   ├─ 黑盒 → key PageDown/Up/Down（滚动）/ click 滚动条 / key Ctrl+G 等（编辑器跳行）
│   └─ 灰盒后备 → rcall（仅灰盒/白盒测试或夹具初始化）
├─ 点击控件
│   ├─ 控件本身（获焦/激活）→ click ControlName
│   ├─ TCollection 派生控件的指定项（TListBox/TTreeView/TPageControl 等）→ click ControlName@ItemCaption
│   ├─ 开关/切换类控件（TToggleSwitch/TJvSwitch/TiSwitch*/自绘开关）→ 走 §2.1 探针流程（读状态→点对侧→验证），不要直接 click 中心
│   ├─ 自绘/Panel 上的可见文字 → textbounds + click ControlName@x,y（用 visible_* 坐标）
│   ├─ GDI/GDI+ 控件的某个标签 → textbounds + click
│   ├─ DirectUI/WPF/UWP/Electron/WebView → uiaclick
│   └─ 都不行 → capture + daofy_ocr recognize + click @x,y
├─ 验证文字是否截断
│   ├─ GDI/GDI+ → textbounds（visible_state=full 即无截断）+ rget 对比完整值
│   └─ 其他 → capture + OCR
└─ 截图存证 → capture
```

---

## 2. 按钮 / 复选 / 单选类

### 2.1 VCL 标准

| 控件 | 推荐命令 | 后备 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|------|--------------|:---:|------|
| TButton | `click` | — | Caption, ModalResult, Enabled, Visible, Default, Cancel | ✅ GDI | TButton.Enabled=False 时 click 会被忽略，应断言 `rget Enabled=False`；黑盒不应通过 rset Enabled 绕过 |
| TBitBtn | `click` | — | Caption, Kind, Glyph, Layout, Margin, NumGlyphs, Spacing, ModalResult | ✅ GDI | Kind=bkClose/bkOK 等会自动响应 ModalResult，点击后窗口关闭，下一 step 可能 listwnd 失败 |
| TSpeedButton | `click` | — | Caption, GroupIndex, Down, AllowAllUp, Flat, Glyph, Layout | ✅ GDI | GroupIndex>0 时 Down 是状态，点击会切换；Flat=True 时只在 hover 才显示边框，textbounds 仍能捕获 |
| TButtonControl（基类）| — | 灰盒：`rset Checked` | Checked | — | 抽象基类，不直接用 |
| TCheckBox | `click` | 灰盒：`rset Checked` | Caption, Checked, State, AllowGrayed, Enabled | ✅ GDI | AllowGrayed=True 时 State=cbGrayed，Checked 不能区分灰态；黑盒用 click 切换，rget 验证 Checked |
| TRadioButton | `click` | 灰盒：`rset Checked` | Caption, Checked, Enabled | ✅ GDI | 同组内点一个会自动取消其他，无需遍历 |
| TToggleSwitch | `click`（按下方通用探针流程）| `rset State`（仅灰盒/白盒跳过 UI 时）| Caption, State, ShowText, OnText, OffText | ✅ GDI | 击中区域是滑块本身不是 Caption，click 控件中心会命中滑块但不切换；黑盒应走"读状态→点击左/右侧→再读状态验证"建立左右与 on/off 的对应关系 |

**开关类控件黑盒点击探针流程**（通用，适用于 TToggleSwitch / TJvSwitch / TiSwitchLed / TiSwitchPanel / TiSwitchRotary / TiSwitchSlider / TiSwitchToggle / TCheckboxCtrl / TRadioBtnCtrl 等所有"击中区域 ≠ 控件中心"的开关/切换控件）：

```json
[
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "note": "记录初始状态基线（StateProp 取下表对应属性）"},
  {"cmd": "click", "target": "<ControlName>", "x": "<Width*0.25>", "y": "<Height/2>", "note": "点击左半侧（避开滑块/旋钮）"},
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "assert_expr": "actual != '<上一步初始值>'", "note": "验证状态变更，建立'左半侧 → 切换方向'的对应关系；若未变更说明左半侧是当前状态的同侧"},
  {"cmd": "click", "target": "<ControlName>", "x": "<Width*0.75>", "y": "<Height/2>", "note": "点击右半侧反向验证"},
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "assert_expr": "actual == '<初始值>'", "note": "右半侧应切换回原状态，建立'右半侧 → 反向'对应"}
]
```

适用控件与状态属性对照：

| 控件 | 库 | StateProp | 取值 | 备注 |
|------|----|----------|------|------|
| TToggleSwitch | VCL | `State` | tgOn / tgOff | 标准 ToggleSwitch |
| TJvSwitch | jvcl | `State` | tgOn / tgOff | 与 TToggleSwitch 类似 |
| TiSwitchLed / TiSwitchPanel / TiSwitchRotary / TiSwitchSlider / TiSwitchToggle | IOComp | `Value` 或 `State` | 控件特定（看 rinspect） | 工业开关，部分用 Value（Boolean），部分用 State |
| TCheckboxCtrl / TRadioBtnCtrl | Image32 | `Checked` | True / False | 实验性，渲染栈不确定 |
| TSpeedButton（GroupIndex>0） | VCL | `Down` | True / False | 同组互斥切换 |
| 自绘开关控件 | 任意 | 看具体实现 | — | 用 rinspect 找状态属性，再套用此流程 |

通过这个探针可以确认：当前控件实例下，点击左/右半侧分别对应 On 还是 Off（不同 Delphi 版本/主题/控件库可能有差异），后续点击就用已建立的对应关系直接点对侧。

### 2.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvBitBtn/TJvButton/TJvArrowButton/TJvBitmapButton/TJvHTButton | jvcl | `click` | ✅ GDI | TJvHTButton 支持 HTML 标签的 Caption，textbounds 拿到的是渲染后的纯文本 |
| TJvCaptionButton | jvcl | `click` | ⚠️ 不可靠 | 标题栏按钮，绘制走 NC area，paint-hook 不拦截非客户区绘制 |
| TJvSwitch/TJvRollOut | jvcl | `click`（按上方通用探针流程）/ `rset State`（仅灰盒）| ✅ GDI | TJvSwitch 与 TToggleSwitch 类似，击中区域 ≠ 中心，黑盒走探针流程；TJvRollOut 是折叠面板，点击 Caption 区域展开/折叠 |
| TRxSpeedButton/TRxAnimBitBtn | RxLib | `click` | ✅ GDI | TRxAnimBitBtn 有动画 Glyph，点击时序敏感 |
| TiSwitchLed/TiSwitchPanel/TiSwitchRotary/TiSwitchSlider/TiSwitchToggle | IOComp | `click`（按上方通用探针流程）/ `rset Value`（仅灰盒）| ✅ GDI+ | 工业开关，击中区域是旋钮/滑块本身不是控件中心，黑盒走探针流程；灰盒可用 rset Value/State 直接改 |
| TButtonCtrl/TRoundedBtnCtrl/TEllipseBtnCtrl/TImageBtnCtrl | Image32 | `click`（灰盒后备：`rcall DoClick`）| ⚠️ 自绘 | 实验性控件，无标准 published Caption；黑盒用 click 控件中心，若击中区域不在中心用 textbounds 定位 |
| TCheckboxCtrl/TRadioBtnCtrl | Image32 | `click`（按上方通用探针流程，灰盒后备：`rcall Toggle`）| ⚠️ 自绘 | 实验性，渲染栈不确定，黑盒走探针流程（用 `Checked` 作为 StateProp） |

---

## 3. 输入框 / 编辑框类

### 3.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TEdit | `type`（写入） / `rget Text`（读验证）| Text, MaxLength, PasswordChar, ReadOnly, CharCase, NumbersOnly, SelStart, SelLength, SelText | ✅ GDI | type 模拟真实键盘，黑盒首选；rset Text 是灰盒后备，不触发 OnKeyPress/OnChange |
| TMemo | `type`（写入） / `rget Lines.Text`（读验证）| Text, Lines (TStrings), SelStart, SelLength, SelText, ScrollBars, WordWrap, CaretPos | ✅ GDI | type-bound 用 `EM_POSFROMCHAR` + `EM_LINEINDEX` 精确计算行首 Y 与行高（替代硬编码 16 像素），字体变化时矩形准确；行高优先取下一行 Y 差，末行用 `GetTextMetrics` 字体高度 |
| TMaskEdit | `type`（写入） / `rget EditText`（读验证）| Text, EditMask, MaxLength, EditText | ✅ GDI | EditText 是去掉掩码后的值，Text 可能含掩码字符；测试时建议 rget EditText |
| TLabeledEdit | `type`（写入） / `rget Text`（读验证）| Text, EditLabel.Caption, LabelPosition, LabelSpacing | ✅ GDI | EditLabel 是子控件，点击 EditLabel 不会获焦 Edit |
| TButtonedEdit | `type`（写入） / `rget Text`（读验证）| Text, LeftButton.Visible, RightButton.Visible, Images | ✅ GDI | 点击左右按钮需要 textbounds 定位按钮图标位置后 click；灰盒后备 `rcall` 调用 OnLeftButtonClick/OnRightButtonClick |
| TSpinEdit | `type`（写入数字） / `click` 上下箭头 / `rget Value`（读验证）| Text, Value, MinValue, MaxValue, Increment | ✅ GDI | 黑盒用 type 输入数字或 click 上下箭头按钮；rset Value 是灰盒后备 |
| TComboBox | `click ControlName@ItemCaption`（选项） / `type`（csDropDown 时输入） / `rget ItemIndex`（读验证）| Items, Text, Style, ItemIndex, DropDownCount, Sorted | ✅ GDI | Style=csDropDownList 时只能选 Items 中的项，不能用 type；**type-bound 仅计算可见项**：下拉未展开时仅匹配选中项返回 Edit 框矩形（否则 `DROPDOWN_CLOSED`），展开时按 `CB_GETTOPINDEX`+可见项数检查，不可见返回 `NOT_VISIBLE`（需先滚动） |
| TComboBoxEx | `click ControlName@ItemCaption` | ItemsEx, Images, Style, DropDownCount | ✅ GDI | ItemsEx 是 TComboExItems，每项含 ImageIndex/SelectedImageIndex/OverlayImageIndex/Indent |
| TColorBox | `click ControlName@颜色名` | Selected, Style, Colors, DefaultColorColor, CustomColors | ✅ GDI | Selected 是 TColor，黑盒应 click 列表项；灰盒后备 `rset Selected` |

### 3.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvEdit/TJvCheckedMaskEdit | jvcl | `type`（写入） / `rget Text`（读验证）| ✅ GDI | TJvCheckedMaskEdit 的 CheckBox 状态黑盒用 click 切换，灰盒后备 rset Checked |
| TJvIPAddress | jvcl | `type` 逐段输入（`key` TAB 切换字段）| ✅ GDI | Text 是 `1.2.3.4` 格式；黑盒 type 各字段并用 key TAB 切换；灰盒后备 `rcall FocusField(idx)` |
| TJvComboBox/TJvCheckedComboBox/TJvColorComboBox/TJvFontComboBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | TJvCheckedComboBox 多选，黑盒 click 各项切换勾选；灰盒后备 `rset Checked[I]` |
| TJvComboListBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | 是 ListBox 派生，不是 ComboBox |
| TCustomNumEdit/TCurrencyEdit/TRxCalcEdit | RxLib | `type`（写入数字） / `rget Value`（读验证）| ✅ GDI | 黑盒 type 数字字符串；rset Value 是灰盒后备 |
| TRxDBComboBox/TDBIndexCombo | RxLib | `click ControlName@ItemCaption` | ✅ GDI | 数据感知，黑盒 click 列表项 |
| TSynHotKey | SynEdit | `key`（按键组合，如 Ctrl+A）| ✅ GDI | 黑盒用 key 按下组合键；HotKey 是 TShortcut 属性，灰盒后备 `rset HotKey` |
| TiEdit/TiModeComboBox | IOComp | `type`（写入） / `click` 选项 | ✅ GDI+ | 工业控件，黑盒用 type/click；rset Value/Text 是灰盒后备 |
| TEditCtrl/TMemoCtrl | Image32 | `type`（写入） | ⚠️ 自绘 | 实验性；rset Text 是灰盒后备 |

---

## 4. 列表 / 网格类

### 4.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TListBox | `click ControlName@ItemCaption` | Items (TStrings), ItemIndex, TopIndex, Count, Sorted, MultiSelect, Selected[I], ItemHeight | ✅ GDI | MultiSelect=True 时 Selected 数组可独立切换，黑盒用 key Ctrl+click 或 Shift+click 模拟多选 |
| TCheckListBox | `click ControlName@ItemCaption`（勾选切换）| Items, ItemIndex, Checked[I], State[I], AllowGrayed | ✅ GDI | **⚠️ type-bound 实现仅匹配 `Ctl is TListBox`，TCheckListBox 不会命中该分支**（继承自 TCustomListBox 而非 TListBox），应 mode=auto 让 paint-hook 接管；黑盒用 click 项切换勾选，rget Checked[I] 验证 |
| TComboBox（已列于输入框）| 同上 | 同上 | ✅ GDI | 同上 |
| TListView | `click ControlName@ItemCaption` | Items, Columns, ViewStyle, Selected, TopItem, ItemIndex, SortType, SmallImages, LargeImages | ✅ GDI | **type-bound 仅匹配 Caption，不查 SubItems**，要定位子列文本必须 mode=auto；ViewStyle=vsReport 时项文本是 Caption，子列是 SubItems |
| TDrawGrid | `click ControlName@x,y`（先 textbounds 定位）| ColCount, RowCount, FixedCols, FixedRows, Selection, TopRow, LeftCol, DefaultColWidth, DefaultRowHeight | ⚠️ 自绘 | DrawGrid 无内置文本，必须用 OnDrawCell 事件自绘；textbounds 在 OnDrawCell 内若用 GDI 文本 API 可捕获，自绘图标/GDI+ 视情况 |
| TStringGrid | `click ControlName@x,y`（先 textbounds 定位单元格） / `rget Cells[col,row]`（读验证）| Cells[col,row], Rows[row], Cols[col], Objects[col,row], ColCount, RowCount, FixedCols, FixedRows, Selection | ✅ GDI | 黑盒用 textbounds 定位单元格后 click；rget Cells 读取验证；rset Cells 是灰盒后备 |
| TValueListEditor | `click ControlName@x,y`（先 textbounds 定位） / `rget Values['Key']`（读验证）| Strings (TStrings), Keys[I], Values[I], ItemProps, TitleCaptions | ✅ GDI | 类似 TStringGrid 但每行是 Key=Value；黑盒 click 单元格后 type 修改；rset Values 是灰盒后备 |

### 4.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TVirtualStringTree | VirtualTreeView | `click` 节点（先 textbounds 定位）/ `rget` 节点文本 | ⚠️ 视后端 | **虚拟树，无内置 Items 集合**，文本通过 OnGetText 事件提供；Default 后端是 GDI（✅），Direct2D/GDI+ 后端情况视控件 RenderStyle 设置；黑盒用 textbounds 定位后 click，灰盒后备 `rcall FocusedNode` |
| TVirtualDrawTree | VirtualTreeView | `click` 节点（先 textbounds 定位）| ⚠️ 视后端 | 完全自绘，无文本概念；黑盒用 textbounds 定位后 click，需先确保渲染后端是 GDI |
| TJvListBox/TJvCheckListBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | 同标准 TListBox |
| TTextListBox/TRxCheckListBox | RxLib | `click ControlName@ItemCaption` | ✅ GDI | 同标准 |
| TJvDBGrid | jvcl | `click` 单元格（先 textbounds 定位）/ `rget SelectedField.Value`（读验证）| ✅ GDI | 数据感知，黑盒用 textbounds 定位后 click；SelectedField 是当前选中字段 |
| TiLinkedListBox/TiModeComboBoxDisplay | IOComp | `click ControlName@ItemCaption` | ✅ GDI+ | 工业控件，黑盒 click 项；灰盒后备 `rset ItemIndex` |
| TListCtrl/TScrollingCtrl | Image32 | `click` 项（先 textbounds 定位）| ⚠️ 自绘 | 实验性 |

---

## 5. 树形类

### 5.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TTreeView | `click ControlName@NodeText`（先展开父节点）| Items (TTreeNodes), Selected, TopItem, ShowButtons, ShowLines, ShowRoot, Indent, SortType | ✅ GDI | **type-bound 扁平遍历所有 Items，未过滤展开状态**，DisplayRect(True) 对隐藏节点返回无效矩形；折叠状态下定位子节点必须 mode=auto；黑盒用 `click` 父节点展开图标展开后再 click 子节点，灰盒后备 `rcall Items.GetFirstNode` |

### 5.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TVirtualStringTree | VirtualTreeView | `click` 节点（先 textbounds 定位） | ⚠️ 视后端 | **虚拟树，节点不预创建**，文本通过 OnGetNodeText 取；黑盒用 textbounds 定位节点后 click，灰盒后备 `rcall FullExpand` / `rcall FocusedNode := Node` / `rcall EnsureVisible` |
| TJvTreeView/TJvCheckTreeView | jvcl | `click ControlName@NodeText`（勾选切换）| ✅ GDI | TJvCheckTreeView 黑盒 click 节点切换勾选；灰盒后备 `rset Checked[Node]` |

---

## 6. 页签 / 向导类

### 6.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TPageControl | `click ControlName@TabCaption` | Pages, ActivePage, ActivePageIndex, PageCount, TabHeight, TabWidth, TabPosition, Style, MultiLine | ✅ GDI | TabPosition=tpBottom/tpLeft/tpRight 时 TabRect 矩形坐标不同，type-bound 仍能命中；黑盒 click 页签切换，rget ActivePageIndex 验证；rset ActivePageIndex 是灰盒后备 |
| TTabControl | `click ControlName@TabCaption` | Tabs, TabIndex, TabWidth, TabHeight, Style, MultiLine | ✅ GDI | TTabControl 不像 TPageControl 有 Pages 集合，是单纯页签条；rset TabIndex 是灰盒后备 |
| TTabSheet | `rget Caption`（读验证） | Caption, PageControl, PageIndex, TabVisible, ImageIndex, Highlighted | ✅ GDI | 直接 click TTabSheet 不会切换页签，必须 click 父 TPageControl 的 TabRect |
| TNotebook | 无黑盒切换方式 | Pages, ActivePage, PageIndex | ⚠️ 不可靠 | 旧控件，无可见页签条，黑盒无法切换；灰盒后备 `rset ActivePage` |

### 6.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvTabControl/TJvPageControl/TJvTabBar | jvcl | `click ControlName@TabCaption` | ✅ GDI | TJvTabBar 是 Outlook 风格；rset ActivePageIndex 是灰盒后备 |
| JvgPage/JvgTab | jvcl | `click ControlName@TabCaption` | ✅ GDI | Globus 系列；rset ActivePage 是灰盒后备 |
| TJvWizard | jvcl | `click` Next/Previous 按钮 | ✅ GDI | 黑盒 click 向导界面上的 Next/Previous 按钮；灰盒后备 `rcall NextPage` / `rcall PriorPage` |
| TCnVSNETTabPageControl/TCnVIDTabPageControl | cnvcl | `click ControlName@TabCaption` | ✅ GDI | 停靠风格的页签；rset ActivePage 是灰盒后备 |
| TPageTabCtrl/TPagePnlCtrl/TPageCtrl | Image32 | `click` 页签（先 textbounds 定位）| ⚠️ 自绘 | 实验性；rset ActivePageIndex 是灰盒后备 |

---

## 7. 容器 / 面板类

### 7.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TPanel | `rget Caption` | Caption, Alignment, BevelInner, BevelOuter, BevelWidth, BorderStyle, FullRepaint, Locked, ParentBackground | ✅ GDI | 点击 Panel 上的 Label 应直接 click LabelName，而非 click PanelName |
| TGroupBox | `rget Caption` | Caption | ✅ GDI | 同 TPanel |
| TScrollBox | `click` 滚动条 / `key` PageDown/Up | HorzScrollBar, VertScrollBar, AutoScroll | ✅ GDI | 子控件超出可视区时 click 前要先黑盒用滚动条或 key 翻页；灰盒后备 `rcall ScrollInView` |
| TControlBar | `rget ButtonCount` | ButtonCount, Buttons[I], RowCount, AutoSize, Picture | ✅ GDI | 可拖动布局的子控件 |
| TFlowPanel | 通过子控件操作 | FlowStyle, AutoWrap, LastWrapBreak | ✅ GDI | 自动排列子控件 |
| TGridPanel | 通过子控件操作 | ColumnCollection, RowCollection, ExpandStyle | ✅ GDI | 网格布局 |
| TSplitter | `rget MinSize` | MinSize, MinSize, ResizeStyle, AutoSnap | ✅ GDI | 拖拽用 `drag SplitterName` |
| THeader | `rget Section[I].Text` | Sections, Section[I].Text, Section[I].Width | ⚠️ 旧控件 | 旧控件，建议用 THeaderControl |
| THeaderControl | `rget Sections[I].Text` | Sections, Sections[I].Text, Sections[I].Width, Sections[I].MinWidth, Sections[I].MaxWidth | ✅ GDI | 拖动分隔线改变宽度用 `drag HeaderControl1@x,y` |

### 7.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvPanel/TJvCaptionPanel/TJvBehaviorLabel | jvcl | `rget Caption` | ✅ GDI | TJvCaptionPanel 可拖动标题栏 |
| TJvBackgrounds/TJvFooter/TJvContentScroller/TJvSpacer/TJvShape/TJvSticker | jvcl | — | ✅ GDI | 装饰性容器 |
| TJvCoolBar/TJvControlBar/TJvToolBar | jvcl | — | ✅ GDI | 工具条 |
| TJvLookOut/TJvOutlookBar/TJvNavigationPane | jvcl | `click` 导航项 | ✅ GDI | Outlook 风格导航，黑盒 click 项切换；rset ActivePage 是灰盒后备 |
| TCnVSNETDockPanel/TCnVIDDockPanel | cnvcl | `rget VisibleDockClients` | ✅ GDI | 停靠面板，dockable 子控件 |
| TRxPanel/TRxProgress | RxLib | `rget Caption` / `rget Position` | ✅ GDI | TRxProgress 是进度条（显示型，黑盒只能 rget 读，不能改） |
| TSecretPanel | RxLib | `rget Caption` | ✅ GDI | 可滚动字幕面板（显示型）；rset Active 是灰盒后备 |
| TiAboutPanel/TiStripChart/TiGradient | IOComp | `rget Caption` / `rget TitleText` | ✅ GDI+ | 工业控件（显示型，黑盒只能 rget 读） |
| TPanelCtrl/TRootCtrl | Image32 | 无黑盒修改方式 | ⚠️ 自绘 | 实验性；rset Caption 是灰盒后备 |

---

## 8. 标签 / 显示类

### 8.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TLabel | `rget Caption` | Caption, Alignment, Layout, WordWrap, AutoSize, Transparent, FocusControl | ✅ GDI | 点击 TLabel 不会获焦（无句柄），若要触发 FocusControl 的 GotFocus 必须 click FocusControl 本身 |
| TStaticText | `rget Caption` | Caption, Alignment, BorderStyle, ShowAccelChar | ✅ GDI | 有句柄的 TLabel |
| TLinkLabel | `rget Caption` | Caption | ✅ GDI | Caption 含 `<a>` HTML 标签，渲染后是普通文本，textbounds 拿到纯文本 |
| TPaintBox | — | Canvas, Anchors, Hint | ⚠️ 自绘 | 无 Caption/Text，绘制内容由 OnPaint 事件决定；textbounds 仅在 OnPaint 内用 GDI 文本 API 时可捕获 |

### 8.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvLabel/TJvBehaviorLabel/TJvHtmlLabel | jvcl | `rget Caption` | ✅ GDI | TJvHtmlLabel 支持 HTML 标签，textbounds 拿到渲染后纯文本 |
| JvgLabel/JvgDigits/JvgShadow | jvcl | `rget Caption` | ✅ GDI | Globus 系列，特效标签 |
| TRxLabel/TRxCustomLabel | RxLib | `rget Caption` | ✅ GDI | — |
| TiLabel/TiImageDisplay | IOComp | `rget Caption` | ✅ GDI+ | 工业控件 |
| TLabelCtrl/TStatusbarCtrl | Image32 | `rget Caption`（显示型，无黑盒修改）| ⚠️ 自绘 | 实验性；rset Caption 是灰盒后备 |

---

## 9. 图像 / 动画类

### 9.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TImage | `rget Picture` | Picture, Stretch, Proportional, Center, Transparent, AutoSize | ❌ 无文本 | 无 Caption/Text，仅显示图像 |
| TShape | `rget Shape` | Shape, Brush, Pen | ❌ 无文本 | 无文本 |
| TBevel | `rget Shape` | Shape, Style | ❌ 无文本 | — |
| TAnimate | `rget FileName` / `rget Active`（读验证）| FileName, CommonAVI, Active, StartFrame, StopFrame, Repetitions | ❌ 无文本 | AVI 动画，黑盒无用户操作入口（除非有 OnClick）；灰盒后备 `rset Active=True` |
| TImageList | `rget Count` | Count, Width, Height, AllocBy, BkColor, BlendColor | ❌ 无文本 | 非可视 |
| TTimer | `rget Enabled`（读验证）| Enabled, Interval | ❌ 无文本 | 非可视，黑盒无用户操作入口；灰盒后备 `rset Enabled=True` |

### 9.2 第三方

| 控件 | 库 | 推荐命令 | textbounds | 陷阱 |
|------|----|-----|:---:|------|
| TJvImage/TJvBaseThumbImage/TJvBaseThumbnail/TJvBaseThumbView | jvcl | `rget Picture` | ❌ 无文本 | — |
| TJvAnimate/TJvAnimatedImage/TJvBmpAnimator/TJvGIFCtrl | jvcl | `rget Active`（读验证）| ❌ 无文本 | 动画控件，黑盒无标准用户操作入口；灰盒后备 `rset Active=True` |
| TJvPicClip/TJvZoom | jvcl | — | ❌ 无文本 | TJvZoom 是放大镜效果 |
| TPicShow/TDBPicShow | picshow | `rget Picture`（读验证）| ❌ 无文本 | 图像过渡显示，过渡过程中画面变化快；黑盒无标准操作入口；灰盒后备 `rset Picture` / `rset Step=0` |
| TImage32Panel/TNotifyImage32/TBaseImgPanel | Image32 | `rget Bitmap`（读验证）| ❌ 无文本 | GDI 显示图像，黑盒无标准操作入口；灰盒后备 `rset Bitmap` |
| TRVCamView/TRVCamMultiView | RVMedia | `rget Active`（读验证）| ❌ 无文本 | 视频流显示，画面动态；黑盒无标准操作入口；灰盒后备 `rset Active=True` |

---

## 10. 编辑器类（代码 / 富文本）

| 控件 | 库 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|-----|---------|----|:---:|------|
| TRichEdit | VCL | `type`（写入）/ `rget Lines.Text` / `rget SelText`（读验证）| Lines, Text, SelStart, SelLength, SelText, SelAttributes, Paragraph | ✅ GDI | 黑盒用 `type` 写入、`rget` 读取验证；**type-bound 用 ClassNameIs 而非 is**，原因是不想 uses Vcl.ComCtrls；同 TMemo 用 `EM_POSFROMCHAR` 精确计算行高（RichEdit 2.0+ 的 `EM_POSFROMCHAR` 参数语义与 EDIT 不同：wParam=@Point, lParam=CharIdx）；灰盒后备 `rset SelText` |
| TSynEdit/TDBSynEdit | SynEdit | `type`（写入）/ `rget Lines.Text` / `rget CaretXY`（读验证）/ `key` Ctrl+G 跳行（黑盒 GotoLine）| Lines, Text, SelStart, SelLength, SelText, CaretXY, TopLine, LinesInWindow, BlockBegin, BlockEnd, Highlighter | ✅ GDI（默认）/❌ Direct2D（SynDWrite 启用） | 黑盒用 `type`/`key` 操作；**代码编辑器，行高/字体高度多变**，type-bound 不适用，务必 mode=auto 或 paint；SynDWrite 启用时 paint-hook 失效，黑盒改用 `key` Ctrl+G → `type` 行号 → `key` Enter 替代跳行；灰盒后备 `rset SelText` / `rcall GotoLineAndCenter` |
| TJvEditor/TJvMemo | jvcl | `type`（写入）/ `rget Lines.Text`（读验证）| Lines, Text, CaretX, CaretY, TopLine, LeftChar | ✅ GDI | TJvEditor 是简单代码编辑器，黑盒用 `type` 写入 |
| TJvHTButton 类 HTML 标签显示控件 | jvcl | `rget Caption` | Caption | ✅ GDI | HTML 渲染后纯文本 |
| TRichView（未在 Thirdpart 但常见） | — | `rget RVData.GetText` | RVData, Style, BackgroundBitmap | ⚠️ 视实现 | 富文本，绘制走 GDI 但内容多段，textbounds 拿到首个匹配段 |
| THexDump | RxLib | `rget DataSize` | Data, DataSize, BytesPerRow, OffsetFormat | ✅ GDI | 十六进制查看器 |

---

## 11. 仪表 / 工业控件（IOComp 专属）

IOComp 全部使用 GDI+ 渲染（iGPFunctions.pas 封装），textbounds ✅ 可用。这些控件主要是**显示型**——Value/Position 等属性通常由外部数据源（PLC/传感器/业务代码）驱动，**不是用户直接操作 UI 触发**。因此：

- **黑盒测试**：只能 `rget` 读取数值验证显示效果；不能通过 `click`/`type` 改变 Value/Position（除非控件本身有交互入口如鼠标拖动旋钮、虚拟键盘按键）
- **灰盒测试**：可用 `rset` 直接改属性值模拟数据源变化，验证显示是否正确

| 控件 | 类别 | 黑盒推荐命令 | 灰盒后备 | 关键 RTTI 属性 |
|------|------|---------|------|--------------|
| TiAnalogDisplay/TiAnalogOutput/TiIntegerOutput | 数字显示 | `rget Value`（读验证）| `rset Value` | Value, ValueFormat, Alignment |
| TiAngularGauge/TiAngularLogGauge/TiLinearGauge/TiLogGauge | 仪表盘 | `rget Value`（读验证）| `rset Value` | Value, Min, Max, PointerColor |
| TiLed/TiLedArrow/TiLedDiamond/TiLedRectangle/TiLedRound/TiLedSpiral | LED 指示灯 | `rget Active`（读验证）| `rset Active=True` | Active, Color, Beveled |
| TiLedBar/TiLedMatrix/TiLCDMatrix/TiLCDCharacter | LED 条/矩阵 | `rget Value`（读验证）| `rset Value` | Value, SegmentColor |
| TiSevenSegmentDisplay/Clock/ClockSMPTE/Analog/Binary/Character/Hexadecimal/Integer | 七段数码管 | `rget Value`（读验证）| `rset Value` | Value, ColorOn, ColorOff |
| TiKnob/TiSlider/TiCompass/TiDualCompass/TiMotor/TiThermometer/TiOdometer | 旋钮/滑块/罗盘/温度计/里程表 | `drag` 旋钮/滑块（部分支持）/ `rget Value` / `rget Position`（读验证）| `rset Value` / `rset Position` | Value, Position, Min, Max |
| TiSwitchLed/TiSwitchPanel/TiSwitchRotary/TiSwitchSlider/TiSwitchToggle | 开关 | `click`（按 §2.1 探针流程）/ `rget Value` / `rget State`（读验证）| `rset Value` / `rset State` | Value, State |
| TiKeyBoard | 虚拟键盘 | `click` 按键（黑盒模拟用户按键）| — | Keys |
| TiCheckBox | 复选框 | `click`（黑盒切换）| `rset Checked=True` | Checked, Caption |
| TiEdit/TiModeComboBox | 输入框 | `type`（写入）/ `click ControlName@ItemCaption` | `rset Text` | Text, Value |
| TiLabel/TiImageDisplay/TiGradient/TiAboutPanel/TiStripChart | 显示/图表 | `rget Caption` / `rget TitleText`（读验证）| `rset Caption` / `rset TitleText` | Caption, TitleText |
| TiPlotComponent/TiScope | 高级绘图 | `rget Channel[I].Value`（读验证）| `rset Channel[I].Value` | Channels, Channel[I].Value |

---

## 12. 日期 / 时间类

### 12.1 VCL 标准

| 控件 | 推荐命令 | RTTI 可用属性 | textbounds | 陷阱 |
|------|---------|--------------|:---:|------|
| TMonthCalendar | `click` 日期单元格（黑盒选择日期）/ `rget Date` / `rget EndDate`（读验证）| Date, EndDate, MinDate, MaxDate, MultiSelect, FirstDayOfWeek, ShowToday, ShowTodayCircle | ✅ GDI | 黑盒 click 日期单元格选择日期，多选时 click 起始日期 + Shift+click 结束日期；灰盒后备 `rset Date` / `rset EndDate` |
| TDateTimePicker | `click` 下拉箭头展开日历 / `type` 输入日期或时间（黑盒）/ `rget Date` / `rget Time`（读验证）| Date, Time, DateTime, Format, Kind, ShowCheckbox, Checked, CalAlignment | ✅ GDI | 黑盒 click 下拉箭头展开日历后 click 日期，或直接 `type` 输入日期/时间字符串；Kind=dtkTime 时只显示时间，Date 属性仍包含日期部分；ShowCheckbox=True 时 click 复选框切换启用；灰盒后备 `rset Date` / `rset Time` / `rset Format` |
| TCalendar（Vcl.Samples.Calendar）| `click` 日期单元格（黑盒选择）/ `rget Year` / `rget Month` / `rget Day`（读验证）| Year, Month, Day, StartOfWeek, UseCurrentDate | ✅ GDI | 旧控件，黑盒 click 日期单元格；灰盒后备 `rset Year` / `rset Month` / `rset Day` |

---

## 13. 对话框 / 弹窗类

| 控件 / 类型 | 推荐命令 | 陷阱 |
|------|---------|------|
| TOpenDialog/TSaveDialog | `dlgfile`（执行）+ `dlgfile path="..."`（填路径） | Windows 8+ 现代视图的文件列表走 DirectUI，textbounds 不覆盖该区域，列表项点击改用 `uiaclick` |
| TFontDialog | `uiascan` + `uiaclick` | 系统对话框，DirectUI/GDI 混合渲染 |
| TColorDialog | `uiascan` | 同上 |
| TPrintDialog | `uiascan` | 同上 |
| TFindDialog/TReplaceDialog | `uiascan` + `uiatype`/`uiaclick`（黑盒填文本/点击按钮）| 是非模态对话框，黑盒用 uia.* 操作 Find/Replace 输入框和按钮；灰盒后备 `rset FindText` / `rset ReplaceText` / `rcall CloseDialog` |
| MessageBox / Application.MessageBox | `msgscan` + `msgclick` | 走 `MessageBox` API 的标准 GDI 弹窗 |
| TTaskDialog | `uiascan` + `uiaclick`（DirectUI 渲染） | 较新的任务对话框 |
| TJvCommonDialog 系列派生 | `click` 触发按钮（黑盒调用 Execute）+ `uiascan`/`uiaclick` 操作弹窗 | 第三方对话框，黑盒通过 click 触发按钮调用 Execute，弹窗内用 uia.*；灰盒后备 `rcall Execute` |

---

## 14. 公共操作速查

### 14.1 滚动到可见

**黑盒方式**（推荐）：

```json
{"cmd": "key", "target": "TreeView1", "key": "PageDown", "note": "翻页直到目标节点可见"}
{"cmd": "key", "target": "ListBox1", "key": "Down", "note": "逐项下移到目标项可见"}
{"cmd": "click", "target": "ScrollBox1", "x": "<Width-8>", "y": "<Height-8>", "note": "click 垂直滚动条下箭头"}
{"cmd": "key", "target": "ScrollBox1", "key": "PageDown"}
```

**灰盒后备**（仅灰盒/白盒测试或夹具初始化）：

```json
{"cmd": "rcall", "target": "TreeView1.Selected.EnsureVisible"}
{"cmd": "rcall", "target": "ListBox1.TopIndex = 5"}
{"cmd": "rcall", "target": "VirtualStringTree1.FocusedNode.EnsureVisible"}
{"cmd": "rcall", "target": "ScrollBox1.ScrollInView(Panel1)"}
```

### 14.2 选中项

| 控件 | 黑盒推荐命令 | 灰盒后备 |
|------|---------|------|
| TListBox | `click ListBox1@<项文本>` | `rset ListBox1.ItemIndex = 5` |
| TComboBox | `click ComboBox1@<项文本>` | `rset ComboBox1.ItemIndex = 5` |
| TListView | `click ListView1@<项文本>` | `rset ListView1.Selected = ListView1.Items[5]` |
| TTreeView | `click TreeView1@<节点文本>`（先展开父节点）| `rset TreeView1.Selected = TreeView1.Items[5]` |
| TPageControl | `click PageControl1@<页签标题>` | `rset PageControl1.ActivePageIndex = 2` |
| TStringGrid | `click StringGrid1@x,y`（先 textbounds 定位单元格）| `rset StringGrid1.Selection = TRect.Create(0,5,0,5)`（行=5，列=0） |
| TVirtualStringTree | `click VirtualStringTree1@x,y`（先 textbounds 定位节点）| `rcall VirtualStringTree1.FocusedNode := Node` |

### 14.3 文本截断验证（仅 GDI/GDI+）

```json
[
  {"cmd": "rget", "target": "Label1.Caption", "note": "拿完整文本"},
  {"cmd": "textbounds", "target": "Label1", "text": "<完整文本>", "mode": "auto"},
  {"cmd": "assert_expr", "actual": "<textbounds.state.visible_state>", "expr": "actual == 'full'"}
]
```

非 GDI/GDI+ 控件：用 `capture + daofy_ocr` 识别 + 字符串比对。

---

## 附录 A：Type-bound 已覆盖控件清单（VCL only）

来源：[Vcl.DaofyAutomation.pas](file:///c:/user/daofy-agent/daofy/tools/auto/Vcl.DaofyAutomation.pas) `TypeBoundFallback` 函数（L652-830）。

| 控件 | 查找项文本 | 项矩形 | 已知限制 |
|------|----------|-------|---------|
| TListBox | Items[I] | ItemRect(I) | 仅匹配 `Ctl is TListBox`，**TCheckListBox 不命中**（继承自 TCustomListBox） |
| TComboBox | Items[I] | 可见项区域：未展开时仅匹配选中项返回 Edit 框矩形；展开时按 `CB_GETTOPINDEX`+可见项数手算 `Rect(0, (I-TopIdx)*ItemHeight, Width, (I-TopIdx+1)*ItemHeight)` | **未展开且非选中项返回 `DROPDOWN_CLOSED`；展开但项不可见返回 `NOT_VISIBLE`（需先滚动）** |
| TTreeView | Items[I].Text | DisplayRect(True) | **未过滤展开状态**，隐藏节点矩形无效 |
| TListView | Items[I].Caption | DisplayRect(drBounds) | **不查 SubItems**，要定位子列必须 mode=auto |
| TPageControl | Pages[I].Caption | TabRect(I) | TabPosition=tpBottom/tpLeft/tpRight 时仍能命中 |
| TTabControl | Tabs[I] | TabRect(I) | — |
| TMemo | Lines[I]（SameText + Pos 双匹配）| `EM_POSFROMCHAR` + `EM_LINEINDEX` 精确计算 `Rect(2, StartY, Width-2, StartY+LH)` | 行高优先取下一行首字符 Y 差，末行用 `GetTextMetrics` 字体高度；WordWrap 多视觉行时矩形覆盖整块 |
| TRichEdit | 同 TMemo（ClassNameIs 强转 TMemo） | 同 TMemo（IsRichEdit=True，`EM_POSFROMCHAR` 参数语义不同） | 同 TMemo；ClassNameIs 绕过 is 检查以避免 uses Vcl.ComCtrls |
| TWinControl 通用回退 | RTTI `IsPublishedProp('Caption')` + `GetStrProp` | ChildCtl.Left/Top/Width/Height | 仅覆盖直接子控件，不递归；非 published Text 属性无法命中 |

**FMX 无 type-bound 实现**（[Fmx.DaofyAutomation.pas:780](file:///c:/user/daofy-agent/daofy/tools/auto/Fmx.DaofyAutomation.pas#L780) 显式返回 UNSUP），FMX 必须用 mode=auto 或 mode=paint。

---

## 附录 B：第三方 UI 库速查

| 库 | 渲染 | 类别覆盖 | 入口路径 |
|----|:---:|---------|---------|
| jvcl | GDI | 全类（按钮/输入/列表/树/编辑器/图像/容器/动画/向导/工具条/导航）| `C:\user\Thirdpart\jvcl\run\` |
| SynEdit | GDI（默认）/Direct2D（SynDWrite）| 代码编辑器 + 50+ 高亮器 | `C:\user\Thirdpart\SynEdit\Source\` |
| VirtualTreeView | GDI/GDI+/Direct2D（多后端）| 虚拟树/网格 | `C:\user\Thirdpart\virtualtreeview\Source\` |
| cnvcl | GDI 自绘 | 皮肤控件 + 停靠控件 | `C:\user\Thirdpart\cnvcl-master\Source\Skin\`、`Source\NonVisual\` |
| picshow | GDI 自绘 | 图像过渡显示 | `C:\user\Thirdpart\picshow\` |
| RxLib v2.75 | GDI | 经典 UI 控件增强（按钮/输入/列表/标签/计算器）| `C:\user\Thirdpart\RxLib v2.75\units\` |
| IOComp v404Sp2 | GDI+ | 工业仪表（仪表盘/LED/数码管/示波器）| `C:\user\Thirdpart\IOComp v404Sp2\Source\` |
| Image32-main | 自绘 | 图像处理 + 实验性 UI 控件 | `C:\user\Thirdpart\Image32-main\source\`、`Examples\Experimental\` |
| RVMedia 93FS | GDI 自绘 | 摄像头/视频显示 | `C:\user\Thirdpart\RVMedia 93FS\Source\` |

---

## 附录 C：开关类控件何时需要探针流程

当控件满足以下任一条件时，**不要直接 click 控件中心**，应走 §2.1 的"开关类控件黑盒点击探针流程"：

| 条件 | 示例控件 |
|------|---------|
| 击中区域是滑块/旋钮本身，点击控件中心命中滑块但不切换 | TToggleSwitch / TJvSwitch / TiSwitchSlider / TiSwitchRotary |
| 控件是"开关"语义但渲染为旋钮/拨杆/把手等可拖动元素 | TiSwitchToggle / TiSwitchPanel |
| 同组互斥切换的 SpeedButton，点击中心可能命中装饰区而非有效点击区 | TSpeedButton（GroupIndex>0，Flat=True） |
| 自绘开关控件，无标准击中区域定义 | TCheckboxCtrl / TRadioBtnCtrl（Image32 实验性） |
| 不同 Delphi 版本/主题下左右↔On/Off 对应关系不固定 | TToggleSwitch（VCL 风格 vs 平台风格） |

**不需要探针的开关类**（控件中心即有效点击区，可直接 click）：

- TCheckBox / TRadioButton（标准 VCL，中心命中文字或勾选框都触发）
- TBitBtn / TButton（中心即响应区）
- TButtonedEdit 的左右按钮（用 textbounds 定位按钮图标位置后 click）

## 附录 D：何时不用 textbounds

| 场景 | 改用 |
|------|------|
| 控件是 TCollection 派生（TListBox/TTreeView/TPageControl 等）且要点击项 | `click ControlName@ItemCaption`（RTTI 项点击，更可靠） |
| 控件文本是 published 属性且要验证内容 | `rget`（更精确，微秒级） |
| 控件是 TImage/TShape/TBevel/TAnimate（无文本） | 不用 textbounds，无文本可拦截 |
| 控件是 DirectUI/WPF/UWP/Electron/WebView/Qt | `uia.*` 或 `capture + daofy_ocr` |
| 控件用 Direct2D/DirectWrite 渲染（如 SynDWrite 启用的 SynEdit） | `uia.*` 或黑盒 `key`+`type`（如 Ctrl+G GotoLine → 输入行号 → Enter）；灰盒 `rcall` |
| 控件是非 GDI/GDI+ 自绘（Image32 实验性） | `capture + daofy_ocr`；灰盒 `rset/rcall` |
| TMemo/TRichEdit WordWrap 且末行多视觉行 | mode=auto（type-bound 末行用 `GetTextMetrics` 单行高，多视觉行仅覆盖首视觉行） |
| TCheckListBox 项点击 | mode=auto（type-bound 不命中 TCheckListBox） |
| TListView 子列文本 | mode=auto（type-bound 仅匹配 Caption） |
| TTreeView 折叠状态下点击子节点 | mode=auto（type-bound 不过滤展开状态） |

---

## 附录 E：何时不用 rget/rset/rcall

| 场景 | 改用 |
|------|------|
| 黑盒测试且属性是用户可见行为 | `click`/`type`/`key`（模拟真实用户操作） |
| 控件是 published 之外的状态（自绘内容） | `textbounds` + `click` 或 `capture + OCR` |
| 控件是其他进程（系统对话框/第三方应用） | `uia.*` 命令 |
| 控件正在动画过程中 | `waitfor` 等动画结束再操作 |
| 控件 Enabled=False 但要测禁用状态 | `rget Enabled` + 断言 False，不要尝试 click |
| 跨平台脚本（FMX 在非 Windows 平台） | DaofyAutomation 仅 Windows 支持，FMX 跨平台需用 OS 级 UIA 工具或 Playwright，不能用 `rset/rcall` 替代黑盒操作 |
