# Daofy 教程素材

本目录包含录制教程所需的所有演示素材，按场景组织。

---

## 目录结构

```
docs/tutorial/
├── tutorial_script.md         ← 完整演示脚本（主脚本）
├── README.md                  ← 本文件（素材索引）
│
├── demo-project/              ← 场景 4.5 / 4.7 / 5.4 / 4.11
│   ├── DemoApp.dproj          # 示例 Delphi 项目文件
│   ├── DemoApp.dpr            # 程序入口
│   ├── MainForm.pas           # 主单元（使用 JsonConfigManager）
│   ├── JsonConfigManager.pas  # JSON 配置管理器（完整实现）
│   └── CODING_RULES.mdc       # 项目编码规范（现代风格）
│
├── legacy-project/            ← 场景 4.11 编码规范对比
│   ├── LegacyApp.dproj        # 占位项目文件（用于 project_path 参数）
│   └── CODING_RULES.mdc       # 旧项目编码规范（匈牙利命名/4空格/行尾begin）
│
├── review-demo/               ← 场景 4.7 代码审计
│   └── LegacyData.pas         # 含 5 类故意问题的代码（无提示注释）
│
├── refactor-demo/             ← 场景 4.9 多文件重构
│   ├── DataProcessor.pas      # 用 TStringList 做数据解析
│   ├── ConfigManager.pas      # 用 TStringList 管理配置
│   └── UserManager.pas        # 用 TStringList 管理用户
│
├── compile-error-demo/        ← 场景 5.3 复杂编译错误诊断
│   ├── ErrorCode.pas          # 未提供比较器的 TDictionary 泛型错误
│   └── ErrorCode_Fixed.pas    # 修复后的参考版本（录制者对照用）
│
├── database-demo/             ← 场景 4.4 知识库驱动代码生成
│   └── DatabaseManager.pas    # AI 生成的 FDConnection + SQLite 管理单元
│
├── group-project/             ← 场景 4.12 批量多项目编译
│   ├── ProjectGroup.groupproj # 项目分组文件
│   ├── LibProject/            # 公共库项目（先编译）
│   │   ├── LibUtils.dproj
│   │   ├── LibUtils.dpr
│   │   └── LibUtils.pas
│   └── AppProject/            # 应用项目（后编译，依赖 LibProject）
│       ├── MainApp.dproj
│       ├── MainApp.dpr
│       └── MainApp.pas
│
├── employee-input/            ← 场景 4.5 FireDAC SQLite 员工信息录入
│   ├── EmployeeInput.dproj    # FireDAC SQLite 项目
│   ├── EmployeeInput.dpr      # 程序入口
│   ├── Form.Main.pas          # 主窗体（DBGrid + DBEdit 详情面板）
│   └── Form.Main.dfm          # 窗体布局（左右分栏）
│
├── test-project/              ← 场景 4.6 单文件语法检查/run_verify 验证
│   ├── TestProject.dproj      # 简洁 VCL 项目
│   ├── TestProject.dpr
│   ├── Unit1.pas
│   └── Unit1.dfm
│
├── test-verify-crash/         ← 场景 run_verify 崩溃检测演示
│   ├── TestCrash.dproj        # FormCreate 抛出异常
│   ├── TestCrash.dpr
│   ├── MainForm.pas
│   ├── MainForm.crash.dproj.bak
│   ├── Form.MainForm.pas
│   └── Form.MainForm.dfm
│
└── workflow-demo/             ← 场景 5.4 完整工作流
    ├── config.json            # JSON 示例配置文件
    └── IniConfigManager.pas   # INI 读写单元
```

---

## 场景对照表

