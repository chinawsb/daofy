<!-- @when: 需要自动化测试提示词模板时 -->

# 自动化测试提示词模板

以下模板供 AI 在自动化测试各阶段直接套用，将 `{变量}` 替换为实际值。

MCP resource URI: `delphi://automation/prompts`。

## F0. 系统角色与思维框架

> **角色注入**：调用 MCP prompt `automate-expert-primer` 即可注入完整「Delphi UI 自动化测试专家」角色（含三层递进思维模型 + 角色边界），无需在此展开。
>
> 调用方式：`prompts/get automate-expert-primer`，参数：`app_name`, `project_path`
>
> 角色边界：仅用于自动化测试阶段。测试完成后角色自动切回 Delphi 开发专家。

---

## F1. 测试规划模板

```
== 测试规划 ==

**目标**: {测试目标描述}
**前置条件**: {当前应用状态}

**① 检索经验**
experience(action="search", query="{场景关键词}", top_k=3)
- 有匹配 → 参考其工具选择、失败模式、恢复策略
- 无匹配 → 按默认策略规划

**② 感知当前状态**
- listwnd → 确认窗口列表
- dumpstate / capture → 获取 UI 结构和截图
- msgscan → 检查残留弹窗

**③ 规划步骤序列**

| # | 阶段 | 工具 | 目标 | 预期结果 | 超时 | 失败处理 |
|---|---|------|------|---------|------|---------|
| 1 | perceive | listwnd+dumpstate | 获取初始状态 | 主窗口已打开 | 5s | 上报 |
| 2 | execute | goto+click | 点击按钮X | 对话框打开 | 10s | capture→msgscan→分析 |
| 3 | verify | waitfor+capture | 确认对话框 | 控件Y可见 | 5s | 降级RTTI |

**④ 执行循环**
严格 感知→执行→验证 每步循环，失败即停。
```

## F2. 单步执行协议

每步操作严格按四段式执行：

```
┌─ ① 前置感知 ──────────────────┐
│ msgscan：检查弹窗（每步前必做） │
│ capture/dumpstate：确认当前状态 │
│ 确认上一步验证已通过            │
└────────────────────────────────┘
          ↓
┌─ ② 执行 ──────────────────────┐
│ 调用目标工具/命令               │
│ 同步命令 → 检查返回码和结果     │
│ 异步命令 → 记录操作已发送       │
└────────────────────────────────┘
          ↓
┌─ ③ 等待 ──────────────────────┐
│ 异步命令 → wait(500~2000ms) /  │
│   waitfor(控件, 超时=10000)     │
│ 同步命令 → 跳过等待             │
└────────────────────────────────┘
          ↓
┌─ ④ 验证 ──────────────────────┐
│ msgscan：确认无意外弹窗         │
│ capture/rget/ocr：确认结果符合  │
│ 一致 → 标记完成，继续下一步     │
│ 不一致 → 转入失败恢复模板(F3)   │
└────────────────────────────────┘
```

**模板化提交**：
```
[步骤{N}] 阶段=perceive|execute|verify
工具={tool} 参数={params}
预期={expected}
前置感知: {msgscan/dumpstate/capture 结果}
执行结果: {工具返回}
等待结果: {waitfor/wait 结果}
验证结果: {一致/不一致，差异描述}
```

## F3. 失败恢复模板

```
**失败恢复 — 步骤{N}**

**失败信号**: {超时/返回值错误/弹窗/OCR不匹配...}
**预期**: {expected}
**实际**: {actual}

**① 诊断**
- capture 当前状态（截图留存）
- dumpstate 获取当前控件树
- msgscan 检测弹窗
- 分析差异原因：操作未生效？弹窗干扰？时序问题？控件变化？

**② 决策**
| 条件 | 恢复策略 |
|------|---------|
| 弹窗干扰 | msgclick(OK/Cancel) → 重试原操作 |
| 控件不可见 | dumpstate 查替代路径 → 修正 goto |
| 超时但无错误 | 增加 waitfor 时间 → 重试 |
| 可用 RTTI | 黑盒先修 UI 路径；灰盒诊断可用 rcall/rset |
| 确定性失败 | 上报（记录到经验库） |

**③ 恢复执行**
{选择的恢复策略 + 具体操作}

**④ 学习记录**
保存到经验库：
- problem: "{场景} — {失败原因}"
- solution: "{恢复策略} — {应用/版本} 上有效"
- tags: ["automation", "{app_name}", "{failure_type}"]
```

## F4. 经验保存模板

```
**经验保存**

**场景**: {测试用例名称}
**应用**: {应用名/版本}
**执行概况**: 总步骤数 N，成功 N，失败+恢复 N，不可恢复 N，耗时 Xs

**成功模式**（哪些工具/命令组合效果好）:
- 工具组合: {如 "goto+click 配合 waitfor 稳定"}
- RTTI 使用: {如 "灰盒诊断用 rcall 定位，黑盒脚本保持真实 UI 操作"}

**失败模式**（哪些操作容易出问题，如何恢复）:
- {失败描述}: {原因} → {恢复方式} → {是否可自动化恢复}

**优化建议**:
1. {建议1}
2. {建议2}

**保存**:
experience(action="save", problem="{场景关键词}", solution="{核心做法}", tags=["automation", "{app_name}"])
```

## F5. MCP Prompt 一览

| Prompt | 用途 | 参数 | 对应 F 节 |
|--------|------|------|-----------|
| `automate-expert-primer` | 注入测试专家角色 | `app_name`, `project_path` | F0 |
| `automate-code-analysis` | 代码感知分析 | `form_name`, `project_path`, `app_path` | H |
| `automate-test-plan` | 完整测试规划 | `goal`, `app_path`, `project_path` | F1 |
| `automate-step-execute` | 单步执行协议 | `phase`, `tool`, `target`, `expected` | F2 |
| `automate-failure-recover` | 失败恢复 | `signal`, `expected`, `actual` | F3 |
| `automate-save-experience` | 保存经验到知识库 |（无参数）| F4 |
| `automate-session-end` | 结束会话 | `save_experience`, `export_script` | — |

> 所有 prompt 通过 `prompts/get <prompt_name>` 调用。部分需前置参数，建议调用前阅读对应 F 节。