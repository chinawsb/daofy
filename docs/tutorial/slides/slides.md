# Daofy
## 与 AI 共舞 · 享 AI 时代

---

## 目录

1. 什么是 MCP？
2. Daofy 能做什么？
3. 安装（AI 自动）
4. 知识库搜索
5. 编译与格式化
6. AI 辅助开发
7. 高级功能
8. 完整工作流演示

---

## 什么是 MCP？

**Model Context Protocol**

- 由 Anthropic 提出的开放协议
- 让 AI 助手能直接调用本地工具
- 类比：AI 的"USB 接口"

```
AI 助手 ←→ MCP Server ←→ 本地环境
  (Claude等)     (工具)    (编译器/文件系统)
```

---

## MCP 解决了什么问题？

**传统 AI 辅助开发：**

```
用户: "帮我编译一下项目"
AI: "请打开命令行，输入 msbuild..."
```

**有了 MCP Server：**

```
用户: "帮我编译一下项目"
AI: ✅ 编译成功 (调用 MCP 工具)
```

AI 从"给建议"变成"帮你做"。

---

## Daofy 功能全景

| 模块 | 功能 |
|------|------|
| 🔧 编译 | 项目编译、语法检查、批量编译 |
| 📚 知识库 | 30 万函数、16 万页面索引 |
| 📝 文件操作 | 读/写/格式化/备份 一站集成（含 pasfmt） |
| 📋 编码规范 | 规范驱动代码生成与审计 |
| 🛡️ 运行时验证 | 编译后自动运行，检测启动崩溃（`run_verify`）|
| 🔍 运行时审计 | 扫描 DFM 组件类，检测遗漏 uses 单元 |
| 📦 组件管理 | 编译安装 .dpk 组件包 |

---

## 安装流程

**用户只需：**

```
用户: 帮我安装 Daofy
```

**AI 自动完成：**
1. ✅ 检查 Python/Git/7-Zip
2. ✅ 克隆 GitHub 仓库
3. ✅ 创建虚拟环境 + 安装依赖
4. ✅ 自动检测 AI 客户端并配置

> 💡 整个过程在对话中完成，无需手动操作

---

## 知识库规模

| 知识库 | 文件数 | 类数量 | 函数数量 | 大小 |
|--------|--------|--------|----------|------|
| Delphi 源码 | 2,798 | 163,737 | 300,228 | 260 MB |
| 三方库 | 1,800 | 5,724 | 28,801 | 27 MB |
| 文档 (CHM) | 160,328 | — | — | 1,306 MB |

**总计：近 17 万类、33 万函数、16 万文档页面**

---

## 知识库搜索

| 搜索方式 | 用法 | 示例 |
|----------|------|------|
| 🎯 精确搜索 | 已知类名/函数名 | `TStringList`, `Split` |
| 🔍 语义搜索 | 自然语言描述 | "JSON 深度比较" |
| 🔗 引用查询 | 查谁引用了某单元 | `Vcl.Forms` 被哪些文件引用 |

> 搜索策略：先猜精确名 → 再语义兜底

---

## 语义搜索 — 发现隐藏 API

**场景：你不知道 API 叫什么**

```
用户: Delphi 有没有可以比较两个 JSON 对象
      是否结构相同的功能？
```

**传统方式**：翻 CHM / Google / StackOverflow

**AI + KB 方式**：
1. 语义搜索 30 万函数
2. 命中 `TJSONObject.Equals`
3. 确认签名 → 直接使用

---

## 知识库驱动代码生成

**场景：用 FireDAC 连接 SQLite**

```
用户: 帮我写一个 SQLite 数据库管理单元
```

**AI 的工作流：**

```
① get_coding_rules()    → 获取规范
② delphi_kb(TFDConnection) → 查 API 签名
③ delphi_kb(TFDQuery)      → 查参数绑定
④ file_tool(action="write") → 生成代码（自动备份）
⑤ compile_project           → 编译验证
```

> 💡 不是凭记忆写，而是先查 KB 确认 API

---

## 编译功能

| 能力 | 说明 |
|------|------|
| 项目编译 | .dproj / .dpr → exe/dll |
| 单文件检查 | .pas 语法检查 |
| 批量编译 | .groupproj → 按依赖顺序 |
| 多平台 | Win32/Win64/OSX/iOS/Android/Linux |
| 配置 | Debug / Release + 自定义选项 |

---

## 复杂编译错误诊断

**示例：E2511 must have a comparer**

```
TDictionary<TCustomKey, string>  // 编译错误！
```

**AI 的诊断链：**
1. 搜索 KB → `TDictionary` 泛型约束
2. 搜索 KB → `TEqualityComparer` 基类
3. 根因：record 类型无默认比较器
4. 生成 `TCustomKeyComparer` → 修复 → 编译通过

---

## 统一文件操作 + 自动备份

**一体化的文件接口 `file_tool`：**