| 场景 | 素材 | 威力点 |
|------|------|--------|
| 4.3 语义搜索发现隐藏 API | — | 30 万函数中自然语言匹配 |
| 4.4 知识库驱动复杂代码生成 | `database-demo/DatabaseManager.pas` | AI 查 KB 确认 FDConnection 签名后生成 |
| 4.5 编译项目 | `demo-project/DemoApp.dproj` | 一键编译 |
| 4.6 单文件语法检查 | `demo-project/MainForm.pas` | 快速检查 |
| 4.7 编码规范驱动审计 + 创建工单 | `review-demo/LegacyData.pas` | 逐条对照规范审查 + 自动创建 Issue |
| 4.8 引用查询 | `refactor-demo/*.pas` | 评估修改影响 |
| 4.9 多文件重构 | `refactor-demo/*.pas` | TStringList → TArray\<String\> |
| 4.10 代码格式化 + 自动备份 | `refactor-demo/*.pas` | pasfmt 格式化 + `__history` 版本备份 |
| 4.11 编码规范控制 AI 行为 | `demo-project/CODING_RULES.mdc` + `legacy-project/CODING_RULES.mdc` | 同需求→不同规则→不同代码风格 |
| 4.12 批量多项目编译 | `group-project/ProjectGroup.groupproj` | 自动处理依赖顺序 |
| 5.1a 构建文档 KB | — | 16 万页 CHM 索引 |
| 5.1b 文档 KB 实战搜索 | — | 自然语言搜帮助文档 |
| 5.2 安装组件包 | — | 编译注册 .dpk |
| 5.3 复杂编译错误诊断 | `compile-error-demo/ErrorCode.pas` | KB 查泛型约束 → 根因修复 |
| 5.4 完整从 0 到 1 工作流 | `demo-project/*` | 规范→API→编码→编译→审计→工单 |

---

## 关键场景详解

### `compile-error-demo/` — 复杂编译错误诊断

**错误**：`E2511 Type parameter 'TCustomKey' must have a comparer`

**根因**：`TDictionary<TCustomKey, string>` 的 `TKey` 是 record，没有默认 `IEqualityComparer`。

**AI 的诊断链**：
1. 搜 KB → `TDictionary` 类定义 → 发现泛型约束需要比较器
2. 搜 KB → `TEqualityComparer` 类定义 → 了解如何子类化
3. 生成 `TCustomKeyComparer` + 修改构造函数
4. 重编译通过

`ErrorCode_Fixed.pas` 是修复后的参考版本（录制者对照用，不给 AI 输入）。

### `review-demo/LegacyData.pas` — 5 类故意问题

| # | 问题 | 位置 | 级别 |
|---|------|------|------|
| 1 | TStringList.Create 没有 try/finally | ExportData | 🔴 严重 |
| 2 | for 循环内 Delete 导致跳项 | ProcessItems | 🔴 严重 |
| 3 | 魔法数值（10/1.5/100/0.95） | CalculateTotal | 🟡 警告 |
| 4 | finally 后取值，逻辑脆弱 | GetUserCount | 🟡 警告 |
| 5 | 未使用的局部变量 LValue | ExportData | 🔵 建议 |

> 代码文件**不含任何提示性注释**，问题全部隐藏在逻辑层面。

### `refactor-demo/` — 可重构的模式

三个单元都返回 `TStringList`，适合整体重构为 `TArray<String>`：
- **DataProcessor.pas**: ParseCSV / SplitLines / JoinLines
- **ConfigManager.pas**: LoadConfig / GetSectionNames
- **UserManager.pas**: LoadUsers / GetUserEmails / SortUsers

### `group-project/` — 编译依赖顺序

```
LibProject/LibUtils.dproj → 先编译（输出 .dll/.bpl）
        ↓ 依赖
AppProject/MainApp.dproj → 后编译（引用 LibUtils 单元）
```

`ProjectGroup.groupproj` 的 `<BuildOrder>` 中明确指定了顺序。

---

## 录制前准备清单

- [ ] Python 3.10+ / Git / Delphi IDE 已安装
- [ ] 项目已克隆，依赖已安装，AI 客户端已配置好 MCP Server
- [ ] `demo-project/` 复制到本机可编译路径
- [ ] `.dproj` 的 `ProjectVersion` 匹配本地 Delphi 版本（21=10.4 / 22=11 / 23=12）
- [ ] 文档知识库已预先构建完成（构建耗时数分钟，建议录前建好）
- [ ] 语义搜索场景需提前构建 embedding：`delphi_kb(action="build_embedding")`
- [ ] Gitea 场景需可访问的 Gitea 实例（如 https://code.qdac.cc:3000）和仓库权限
- [ ] 每个场景录制前确认素材文件在正确目录
