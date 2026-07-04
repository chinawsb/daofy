<!-- @when: 需选择 RTTI 还是 OCR 做验证时 -->

# RTTI vs OCR 决策矩阵

MCP resource URI: `delphi://automation/rtti-ocr-matrix`。

RTTI = 功能性验证（数据是否正确？）——精确、微秒级
OCR = 视觉完整性验证（显示是否正确？）——百毫秒级，反映用户真实所见
capture = 证据留存——截图，人工可回溯

两者互补，不是替代。操作后用 `rget` 确认数据状态，关键节点用 `capture+OCR` 验证视觉呈现。

> 当前版本 OCR 仅支持文字识别，不支持颜色/字体/格式检测。

| 场景 | 推荐 | 原因 |
|------|------|------|
| 读取 Edit 输入值 / 按钮可用 / 标签标题 | `rget(Text/Enabled/Caption)` | 精确、微秒级 |
| 文本截断/省略/换行 | `rget` + `OCR` | RTTI 读完整值，OCR 确认视觉截断 |
| HDPI/缩放测试 | `capture` + `OCR` | RTTI 不知道渲染后控件是否错位/截断 |
| Placeholder 水印文字 | `OCR` | RTTI 返回空 Text，OCR 看到提示文字 |
| Grid/List 单元格 | `OCR` | RTTI 知道 Items/DataSource，但不知每格显示值 |
| WebView / 浏览器内容 | `OCR` | RTTI 完全看不到 HTML 渲染结果 |
| Tooltip 提示 | `OCR` | RTTI 只能读 Hint 字面值 |
| 国际化/本地化验证 | `OCR` | 检查翻译后文字是否截断、CJK 是否显示为方框 |
| 报表/打印预览 | `OCR` | RTTI 看不到报表引擎的渲染输出 |
| 动画/过渡状态 | `capture` + `OCR` | RTTI 不知道视觉动画进度 |
| 自定义绘制/第三方控件 | `OCR` | 非 Delphi 控件，无 RTTI |
| 错误弹窗内容 | `msgscan` | 精确获取弹窗标题+文本 |
| UI 结构分析 | `dumpstate` / `formsum` | 精确的控件树 + 属性 |
| 整体 UI 快照 | `capture` | 截图留存 |

## 决策树

```
验证目标是什么？
  ├─ 功能性验证（数据/状态是否正确？）
  │  ├─ 属性通过 published 暴露？ → rget
  │  └─ 弹窗内容 → msgscan
  ├─ 视觉完整性验证（用户看到文字是否正确？）
  │  ├─ 文本截断/省略/换行 → rget + OCR 双重验证
  │  ├─ HDPI/缩放 → capture + OCR
  │  ├─ 布局错位/重叠 → capture + OCR
  │  └─ CJK 显示异常（方框□） → OCR
  ├─ 复杂控件内容（RTTI 够不到的显示层）
  │  └─ Grid/WebView/报表/Tooltip/ActiveX → OCR
  ├─ 运行时文字变化
  │  └─ 动画进度/Placeholder/国际化截断 → capture + OCR
  └─ 证据留存 → capture
```

## 典型 HDPI 测试流程

1. 100% 缩放下 capture 基线截图
2. 切换到 150%/200% 缩放
3. 同样操作后 capture + OCR
4. 对比：文字是否截断？按钮文案是否完整？布局是否完整？
5. RTTI 辅助：rget Left/Top/Width/Height 确认控件尺寸缩放