```
file_tool(action="read")              — 读文件（DFM 二进制→文本自动转换）
file_tool(action="write", content=...) — 写文件（默认 backup=True，自动备份到 __history）
file_tool(action="format")            — 格式化（pasfmt 驱动，自动备份）
file_tool(action="backup")            — 备份管理（创建/列表/恢复）
```

**写入即备份 — 无需额外步骤：**

```
file_tool(action="write", file_path="Unit1.pas", content="...")
                              ↑ 默认 backup=True，自动创建 __history 备份
```

**备份机制：**

```
源文件                 __history/
DataProcessor.pas  →  DataProcessor.pas.~1~
                       DataProcessor.pas.~2~  (自动递增)
```

**备份管理：**
- 查看备份列表 `backup_action="list"`
- 恢复指定版本 `backup_action="restore", version=3`
- 与 Delphi IDE 的 History 机制兼容

> 💡 旧接口 `read_source_file` / `format_delphi` 已合并到此工具

---

## DFM 二进制文件透明处理

**DFM 表单文件也有二进制格式，传统方式处理麻烦：**

```
读取二进制 DFM → 乱码 → 还得手动转换
编辑后保存 → 格式搞错 → 编译器报错
```

**`file_tool` 透明处理：**

```
file_tool(action="read",  file_path="Form1.dfm")
  → 检测到二进制 → 自动转文本 → 返回可读内容 ✓

file_tool(action="write", file_path="Form1.dfm", content="...")
  → 原文件是二进制 → 写出后自动转回二进制 ✓
```

**原理：按需编译 Delphi 转换器，调用 `ObjectResourceToText` / `ObjectTextToResource`**

> 💡 修改者无需关心 DFM 格式，读写接口一致

---

## 编码规范控制 AI 行为

**同一需求，不同规则 → 不同代码**

```
用户: 写一个字符串工具单元
```

| 维度 | 现代规范 | 旧规范 |
|------|----------|--------|
| 命名 | T + 大驼峰 | 无前缀小驼峰 |
| 参数 | A + 大驼峰 | 匈牙利命名 |
| 缩进 | 2 空格 | 4 空格 |
| begin | 另起一行 | 行尾 |

> 💡 规则不仅是被查询的，更是被执行的

---

## 代码审计 + 创建工单

**审计维度：**
- 🔴 资源泄漏（try/finally）
- 🔴 循环内删除元素
- 🟡 魔法数值
- 🟡 未使用变量
- 🔵 函数过长

**审计结果 → 自动创建 Issue**

```
GitHub Issue / Gitee 工单
├── 标题: LegacyData.pas 代码质量问题
├── 问题清单（含行号/级别/建议）
└── Issue 链接
```

---

## 多文件重构

**场景：TStringList → TArray\<String\>**

```
用户: 把项目中所有 TStringList
      替换为 TArray<String>
```

**AI 工作流：**
1. 🔗 引用查询 → 评估影响范围
2. 📝 逐文件修改（file_tool write 默认自动备份）
3. ✅ 每改一个编译验证
4. 🎨 统一格式化

> 💡 你做决策，AI 执行 + 验证

---

## 批量多项目编译

**场景：编译整个解决方案**

```
ProjectGroup.groupproj
├── LibProject/ (先编译，因为被依赖)
└── AppProject/ (后编译)
```

```
用户: Release / Win64，编译全部
AI: ✅ LibUtils → ✅ MainApp  一键完成
```

> 💡 自动解析 BuildOrder，按依赖顺序编译

---

## 文档知识库实战搜索

**构建后：一句话搜 16 万页帮助文档**

```
用户: TCanvas.Draw 的参数说明，
      特别是 DrawOpacity 的作用
```

```
Result:
DrawOpacity: 绘制不透明度
  0   = 完全透明
  255 = 完全不透明（默认）
```

> 💡 比翻 CHM 快两个数量级

---

## 安装组件包

```
用户: 安装 MyComponent.dpk
```

**AI 完成：**
1. 编译 .dpk
2. 检测是否为设计期包
3. 自动注册到 IDE 注册表

```
用户: 查看已安装的组件包
AI: 列出所有注册的 BPL 包
```

---

## 完整从 0 到 1 工作流

```
需求：JSON 配置文件管理单元
```

```
① get_coding_rules                    → 获取规范
② delphi_kb(TJSON*)                   → 搜索 API 确认签名
③ file_tool(action="write")           → 写入代码（默认自动备份到 __history）
④ file_tool(action="format")          → 格式化代码
⑤ compile_project                     → 编译验证
⑥ compile_project(run_verify=True)    → 运行验证（捕获 CreateForm 阶段崩溃）
⑦ get_coding_rules(section="review")  → 审计
⑧ run_audit(mode="runtime")           → 运行时注册检查（遗漏 uses 检测）
⑨ 清理 + 确认备份
```

> 💡 重建前先检查现有帮助文档目录，避免重复构建

---

## 运行时启动崩溃检测

**CreateForm 阶段的异常，.dpr 的 try/except 抓不到**

