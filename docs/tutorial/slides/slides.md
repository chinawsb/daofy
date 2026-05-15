# Delphi MCP Server
## AI 辅助 Delphi 开发完全指南

---

## 目录

1. 什么是 MCP？
2. Delphi MCP Server 能做什么？
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

## Delphi MCP Server 功能全景

| 模块 | 功能 |
|------|------|
| 🔧 编译 | 项目编译、语法检查、批量编译 |
| 📚 知识库 | 30 万函数、16 万页面索引 |
| 🎨 格式化 | pasfmt 集成 + 自动备份 |
| 📋 编码规范 | 规范驱动代码生成与审计 |
| 📦 组件管理 | 编译安装 .dpk 组件包 |

---

## 安装流程

**用户只需：**

```
用户: 帮我安装 Delphi MCP Server
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
④ 生成代码 + 编译验证
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

## 代码格式化 + 自动备份

**格式化前自动备份：**

```
源文件                 __history/
DataProcessor.pas  →  DataProcessor.pas.~1~
                       DataProcessor.pas.~2~  (自动递增)
```

**备份管理：**
- 查看备份列表
- 对比差异
- 从备份恢复

> 💡 与 Delphi IDE 的 History 机制兼容

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
2. 📝 逐文件修改
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
① get_coding_rules     → 获取规范
② delphi_kb(TJSON*)    → 搜索 API 确认签名
③ 生成代码             → 编码规范 + API 定义
④ compile_project      → 编译验证
⑤ format_delphi        → 格式化 + 备份
⑥ get_coding_rules     → 审计
⑦ 审计报告 → GitHub Issue
```

> 💡 全程在 AI 对话中完成，你做决策、AI 执行

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
| 🔧 编译 | 编译 + 诊断 + 批量 |
| 📚 KB 搜索 | 精确 + 语义 + 引用 |
| 🎨 格式化 | pasfmt + 自动备份 |
| 📋 规范 | 驱动生成 + 驱动审计 |
| 🛡️ 安全 | 备份 + 恢复 |
| 📦 组件 | 编译 + 安装 |
| 🤖 自动化 | 重构 + 修复 + 工单 |

---

## 开源信息

**GitHub**: [github.com/chinawsb/delphi-complier-mcp-server](https://github.com/chinawsb/delphi-complier-mcp-server)

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