```
Application.CreateForm(TMainForm, MainForm); // ← 异常被 VCL 内部吃掉
```

**方案：TStackTraceManager**

```
StackTrace.pas
├── TStackTraceManager (singleton)
│   └── 挂钩 RTL Exception.GetExceptionStackInfoProc
│       → 异常 raise 时刻立即捕获（不依赖 try/except）
├── TDefaultExceptionLogger
│   └── 写入 exception.log（UTF-8 BOM）
└── ParseMapFile
    └── 解析 .map 文件 → 函数名 + 行号
```

---

## run_verify 工作流

```
compile_project(run_verify=True)

① inject_verify_units()
   ├── 备份 .dproj / .dpr
   ├── 注入 DCCReference + DCC_UnitSearchPath
   └── 注入 TStackTraceManager 初始化

② 重新编译（带 StackTrace.pas）

③ 启动 exe 运行 5 秒

④ 检查 exception.log
   ├── 存在 → detect_encoding 读取 → 嵌入 MCP 响应
   └── 不存在 → ✅ 验证通过

⑤ 恢复原始 .dproj / .dpr
```

**示例输出：**
```
❌ 运行验证失败 - 检测到异常:
[2026-05-25 13:02:46] Exception: 测试异常: 模拟启动崩溃
  Vcl.Forms.TCustomForm.DoCreate+$37 [Vcl.Forms.pas:4160]
  TestCrash.TestCrash+$55 [TestCrash.dpr:16]
```

---

## 运行时注册检查

**编译通过 ≠ 运行正常** — 组件运行时注册可能缺失

```
run_audit(mode="runtime", source_dir=...)
```

**检查原理：**
```
src/rules/runtime_registry.json 规则表
├── "TFDQuery" → 需要 FireDAC.DApt
├── "TFDMemTable" → 需要 FireDAC.DApt  
├── "TChart" → 需要 VCLTee.TeEngine
└── ...
```

**扫描流程：**
```
① 扫描 .pas/.dfm 中组件类名
② 匹配规则表
③ 检查 uses 子句中是否包含必需单元
④ 报告缺失项
```

**零配置扩展：** 新增规则只需编辑 JSON 文件，无需改代码

---

## 示例：FireDAC SQLite 员工信息录入

**从头重建的演示项目 `employee-input/`：**

```
employee-input/
├── EmployeeInput.dproj   # FireDAC SQLite 项目
├── Form.Main.pas         # 主窗体 130 行
├── Form.Main.dfm         # 左右分栏布局
└── Win32/Debug/          # 编译输出
    ├── EmployeeInput.exe # 3.8 MB 代码
    └── employees.db      # 首次运行自动创建
```

**关键点：**
- `TFDPhysSQLiteDriverLink` + `TFDConnection` → 自动建表
- SQLite DB 自动创建在 exe 同级目录
- DBGrid 列表（只读）+ DBEdit 编辑面板（左右分栏）
- UTF-8 BOM 编码 — 消除 `W1057` 隐式字符串转换警告
- `compile_project(run_verify=True)` — 编译 → 运行验证 一键通过

---

## 支持平台

| AI 助手 | 配置方式 |
|---------|----------|
| Claude Desktop | 自动 / 手动 |
| Trae | 自动 |
| CodeArts Agent | 自动 |
| Cursor | 自动 / 手动 |
| Windsurf | 自动 |
| 通义灵码 | 自动 |
| 豆包 | 自动 |
| Kimi | 自动 |
| 更多... | install.ps1 自动检测 |

---

## 总结

| 能力 | 一句话 |
|------|--------|
| 🔧 编译 | 编译 + 诊断 + 批量 + run_verify |
| 📚 KB 搜索 | 精确 + 语义 + 引用 |
| 📝 文件操作 | 读/写/格式化/备份一站集成（含 pasfmt） |
| 📋 规范 | 驱动生成 + 驱动审计 |
| 🛡️ 运行验证 | 启动崩溃检测 + 运行时注册审计 |
| 📦 组件 | 编译 + 安装 |
| 🤖 自动化 | 重构 + 修复 + 工单 |

---

## 开源信息

**GitHub**: [github.com/chinawsb/daofy](https://github.com/chinawsb/daofy)

**许可证**: MIT

**技术栈**: Python 3.10+ / MCP Protocol

**交流方式**: GitHub Issues

---

## Q&A

**感谢观看！**

如果您觉得有用，请给项目点个 Star ⭐

---

# 附录：演示准备清单

## 录制前准备
- [ ] Python 3.10+ / Git / Delphi IDE 已安装
- [ ] 项目已克隆 + 依赖已安装
- [ ] AI 客户端已配置 MCP Server
- [ ] 文档知识库已预先构建
- [ ] 所有演示素材在正确目录

## 关键操作提示
- 安装部分全程 AI 对话，不展示终端
- 复杂场景建议画中画显示 VS Code
- 审计结果展示时停留 2-3 秒
- 构建文档 KB 等耗时操作提前完成或加速
