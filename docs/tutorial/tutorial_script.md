# Daofy 使用教程 — 录制演示脚本

**总时长**: 约 45-50 分钟  
**目标受众**: Delphi 开发者（了解基本 Delphi 开发，初次接触 MCP/AI 辅助编程）  
**录制工具建议**: OBS Studio / Bandicam / ScreenFlow  
**屏幕分辨率建议**: 1920×1080 或更高  
**剪辑建议**: 安装和构建知识库等耗时步骤可加速播放或剪辑跳过

---

## 第一部分：开场 & 项目介绍（约 2 分钟）

### 画面
- 全屏展示 GitHub 项目页面：<https://github.com/chinawsb/daofy>
- 镜头切到 PPT / 项目 README

### 旁白脚本

大家好，欢迎收看本期教程。

今天给大家介绍一个非常实用的工具——**Daofy**。

MCP 全称是 Model Context Protocol，由 Anthropic 公司推出的一种开放协议。它让 AI 助手（比如 Claude、CodeArts Agent 等）能够直接与你的本地开发环境交互。

简单来说：**装了 Daofy 之后，你可以在 AI 助手的聊天对话中，直接编译 Delphi 项目、搜索 VCL/FMX 源码、查询 API 文档、甚至格式化代码。**

不用在 AI 和 IDE 之间来回切换。一条指令下去，AI 调用 MCP 工具帮你完成。

我们看看这个项目能做什么：

- ✅ **编译 Delphi 项目** — 支持 .dproj / .dpr / .pas 文件
- ✅ **知识库搜索** — 内置 Delphi RTL/VCL/FMX 源码索引，支持类名、函数名、语义搜索
- ✅ **项目知识库** — 自动索引你项目中的代码和三方库
- ✅ **代码格式化** — 集成 pasfmt，一键格式化 Delphi 源码
- ✅ **编码规范查询** — 获取项目编码规则，让 AI 生成的代码符合你的风格
- ✅ **组件包安装** — 编译并安装 .dpk 组件包到 IDE

好，那我们从安装开始。

---

## 第二部分：AI 自动安装 & 配置（约 4 分钟）

> **设计思路**：整个安装过程不展示终端操作，全部在 AI 对话界面中完成。用户只需说一句话或粘贴一条提示词，AI Agent 自动处理一切。

### 场景 2.1 — 用户向 AI 提出安装需求

#### 画面
- 全屏展示 AI 助手对话界面（如 Claude Desktop / CodeArts Agent）
- 用户输入安装指令

#### AI 对话演示

```
用户: 帮我安装 Daofy
```

或者粘贴 README 中的安装提示词：

```
用户: 请按以下步骤安装 Daofy:

[] 检查并安装 Git/Python 3.10-3.14/7-Zip (安装时优先使用国内镜像源加速下载)

[] 安装 https://github.com/chinawsb/daofy.git

[] 安装完成后验证结果并帮我配置当前客户端
```

#### 旁白

很多第一次接触 MCP 的用户会觉得配置很麻烦——要装 Python、克隆项目、配虚拟环境、还要写 JSON 配置文件。

但在我们这个教程里，**这些全都不需要手动做**。

你只需要在 AI 助手的对话框里，输入一条指令："帮我安装 Daofy"。

AI Agent 收到指令后会：
1. 检查你的电脑上有没有 Python 和 Git
2. 如果没有，自动下载安装
3. 克隆 GitHub 仓库
4. 创建虚拟环境、安装依赖
5. 运行安装脚本，自动检测并配置你的 AI 客户端

所有操作都在对话中由 AI 自动完成，你只需要看着它一步步执行，然后在需要确认的节点回答"是"或者"继续"即可。

---

### 场景 2.2 — AI 逐步执行安装（画中画展示终端）

#### 画面
- 主画面：AI 对话界面，AI 输出安装进度
- **画中画（小窗口）**：实时展示 AI 正在执行的终端命令和输出，让观众看到背后实际在做什么

#### AI 对话输出（示意）

```
AI: 开始安装 Daofy...

第一步: 检查环境...
  ✅ Git 已安装 (2.47.0)
  ✅ Python 已安装 (3.12.4)
  ⚠️ 未检测到 7-Zip，正在自动下载安装... 完成

第二步: 克隆项目...
  ✅ 已从 github.com/chinawsb/daofy 克隆

第三步: 配置虚拟环境并安装依赖...
  ✅ 虚拟环境已创建
  ✅ 依赖安装完成 (使用清华镜像源加速)

第四步: 配置 AI 客户端...
  🔍 正在检测已安装的 AI 助手...
  ✅ 检测到: Claude Desktop, Trae
  ✅ 已自动配置 Claude Desktop
  ✅ 已自动配置 Trae

安装完成! 🎯
现在你可以让我帮你编译 Delphi 项目了。
```

#### 旁白

AI 收到指令后，会按顺序执行安装步骤。

在画中画窗口里，你可以看到 AI 实际上在执行各种终端命令——检查环境、克隆仓库、安装依赖。但对于观众来说，重点看 AI 对话界面的输出就够了，每一步都有清晰的进度和结果。

最厉害的是第四步：AI 会自动检测你电脑上装了哪些 AI 客户端——Claude Desktop、Trae、CodeArts Agent、Cursor、Windsurf、通义灵码、豆包、Kimi 等十几种——然后自动写入 MCP 配置。**完全不需要手动编辑 JSON 文件。**

---

### 场景 2.3 — 验证安装结果

#### 画面
- AI 对话界面继续

#### AI 对话演示

```
用户: 检查一下安装是否成功
```

- AI 调用 `check_environment(action="check")` 工具
- 展示返回结果：编译器版本、路径、可用平台

#### 旁白

安装完成后，输入"检查一下安装是否成功"。

AI 会调用 `check_environment` 工具，自动从 Windows 注册表检测 Delphi 编译器。如果一切正常，你会看到 Delphi 版本号、dcc32 路径、支持的编译平台——**全自动完成，零配置**。

至此，整个安装配置过程不到两分钟，没有离开过 AI 对话框。

---

## 第三部分：环境检测 & 首次启动（约 2 分钟）

### 场景 3.1 — 启动 MCP Server 并检查编译器

#### 画面
- 在 AI 助手的对话界面中，输入指令
- **用分屏或画中画展示 AI 助手界面**

#### AI 对话演示

```
用户: 检查一下 Delphi 编译环境
```

- AI 调用 `check_environment(action="check")` 工具
- 展示返回结果：编译器版本、路径、可用平台等

#### 旁白

启动配置好 MCP Server 的 AI 助手后，我们第一件事就是检查编译环境。

输入"检查 Delphi 编译环境"，AI 就会调用 `check_environment` 工具，自动从 Windows 注册表检测已安装的 Delphi 编译器。

你会看到检测到的 Delphi 版本、dcc32 编译器路径、以及支持的编译平台。**全程无需手动配置。**

---

### 场景 3.2 — 查看知识库统计

#### AI 对话演示

```
用户: 查看 Delphi 知识库统计
```

- AI 调用 `delphi_kb(action="stats")`
- 展示结果：Delphi 源码知识库的文件数、类数量、函数数量

#### 旁白

再来看知识库的状态。输入"查看 Delphi 知识库统计"，AI 会展示内置的 Delphi 源码知识库的规模。

这个知识库已经预先构建好了 Delphi 官方 RTL、VCL、FMX 的源码索引——包含了超过 **16 万文件、16 万类、30 万个函数**的索引，几乎是 Delphi 全系版本的完整覆盖。

---

## 第四部分：核心功能演示（约 22 分钟）

### 场景 4.1 — 搜索 Delphi API 定义（约 2 分钟）

#### AI 对话演示

```
用户: 帮我查一下 TStringList 的类定义
```

- AI 调用 `delphi_kb(query="TStringList", search_type="class", kb_type="delphi")`
- 展示搜索结果：类的继承链、所在单元、关键方法

#### 旁白

先看知识库搜索功能——这是大家日常用得最多的。

比如我想查 `TStringList` 的类定义，只需输入：

AI 会搜索 Delphi 源码知识库，返回 `TStringList` 的完整信息：继承自 `TStrings` → `TPersistent` → `TObject`，在 `System.Classes` 单元中定义，以及有哪些关键方法。

---

### 场景 4.2 — 搜索函数（约 1 分钟）

#### AI 对话演示

```
用户: 查找 Delphi 中 Split 字符串分割函数
```

- AI 调用 `delphi_kb(query="Split", search_type="function", kb_type="delphi")`
- 展示搜索结果：函数签名、参数说明、所在单元

#### 旁白

查找函数也一样简单。

比如说我想找字符串分割函数，输入"查找 Split 函数"，AI 会返回 `System.StrUtils.SplitString` 等匹配的函数，包括参数签名和使用说明。

注意这里我们推荐用英文函数名搜索，比中文语义搜索准确得多。

---

### 场景 4.3 — 语义搜索发现隐藏 API（约 2 分钟）

> **威力点**：你连 API 名字都不知道，用自然语言描述需求，AI 从 30 万+ 函数中找出你想要的。
>
> ⚠️ **前置条件**：语义搜索需要先构建 embedding 向量索引：`delphi_kb(action="build_embedding", async_mode=true)`。未构建时 semantic 模式会降级为倒排索引搜索，效果可能不如预期。录制前请提前构建。

#### AI 对话演示

```
用户: Delphi 里有没有可以比较两个 JSON 对象是否结构相同的功能？
     不是字符串比较，是忽略键顺序的语义比较。
```

- AI 调用 `delphi_kb(query="JSON object deep compare structural equality", search_type="semantic", kb_type="delphi")`
- 30 万函数中匹配到 `System.Json.TJSONObject.Equals` 以及 `System.Generics.Defaults.TEqualityComparer`
- AI 进一步调用 `delphi_kb(query="TJSONObject.Equals", search_type="function", kb_type="delphi")` 确认签名
- 展示结果：`TJSONObject.Equals` 确实实现了值比较而非引用比较

```
用户: 再帮我找一个功能——读取大文本文件时按行处理，但不想一次性加载整个文件到内存。
```

- AI 调用 `delphi_kb(query="read large text file line by line streaming", search_type="semantic", kb_type="delphi")`
- 搜索结果：`System.Classes.TStreamReader.ReadLine`、`System.IOUtils.TFile.ReadAllLines`（但会全加载）
- AI 推荐 `TStreamReader` 方式并展示用法

#### 旁白

这个场景展示的是**语义搜索的真正威力**。

前面我们演示了精确搜索——你知道 `TStringList` 或 `Split` 的名字，直接搜。但现实开发中，你常常遇到的问题是：**"Delphi 有没有做 X 的功能？"**——你连 API 叫什么都不知道。

比如"比较两个 JSON 对象是否相同"——如果用 `=` 运算符比较两个 `TJSONObject`，比较的是引用地址。你想要的其实是值比较。但你不知道这个 API 叫什么名字，甚至不确定 Delphi 有没有提供。

这时候你用自然语言描述需求，AI 在 **30 万个函数**的知识库中做语义匹配，找到 `TJSONObject.Equals`——它确实重写了 `Equals` 方法来做值比较。

再比如"逐行读取大文件，不要一次性加载到内存"。语义搜索能区分 `TFile.ReadAllLines`（全加载）和 `TStreamReader.ReadLine`（流式读取）的区别，给出正确的推荐。

这就是 30 万函数的 Delphi KB + 语义搜索的组合威力——**你不知道名字，但你描述需求，AI 帮你找到**。

---

### 场景 4.4 — 知识库驱动的复杂代码生成（约 3 分钟）

> **威力点**：AI 搜索 KB 确认 API 签名 → 生成代码 → 一次编译通过。对 FireDAC 这种参数繁多的库尤为强大。

#### AI 对话演示

```
用户: 帮我写一个 SQLite 数据库管理单元，使用 FireDAC 组件，
      要求：
      1. 支持连接配置（文件路径、池大小、超时）
      2. Connect / Disconnect 方法
      3. Execute 方法执行 SQL，支持参数绑定
      4. Query 方法返回数据集
      5. TestConnection 方法
      按项目编码规范来，先去查一下规范。
```

##### 第 1 步：获取编码规范

- AI 调用 `get_coding_rules(section="writing")`

##### 第 2 步：搜索 KB 确认 API 签名（关键！）

- AI 调用 `delphi_kb(query="TFDConnection", search_type="class", kb_type="delphi")` → 了解属性、方法
- AI 调用 `delphi_kb(query="TFDQuery", search_type="class", kb_type="delphi")` → 了解 SQL 赋值、参数绑定
- AI 调用 `delphi_kb(query="TFDPhysSQLiteDriverLink", search_type="class", kb_type="delphi")` → 确认驱动链接用法
- AI 调用 `delphi_kb(query="TFDConnection.Params", search_type="function", kb_type="delphi")` → 确认参数配置方式
- **（画中画展示：AI 在 KB 中查询到的 API 签名片段）**

##### 第 3 步：生成代码

- AI 结合：编码规范 + KB 查到的 API 签名 + 需求 → 生成 `DatabaseManager.pas`
- 代码包含：TDatabaseConfig record、TDatabaseManager class、完整的 try/finally 保护
- **（画中画展示：VS Code 中文件实时生成）**

##### 第 4 步：编译验证

- AI 调用 `compile_project(project_path="DatabaseManager.pas")` → 一次通过 ✅

#### 旁白

前面的 INI 读写示例比较简单，这次我们来个真正有挑战的——**用 FireDAC 连接 SQLite**。

FireDAC 的参数体系非常庞大：`TFDConnection` 的 driver 选择、`Params` 的键值对配置、`TFDQuery` 的 SQL 赋值和参数绑定、驱动链接的创建……手写这些代码时，你通常要去翻帮助或者抄以前的代码。

但 AI 的做法完全不同：

**第一步**，获取编码规范，确定风格。

**第二步，也是关键**——AI 不是凭记忆瞎写，而是调用知识库搜索 `TFDConnection`、`TFDQuery`、`TFDPhysSQLiteDriverLink` 的类定义，**确认真实的 API 签名**。构造函数有几个参数？属性名叫什么？返回值类型是什么？全部从源码 KB 中确认。

**第三步**，结合规范 + 需求 + 查到的 API 定义，生成 `DatabaseManager.pas`。注意它是怎么处理资源释放的——`Create` 中创建、`Destroy` 中释放、`Connect/Disconnect` 的正确配对。

**第四步**，编译验证，一次通过。

关键是 **"先查 KB 确认 API，再写代码"** 的流程——生成的代码不是凭"AI 记忆"瞎猜，而是基于真实的 Delphi 源码定义。对于 FireDAC、Indy、REST 这类参数繁多的库，这比手翻帮助文档快十倍。

---

### 场景 4.5 — 编译 Delphi 项目（约 2 分钟）

#### AI 对话演示

```
用户: 编译当前项目，Debug 模式，Win32 平台
```

- AI 调用 `compile_project(project_path="Project1.dproj", build_configuration="Debug", target_platform="win32")`
- 展示编译过程输出：编译事件、编译参数、编译结果

#### 旁白

接下来是最核心的功能——编译项目。

在 AI 对话中输入"编译当前项目，Debug 模式，Win32 平台"。

AI 会自动找到当前目录下的 .dproj 工程文件，调用 MSBuild 或 dcc32 编译器进行编译。整个编译过程会在聊天窗口中实时输出，包括预处理事件、编译参数、以及最终的编译结果。

如果编译失败，AI 会自动分析错误信息并给出修复建议。

---

### 场景 4.6 — 单文件语法检查（约 1 分钟）

#### AI 对话演示

```
用户: 检查 Unit1.pas 的语法
```

- AI 调用 `compile_project(project_path="Unit1.pas")`
- 展示语法检查结果

#### 旁白

如果你只想检查单个文件的语法，而不是编译整个项目，也非常简单。

输入"检查 Unit1.pas 的语法"，AI 会直接用 dcc32 编译该文件进行语法检查，快速反馈有没有语法错误。

---

### 场景 4.7 — 代码审计 + Gitea 缺陷闭环（约 4 分钟）

> **威力点**：从审计到工单到修复到关闭，全链路在一个 MCP 工具中完成，无需离开 AI 对话。

#### AI 对话演示

##### Phase 1：代码审计

```
用户: 审查一下 review-demo/LegacyData.pas 的代码质量，
      对比项目编码规则，输出审查报告
```

- AI 调用 `get_coding_rules(section="review")` — 获取审核维度和标准
- AI 逐行分析代码，对照编码规则逐项检查：

```
📋 审查报告 — LegacyData.pas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 [严重] ExportData — 资源泄漏风险
  Line 26: TStringList.Create 后没有 try/finally 保护
  若 SaveToFile 抛出异常，LFile 永远不会被 Free
  建议: 使用 try/finally 包裹

🔴 [严重] ProcessItems — 循环内删除导致跳项
  Line 82: for 循环中执行 AItems.Delete(I)
  删除后后续元素前移，I++ 会跳过一个元素
  建议: 改为倒序遍历 for I := Count-1 downto 0

🟡 [警告] CalculateTotal — 魔法数值
  Line 62: 循环上限 10 应定义为常量
  Line 64: 因子 1.5 应定义为常量
  Line 66: 阈值 100 应定义为常量
  Line 68: 折扣率 0.95 应定义为常量

🟡 [警告] GetUserCount — 逻辑错误
  Line 49: LCount 在 try 块中赋值
  Line 53: LFile 已在 finally 中释放后返回 LCount
  当前代码正确，但模式危险 — 容易在修改时出错
  建议: 直接在 try 块中赋值给 Result

🔵 [建议] ExportData — 未使用变量
  Line 24: LValue 声明了但只使用一次
  建议: 直接内联 'data1;data2;data3'
```

##### Phase 2：一键创建 Gitea 工单

```
用户: 把严重问题创建为 Gitea 工单，连接到 https://code.qdac.cc:3000，
      仓库 myteam/demo-project
```

- AI 调用 `code_hosting(platform="gitea", action="create_token", base_url="https://code.qdac.cc:3000", username="...", password="...")` → 获取 API Token（首次使用）
  ```
  ✅ Token 创建成功
    值: 93f2c9e8...a083
  ```

- AI 调用 `code_hosting(platform="gitea", action="init_labels", base_url="...", token="...", repo="myteam/demo-project")`
  → 初始化四维标签体系（可重复执行，不会重复创建）
  ```
  ✅ 标签初始化完成
    新增: 18 | 跳过(已有): 18 | 合计: 18
    分组: 优先级(4) 审阅(4) 状态(5) 类型(5)
  ```

- AI 调用 `code_hosting(platform="gitea", action="create_issue", base_url="...", token="...", repo="myteam/demo-project",
     title="LegacyData.pas 代码质量审计问题",
     body="""## 发现的问题

### 🔴 严重
1. 资源泄漏风险 — ExportData:26
   TStringList.Create 没有 try/finally 保护
2. 循环内删除导致跳项 — ProcessItems:82

### 🟡 警告
3. 魔法数值 — CalculateTotal:62-68
4. 逻辑错误风险 — GetUserCount:49-53""",
     label_names=["类型/缺陷", "优先级/高", "状态/待确认"])`
  ```
  ✅ 工单已创建
    编号: #42 | 状态: open
    标签: 类型/缺陷, 优先级/高, 状态/待确认
    地址: https://code.qdac.cc:3000/myteam/demo-project/issues/42
  ```

##### Phase 3：修复代码

```
用户: 按照审计建议修复代码
```

- AI 读取 `LegacyData.pas` 源码
- AI 逐项修复：
  - ExportData: 添加 try/finally 包裹
  - ProcessItems: 改为倒序遍历
  - CalculateTotal: 魔法数值改为常量定义
  - GetUserCount: 简化逻辑
  - ExportData: 删除未使用的 LValue 变量
- AI 调用 `compile_project(project_path="review-demo/LegacyData.pas")` — 编译验证修复后的代码

##### Phase 4：提交修复并关闭工单

```
用户: 提交修复代码，并在工单中关联提交记录后关闭
```

- AI 调用 `code_hosting(action="git_add", work_dir=".", files=["review-demo/LegacyData.pas"])`
- AI 调用 `code_hosting(action="git_commit", work_dir=".", commit_message="fix: resolve code audit issues in LegacyData.pas

- Add try/finally guard to prevent resource leak
- Fix loop index skipping on Delete
- Replace magic numbers with constants
- Clean up unused variable")`
  ```
  ✅ 提交成功
    Hash: a1b2c3d4e5f6
    信息: fix: resolve code audit issues in LegacyData.pas
  ```

- AI 调用 `code_hosting(platform="gitea", action="add_comment", base_url="...", token="...", repo="myteam/demo-project",
     issue_number=42, body="已在 commit a1b2c3d4 中修复所有 5 个问题。")`
  ```
  ✅ 评论已添加 (ID: 14203)  工单: #42
  ```

- AI 调用 `code_hosting(platform="gitea", action="close_issue", base_url="...", token="...", repo="myteam/demo-project",
     issue_number=42, comment_body="已在 a1b2c3d4 中修复，编译通过 ✅")`
  ```
  ✅ 工单 #42 已关闭
    地址: https://code.qdac.cc:3000/myteam/demo-project/issues/42
    关闭说明: 已在 a1b2c3d4 中修复，编译通过 ✅
  ```

##### Phase 5：验证闭环

```
用户: 查一下已关闭的工单，确认修复记录
```

- AI 调用 `code_hosting(platform="gitea", action="list_issues", base_url="...", token="...", repo="myteam/demo-project", state="closed")`
  ```
  📋 共 1 个工单 (gitea, closed):
    #42 [closed] LegacyData.pas 代码质量审计问题  类型/缺陷, 优先级/高, 状态/已关闭
  ```

#### 旁白

这个场景展示的是 **代码审计 → 工单跟踪 → 修复 → 关闭** 的完整闭环，也是 `code_hosting` 统一工具的集中体现。

整个流程拆解为五个阶段：

**Phase 1 — 审计**：`get_coding_rules` 获取规范 → 逐行审查 → 输出结构化报告（含行号、严重级别、修复建议）

**Phase 2 — 工单创建**：`code_hosting` 的四个 action 衔接：
1. `create_token` → 获取 API 访问令牌（仅首次需要）
2. `init_labels` → 初始化四维标签，同 scope 互斥
3. `create_issue` → 创建工单，自动按名称匹配标签 ID
4. 返回的工单链接可直接在浏览器中打开

**Phase 3 — 修复**：AI 根据审计建议逐项修改源码，每处修改针对具体行号，改完后编译验证。

**Phase 4 — 关闭**：修复代码通过 `git_commit` 提交后，通过 `add_comment` 在工单中记录 commit hash，再用 `close_issue` 关闭。**commit 和 issue 之间的关联被保留在 Gitea 的评论中**，后续开发者可以追溯每个问题的修复历史。

**Phase 5 — 验证**：通过 `list_issues` 按状态过滤，确认工单已正确关闭，标签已自动切换为"状态/已关闭"。

关键点：**全部操作通过一个 `code_hosting` 工具完成**，不同的 action 参数切换操作类型。从发现问题到修复关闭，整个生命周期不离开 AI 对话框。这就是 MCP 协议 + 统一工具接口的威力。

---

### 场景 4.8 — 搜索项目代码 & 引用查询（约 2 分钟）

#### AI 对话演示

```
用户: 在项目中搜索 TfrmMain 类
```

- AI 调用 `delphi_kb(query="TfrmMain", kb_type="project", search_type="class")`
- 展示搜索结果

```
用户: 查看项目中哪些单元引用了 Vcl.Forms
```

- AI 调用 `delphi_kb(query="Vcl.Forms", kb_type="project", search_type="reference")`
- 展示引用列表

#### 旁白

项目知识库是另一个非常实用的功能。首次搜索项目代码时，AI 会自动构建项目知识库，索引你项目中的所有源码和三方库。

输入"在项目中搜索 TfrmMain 类"，AI 会在项目知识库中查找这个类的定义位置。

如果你想知道"哪些单元引用了 Vcl.Forms"，使用引用搜索，AI 会列出所有 uses 了 Vcl.Forms 的单元文件。这在重构或评估修改影响范围时特别有用。

---

### 场景 4.9 — 多文件重构（约 2 分钟）

#### AI 对话演示

```
用户: 我想把项目中的 TStringList 全部替换为 TArray<String>，
      先查一下哪些地方用了 TStringList，评估影响范围
```

- AI 调用 `delphi_kb(query="TStringList", kb_type="project", search_type="reference")` 查找引用
- 展示引用列表：哪些文件、哪些行用到了 TStringList
- AI 列出影响评估：涉及 X 个文件、Y 处引用、Z 个单元

```
用户: 影响不大，开始重构。逐个文件替换为 TArray<String>，
      并调整相关的方法调用
```

- AI 逐个文件编辑修改
- 每次修改后调用 `compile_project(project_path="当前文件.pas")` 做语法检查
- 全部修改完成后，调用 `compile_project(project_path="项目.dproj")` 做全项目编译验证，确保跨文件类型引用正确
- 编译通过后，调用 `file_tool(action="format")` 格式化代码
- 展示最终编译通过的确认

#### 旁白

下面这个场景展示的是**多文件重构**——这也是 AI 辅助开发的高价值场景。

比如我想把项目中所有 `TStringList` 的使用替换为 `TArray<String>`，这是一个跨多个文件的变更。

第一步，**查引用评估影响**。输入指令后，AI 先调用 `delphi_kb` 的引用搜索，找出所有用到了 `TStringList` 的文件和位置，列出一份影响清单——涉及几个文件、多少处引用。让你在动手之前就知道改动有多大。

确认影响可控后，第二步，**执行重构**。AI 逐个文件修改，每改完一个文件就编译一次，确保没有引入新的错误。

全部改完后，再统一格式化代码。整个重构过程由 AI 执行、AI 验证，**你只需要做决策——改不改、改哪些——执行的脏活累活交给 AI**。

这就是引用查询 + 项目知识库 + 编译验证三者联动产生的化学效应。

---

### 场景 4.10 — 代码格式化 & 自动备份（约 2 分钟）

> **威力点**：格式化前自动创建 `__history` 版本备份，可随时回退。不怕改坏。

#### AI 对话演示

```
用户: 格式化 refactor-demo/DataProcessor.pas 的代码
```

##### 第 1 步：自动备份

- AI 调用 `file_tool(action="format", file_path="DataProcessor.pas", backup=true)`
- pasfmt 在执行格式化前自动执行备份逻辑：
  ```
  ✅ 备份文件已创建: DataProcessor.pas.__history\DataProcessor.pas.~1~
  ```

##### 第 2 步：格式化

- pasfmt 执行格式化，展示 diff：
  ```diff
  - for I := 0 to ALines.Count - 1 do begin
  + for I := 0 to ALines.Count - 1 do
  + begin
  ```

##### 第 3 步：查看备份

```
用户: 让我看看备份文件
```

- AI 列出 `__history` 目录内容：
  ```
  DataProcessor.pas.~1~  (2026-05-15 09:00:00, 1.3 KB)
  ```

```
用户: 对比备份和当前文件的差异
```

- AI 展示 `diff` 对比格式化前后的变化

```
用户: 如果我不满意格式化的结果，帮我恢复到备份版本
```

- AI 将备份文件复制回原位置，恢复完成

#### 旁白

代码格式化和重构有一个让人担心的问题——"改坏了怎么办？"

`delphi_file`（原名 `file_tool`，旧名仍兼容）内置了自动备份机制。默认 `backup=true`，在执行任何写入前，它会在源文件同级目录下创建 `__history` 文件夹，保存一份带版本号的备份。

备份文件的命名规则和 **Delphi IDE 自带的 History 机制完全一致**——`文件名.~版本号~`。如果你反复格式化多次，版本号会自动递增：`~1~`、`~2~`、`~3~`……

任何时候你觉得改得不对，都可以让 AI 查看备份文件、对比差异，甚至直接从备份恢复。

这个机制不只在格式化时生效——**AI 在重构、修复编译错误等任何修改代码的操作中，都会先备份再修改**，确保你的源码安全。

---

### 场景 4.11 — 编码规范对 AI 行为的影响（约 3 分钟）

> **威力点**：同样的需求，换一套编码规则，AI 生成截然不同风格的代码。证明编码规范真实控制 AI 行为。

#### AI 对话演示

```
用户: 给我写一个字符串工具单元，包含 Join 和 Split 方法。
      先用 demo-project 的编码规范。
```

##### 第 1 组规则：现代规范（demo-project/CODING_RULES.mdc）

- AI 调用 `get_coding_rules(project_path="demo-project/DemoApp.dproj")`
- 获取的规则摘要：
  ```
  类型名: T + 大驼峰  变量: L + 大驼峰  参数: A + 大驼峰
  缩进: 2 空格        begin: 另起一行    异常: 具体类型
  ```
- AI 生成的代码：
  ```delphi
  unit StringUtils;

  interface

  type
    TStringUtils = class
    public
      class function Join(const AStrings: TArray<string>;
        const ASeparator: string): string; static;
      class function Split(const AText, ASeparator: string): TArray<string>; static;
    end;

  implementation

  { TStringUtils }

  class function TStringUtils.Join(const AStrings: TArray<string>;
    const ASeparator: string): string;
  var
    I: Integer;
  begin
    // ...
  end;
  ```

```
用户: 现在切换成旧项目的编码规范再生成一次。
```

##### 第 2 组规则：旧项目规范（legacy-project/CODING_RULES.mdc）

- AI 调用 `get_coding_rules(project_path="legacy-project/LegacyApp.dproj")`

  （读取 legacy-project/CODING_RULES.mdc，包含匈牙利命名、4 空格缩进、行尾 begin 等规则）

  （或者直接指定规则文件路径——AI 读取另一份 CODING_RULES）

- 获取的规则摘要：
  ```
  类型名: 无 T 前缀小驼峰  变量: 匈牙利命名   参数: 无前缀小驼峰
  缩进: 4 空格             begin: 行尾      异常: except Exception 兜底
  ```
- AI 生成的代码：
  ```delphi
  unit string_utils;

  interface

  type
    StringUtils = class
    public
      class function join(const arrStrings: array of string;
        const separator: string): string; static;
      class function split(const text, separator: string): TArray<string>; static;
    end;
  ```

##### 并排对比

- **分屏展示**两段代码，标注差异点：

| 维度 | 现代规范 | 旧项目规范 |
|------|----------|-----------|
| 类型名 | `TStringUtils` | `StringUtils` |
| 方法名 | `Join`, `Split` | `join`, `split` |
| 参数名 | `AStrings`, `ASeparator` | `arrStrings`, `separator` |
| 缩进 | 2 空格 | 4 空格 |
| begin | 另起一行 | 行尾 |
| 单元名 | `StringUtils` | `string_utils` |

#### 旁白

前面我们看过编码规范查询——但它的真正价值在于：**规范不是摆设，它会实际改变 AI 的输出行为。**

这个对比实验很能说明问题：

同样的需求——"写一个字符串工具单元，包含 Join 和 Split 方法"。换了一套 CODING_RULES，AI 生成的是**风格截然不同的两套代码**。

左边是现代规范：`T` 前缀类型名、`A` 前缀参数、`L` 前缀变量、2 空格缩进、`begin` 另起一行。

右边是旧项目规范：无前缀类型名、匈牙利命名法、4 空格缩进、`begin` 放在行尾、甚至单元名都变成了下划线风格。

**编码规范不是装饰——它真实地控制了 AI 的行为。**

这意味着：
- 你接手一个遗留项目？把项目的原编码规范写成 CODING_RULES.mdc，AI 生成的代码自动匹配项目风格，不会显得突兀
- 团队有严格的代码审查标准？把审查规则写进去，AI 生成代码时自动绕过红线
- 新人加入团队？不用反复强调规范，AI 自动遵守

这就是编码规范对 AI Agent 的行为影响——**你定规则，AI 执行，一致性有保障**。

---

### 场景 4.12 — 批量多项目编译（约 2 分钟）

> **威力点**：一句话编译整个解决方案，依赖顺序由 AI 处理。

#### AI 对话演示

```
用户: 编译整个解决方案，group-project 下的所有项目
```

- AI 发现 `ProjectGroup.groupproj` 文件，解析项目依赖关系
- AI 按构建顺序编译：
  - 第 1 步：`compile_project(project_path="LibProject/LibUtils.dproj", build_configuration="Debug")` → ✅
  - 第 2 步：`compile_project(project_path="AppProject/MainApp.dproj", build_configuration="Debug")` → ✅
- 展示编译输出：两个项目依次编译成功

```
用户: 用 Release 配置重新编译全部项目，Win64 平台
```

- AI 重新按序编译，这次 `target_platform="win64"`, `build_configuration="Release"`
- 展示输出

#### 旁白

前面演示的都是单个项目编译。但在企业开发中，一个解决方案往往包含多个项目——一个公共库项目 + 几个应用项目，有依赖关系。

传统做法：打开 IDE → 逐个打开每个项目 → 选择配置 → 编译 → 检查结果。如果是全量重新编译，还得注意编译顺序。

现在你只需要说"编译整个解决方案"，AI 会自动找到 `.groupproj` 分组项目文件，解析项目间的依赖关系，**按正确的顺序逐个编译**——先编译 LibProject，再编译 AppProject。

想换平台？"用 Release、Win64 重新编译全部"——一句话，AI 重新按序编译，你不用碰 IDE。

## 第五部分：高级功能（约 12 分钟）

### 场景 5.1 — 构建文档知识库（约 1.5 分钟）

#### AI 对话演示

```
用户: 构建 Delphi 帮助文档知识库
```

- AI 调用 `delphi_kb(action="build", kb_type="document", async_mode=true)`
- 返回 task_id
- 然后调用 `async_task(action="status", task_id="xxx", long_poll_seconds=30)` 查看进度
- **（剪辑提示：此过程耗时数分钟，建议加速或跳过等待）**

#### 旁白

我们知道 Delphi 的帮助文档有大量的 CHM 文件。项目支持将这些 CHM 帮助文档构建为可全文搜索的知识库。

输入"构建 Delphi 帮助文档知识库"，AI 会自动检测 Delphi 安装目录下的帮助文档，用 7-Zip 解压 CHM 文件，然后构建全文索引。

这个过程是异步执行的，你可以通过 `async_task` 查询构建进度。构建完成后，就可以像搜索源码一样搜索帮助文档了。

---

### 场景 5.1b — 文档知识库实战搜索（约 2 分钟）

> **威力点**：16 万页 Delphi 帮助文档，一句自然语言找到答案。不需要翻 CHM，不需要记 API 手册。

#### AI 对话演示

构建完成后：

```
用户: 查一下帮助文档，TCanvas.Draw 方法的参数说明，
      特别是最后一个参数 DrawOpacity 的作用
```

- AI 调用 `delphi_kb(query="TCanvas.Draw", kb_type="document", search_type="all")`
- 在 16 万+ 文档页面中匹配到 `Vcl.Graphics.TCanvas.Draw` 帮助页面
- 展示结果：
  ```
  procedure Draw(X, Y: Integer; const Graphic: TGraphic; DrawOpacity: Byte = 255);
  // DrawOpacity: 绘制不透明度。0=完全透明, 255=完全不透明
  // 默认值 255 表示完全不透明
  ```

```
用户: 搜索帮助文档，怎么用 PrintDialog 组件设置打印机参数
```

- AI 调用 `delphi_kb(query="PrintDialog printer settings", kb_type="document", search_type="semantic")`
- 搜索到 `Vcl.Dialogs.TPrintDialog` 帮助页面及相关文章
- 返回用法说明和代码示例

#### 旁白

构建完帮助文档知识库后，最实在的用法就是——**搜帮助**。

传统的 Delphi 帮助查找方式：打开 CHM → 找到索引 → 输入关键字 → 浏览 → 翻到对的页面。如果不知道准确的关键字，就更痛苦了。

现在你只需要说"查一下 TCanvas.Draw 的参数说明"，AI 在 16 万页帮助文档中做全文检索，直接定位到 `Vcl.Graphics.TCanvas.Draw` 的帮助页面，提取参数说明——`DrawOpacity` 从 0 到 255 控制不透明度，默认 255 不透明。

甚至可以用自然语言搜："怎么用 PrintDialog 设置打印机参数"——语义搜索会帮你找到相关的帮助文章。

这就是 **16 万页文档的即时检索能力**，比翻 CHM 快两个数量级。

### 场景 5.2 — 安装组件包（约 1 分钟）

#### AI 对话演示

```
用户: 安装 MyComponent.dpk 组件包
```

- AI 调用 `install_package(package_path="MyComponent.dpk")`
- 展示编译和注册过程

```
用户: 查看已安装的组件包列表
```

- AI 调用 `list_installed_packages()`
- 展示已注册的 IDE 组件包

#### 旁白

安装 Delphi 组件包也变得很简单。

输入"安装 MyComponent.dpk"，AI 会编译这个包文件，如果是设计期包还会自动注册到 IDE 中。

安装完成后，输入"查看已安装的组件包列表"，就可以看到所有注册了的组件包。

---

### 场景 5.3 — 复杂编译错误诊断（约 2 分钟）

> **威力点**：AI 不是只看错误行——它搜索 KB 理解泛型约束、类型定义等深层信息，从根上修复问题。

#### AI 对话演示

```
用户: 编译 compile-error-demo/ErrorCode.pas，如果有错误分析并修复
```

- AI 调用 `compile_project(project_path="compile-error-demo/ErrorCode.pas")`
- 编译错误：
  ```
  [dcc32 Error] ErrorCode.pas(28): E2511 Type parameter 'TCustomKey' must have a comparer
                      to be used in TDictionary<TCustomKey, string>
  ```

**传统做法：** 看到 `E2511 must have a comparer`，新手可能完全不知道什么意思。即使知道，也得去查 `IEqualityComparer<T>` 怎么实现。

**AI 的做法：**

##### 第 1 步：搜索 KB 理解错误原因

- AI 调用 `delphi_kb(query="TDictionary", search_type="class", kb_type="delphi")` → 查看泛型约束定义
- 发现 `TDictionary<TKey, TValue>` 要求 `TKey` 实现 `IEqualityComparer<TKey>` 或传入比较器
- AI 调用 `delphi_kb(query="TEqualityComparer", search_type="class", kb_type="delphi")` → 查看比较器基类

##### 第 2 步：分析根因

- `TCustomKey` 是 record 类型，没有默认比较器
- 需要创建 `TEqualityComparer<TCustomKey>` 的子类，实现 `Equals` 和 `GetHashCode`
- 在 `TDictionary.Create` 时传入比较器实例

##### 第 3 步：修复代码

- AI 生成 `TCustomKeyComparer` 类
- 修改 `TDataCache.Create` 传入比较器
- 重编译 → 通过 ✅

#### 旁白

前面的编译错误修复演示的是"缺少 uses 单元"这种简单情况。这次我们看一个**真正的硬骨头**。

`E2511 Type parameter must have a comparer`——这个错误对于有经验的 Delphi 开发者来说，意思是用 record 做 `TDictionary` 的 key 时，需要提供一个比较器。但如果你不熟悉泛型约束，这个错误信息非常 cryptic。

AI 的做法跟人类完全不同：

**第一步，AI 搜索知识库**。它去查 `TDictionary` 的类定义，看它的泛型约束到底是什么——确认了 `TKey` 需要 `IEqualityComparer` 的支持。

**第二步，AI 再查 `TEqualityComparer` 的源码 KB**，看这个基类怎么继承、怎么实现 `Equals` 和 `GetHashCode`。

**第三步，根因分析**——`TCustomKey` 是 record，没有默认比较器，所以需要自定义一个 `TCustomKeyComparer`，在 `TDictionary.Create` 时传入。

最后生成修复代码，重新编译通过。

这就是 **AI + 知识库** 配合解决复杂问题的模式——**不是靠 AI 的记忆猜，而是真的去查源码定义来理解错误根因**。对于 Delphi 这种有着 30 年历史、API 庞大繁杂的生态，这个能力尤其珍贵。

**这就形成了一个"写代码 → 编译 → 发现错误 → 修复 → 再编译"的闭环，完全在对话中完成。**

---

### 场景 5.4 — 完整从 0 到 1 工作流（约 3 分钟）

> **设计思路**：这是教程的灵魂场景，把前面所有工具串联成一个完整故事。展示 AI 从零开始完成一个功能的全过程。

#### AI 对话演示

故事线：项目需要一个**JSON 配置文件的读写单元**，从头开始实现。

```
用户: 我需要给项目加一个 JSON 配置文件管理单元，
      按项目编码规范来。先获取一下规则。
```

##### 第 1 步：获取编码规范

- AI 调用 `get_coding_rules(section="writing")`
- 了解命名规范、文件头格式、异常处理要求

```
用户: 查一下 Delphi 处理 JSON 的官方类
```

##### 第 2 步：搜索 API

- AI 调用 `delphi_kb(query="TJSONObject", search_type="class", kb_type="delphi")` 搜索 `TJSONObject`
- AI 调用 `delphi_kb(query="TJSONValue", search_type="class", kb_type="delphi")` 搜索 `TJSONValue`
- AI 调用 `delphi_kb(query="TFile.ReadAllText", search_type="function", kb_type="delphi")` 确认文件读取 API
- 展示搜索结果和 API 用法

```
用户: 好，开始写代码。单元名 JsonConfigManager，
      提供 LoadConfig、SaveConfig、GetValue、SetValue 方法
```

##### 第 3 步：AI 写代码

- AI 结合编码规范和 API 定义，生成完整单元
- 展示生成的代码（可以画中画展示代码文件实时变化）

##### 第 4 步：编译验证

```
用户: 编译项目检查语法
```

- AI 调用 `compile_project(project_path="JsonConfigManager.pas")`
- 如果编译失败，AI 自动修复并重新编译
- 展示编译成功

##### 第 5 步：格式化

```
用户: 格式化代码
```

- AI 调用 `file_tool(action="format", file_path="JsonConfigManager.pas")`
- 展示格式化后的最终代码

##### 第 6 步：代码审计

```
用户: 审计一下代码质量
```

- AI 调用 `get_coding_rules(section="review")`
- 逐项审查：资源泄漏？异常处理？命名规范？类型安全？
- 输出审查报告

```
用户: 按审查意见修改
```

- AI 根据审查报告修改代码
- 再次编译确认通过

#### 旁白

最后一个场景，我们把今天学到的所有工具串联起来，走一遍完整的 **从 0 到 1 开发工作流**。

故事是这样的：项目需要一个 JSON 配置文件管理单元。

你不需要手动打开 IDE、建文件、查帮助，全部在 AI 对话中完成：

**① 获取编码规范** → AI 先了解项目规则
**② 搜索 API 确认签名** → 查 `TJSONObject`、`TJSONValue`、`TFile.ReadAllText` 的确切用法
**③ 知识库驱动代码生成** → 结合规范 + API 定义生成代码（file_tool write 默认自动备份），而不是凭记忆瞎猜
**④ 格式化** → pasfmt 统一风格
**⑤ 编译验证** → 编译检查语法
**⑥ 代码审计 + 创建工单** → 审计后把问题自动登记为 Issue
**⑦ 清理 & 验证** → 删除未用代码，确认备份存在

关键区别在于 **第②步和第⑥步**：
- 第②步不是 AI 凭训练数据"回忆"API——它真的去知识库里查了 `TJSONObject` 的类继承链和构造函数签名
- 第⑥步不是简单的"改完拉倒"——审计报告可以通过 MCP 内置的 `code_hosting` 工具一键转为工单，纳入 Gitea 问题追踪（⑧ Gitea 缺陷闭环：审计工单 → 修复 → `gitea_close_issue` 关联提交并关闭）

整个流程你只需要做决策和提需求，AI 负责执行和验证。这就是 **MCP Server + AI 辅助 Delphi 开发** 的完整形态。

---

### 场景 5.5 — Gitea 缺陷闭环实战（约 3 分钟）

> **威力点**：以本项目自身作为案例，演示代码提交 → 审计 → 创建工单 → 修复 → 关闭工单的完整 Gitea 闭环。
>
> 所有操作通过 `code_hosting` 一个工具完成，无需切换平台。

#### AI 对话演示

故事线：我们刚完成 `code_hosting` 工具的开发，需要提交代码、审计、并将审计发现登记到 Gitea 跟踪。

```
用户: 把我们刚完成的 code_hosting.py 提交到 Git，
      然后审计代码质量，有发现就创建 Gitea 工单跟踪。
```

##### 第 1 步：代码提交

- AI 调用 `code_hosting(action="git_add", work_dir=".", files=["src/tools/code_hosting.py", "src/server.py", "tests/test_code_hosting.py"])`
- AI 调用 `code_hosting(action="git_commit", work_dir=".", commit_message="feat: add unified code_hosting tool")`
- 返回 commit hash：`0a7e8b7`

##### 第 2 步：代码审计

- AI 调用 `get_coding_rules(section="review")` 获取审核规范
- AI 分析 `code_hosting.py` 代码，逐项检查：
  - ✅ 参数校验完整性
  - ✅ 异常处理覆盖
  - ✅ 返回格式一致性
  - ✅ 跨平台路径配置
- 输出审查报告：列出通过项和改进建议

##### 第 3 步：连接 Gitea 并创建工单

```
用户: 将审计结果创建为 Gitea 工单，连接到 https://code.qdac.cc:3000，
      仓库 swish/api_test
```

- AI 调用 `code_hosting(platform="gitea", action="create_token", base_url="https://code.qdac.cc:3000", username="...", password="...")` ← 获得 Token
- AI 调用 `code_hosting(platform="gitea", action="init_labels", base_url="...", token="...", repo="swish/api_test")` ← 确保标签存在
- AI 调用 `code_hosting(platform="gitea", action="create_issue", base_url="...", token="...", repo="swish/api_test",
     title="[审计] code_hosting.py 代码审查",
     body="审计发现的改进建议...",
     label_names=["类型/改进", "优先级/中", "状态/待确认"])`
- 返回工单链接：`https://code.qdac.cc:3000/swish/api_test/issues/7`

##### 第 4 步：修复问题

- AI 根据审计建议修改代码：
  - `_request()` 增加 token 空值校验
  - `code_hosting()` 增加 API 操作前置参数检查
- AI 调用 `code_hosting(action="git_add", ...)` + `git_commit` → commit `8f929b5`

##### 第 5 步：关闭工单（关联提交）

```
用户: 在工单中说明修复内容并关闭
```

- AI 调用 `code_hosting(platform="gitea", action="add_comment", base_url="...", token="...", repo="swish/api_test",
     issue_number=7, body="已在 commit 8f929b5 中修复: ...")`
- AI 调用 `code_hosting(platform="gitea", action="close_issue", base_url="...", token="...", repo="swish/api_test",
     issue_number=7, comment_body="已修复并合并，commit: 8f929b5")`
- 工单关闭 ✅

#### 旁白

最后一个场景，我们用 **本项目自身** 作为案例，走一遍完整的 Gitea 缺陷闭环。

这是一个真正发生在项目开发中的场景——你刚完成一个功能模块的开发，需要走完"提交 → 审计 → 跟踪 → 修复 → 关闭"的全流程。

**① 代码提交**：`git_add` + `git_commit` 提交到本地仓库。

**② 代码审计**：调用 `get_coding_rules` 获取审核规范，逐项审查代码质量。

**③ 创建 Gitea 工单**：通过 `code_hosting` 的 `create_token` 获取访问令牌 → `init_labels` 确保四维标签存在 → `create_issue` 创建工单并打标签。全部通过**同一个工具**完成，不用离开 AI 对话。

**④ 修复**：根据审计建议修改代码，再次提交。

**⑤ 关闭**：`add_comment` 记录修复内容（可包含 commit hash），`close_issue` 关闭工单。工单历史完整可追溯。

这个闭环的关键价值在于：**审计结果不落地在对话里——而是被登记到 Gitea 的问题追踪系统中**，纳入团队的标准化流程。commit 与 issue 之间的关联也被记录下来，后续开发者可以 trace 每个问题的修复历史。

---

## 第六部分：总结 & 结束（约 1 分钟）

### 画面
- 回到项目 GitHub 页面
- 展示 README 中的 Star、License 等信息

### 旁白脚本

好了，今天的教程到这里就结束了。我们来快速回顾一下：

**📋 第一节 — 安装**
一句话让 AI 自动完成克隆、配环境、配置客户端，零手动操作。

**🔍 第二节 — 知识库搜索**
- 精确搜索：搜类（`TStringList`）、搜函数（`Split`），瞬间定位 API
- **🆕 语义搜索**：不知道 API 名字？自然语言描述，AI 从 30 万+ 函数中找出你要的
- **🆕 引用查询**：查哪些文件用了某个类型，评估重构影响
- **🆕 文档 KB 实战搜索**：构建完成后，一句自然语言搜 16 万页帮助文档

**⚙️ 第三节 — 编译 & 格式化**
- 编译完整项目或单文件语法检查
- **🆕 复杂编译错误诊断**：AI 搜索 KB 理解泛型约束等深层原因，从根上修复
- **🆕 批量多项目编译**：一句话编译整个解决方案，自动处理依赖顺序
- pasfmt 一键格式化代码

**📝 第四节 — AI 辅助开发**
- **🆕 知识库驱动的代码生成**：AI 先在 KB 查 API 签名，再写代码，一次编译通过
- **🆕 编码规范驱动的代码审计**：逐条对照规范审查，输出结构化报告
- **🆕 审计结果自动创建工单**：通过 MCP 内置 `code_hosting` 工具一键创建标签和工单
- **🆕 多文件重构**：引用查询 → 影响评估 → 逐文件修改 → 编译验证
- **🆕 修改前自动备份**：format/重构前自动创建 `__history` 版本备份，可恢复
- **🆕 编码规范控制 AI 行为**：同一需求换套规则，生成风格完全不同的代码

**🚀 第五节 — 高级功能**
- 构建 CHM 帮助文档知识库，16 万页全文检索
- 安装 .dpk 组件包到 IDE
- 完整从 0 到 1 工作流：规范 → API 查证 → 代码生成 → 编译 → 格式化 → 审计 → 工单
- **🆕 Gitea 缺陷闭环实战**：代码提交 → 审计 → 创建工单 → 修复 → 关闭，以本项目自身为案例

你可以把这个 MCP Server 配合任何支持 MCP 协议的 AI 助手使用——Claude Desktop、Trae、CodeArts Agent、Cursor 等等。

项目是完全开源的（MIT 协议），GitHub 地址在屏幕上方。如果觉得有用，别忘了点个 Star ⭐ 支持一下！

最后，大家在使用过程中遇到任何问题，欢迎在 GitHub 上提交 Issue。

感谢观看，我们下期再见！

---

## 附录：录制提示

### 屏幕布局建议

| 场景 | 布局 |
|------|------|
| GitHub 页面介绍 | 全屏浏览器 |
| AI 安装演示 | 全屏 AI 对话界面 + **画中画**终端 |
| AI 写代码（复杂代码生成） | 全屏 AI 对话 + **画中画** VS Code 展示代码 + KB 搜索结果 |
| 语义搜索发现隐藏 API | 全屏 AI 对话，突出显示 KB 搜索的命中结果 |
| 代码审计报告 + 创建工单 | 全屏 AI 对话 + **画中画** Gitea 工单界面 |
| 复杂编译错误诊断 | 全屏 AI 对话，突出 KB 搜索 TDictionary 定义的过程 |
| 批量多项目编译 | 全屏 AI 对话 + 画中画显示编译顺序和结果 |
| 多文件重构 | 全屏 AI 对话 + **画中画** VS Code 显示文件切换 |
| 文档 KB 实战搜索 | 全屏 AI 对话，展示搜索命中的帮助文档内容 |
| 代码格式化 + 自动备份 | 分屏：左 = AI 对话，右 = 文件资源管理器展示 __history 目录 |
| 编码规范影响对比 | 分屏：左 = 现代规范生成代码，右 = 旧规范生成代码，并排对比 |
| Gitea 缺陷闭环实战 | 全屏 AI 对话 + **画中画** Gitea 工单界面展示工单状态变化 |

### 需要提前准备

- [ ] Python 3.10+ 已安装
- [ ] Git 已安装
- [ ] Delphi IDE 已安装（任意版本）
- [ ] 项目已克隆并安装好依赖
- [ ] AI 客户端（如 Claude Desktop）已配置好 MCP Server
- [ ] 准备一个可编译的 Delphi 示例项目（含 .dproj 文件）
- [ ] 测试用的 .pas 文件（含可展示的编译错误）
- [ ] 提前准备 JSON 读写单元的示例代码（场景 5.4 使用）
- [ ] 重构场景需要一个含多处 TStringList 用法的项目（refactor-demo/）
- [ ] 复杂编译错误场景需要 ErrorCode.pas（泛型约束错误，compile-error-demo/）
- [ ] 代码审计场景需要 LegacyData.pas（含故意遗留的 5 类问题，review-demo/）
- [ ] 批量编译场景需要 group-project/ 的多项目结构
- [ ] 文档知识库需要在录制前完成构建（构建耗时数分钟）
- [ ] 语义搜索场景需要提前构建 embedding 向量索引：`delphi_kb(action="build_embedding")`
- [ ] Gitea 场景需要可访问的 Gitea 实例（如 https://code.qdac.cc:3000）和仓库权限
- [ ] Gitea 缺陷闭环场景需要预先在仓库中运行一次 init_labels 创建标签
- [ ] 延时代码：`Start-Sleep -Seconds 3` 插入操作间控制节奏

### 剪辑标记

- **[加速]** — 安装依赖、构建知识库等耗时操作，建议 5x-10x 加速
- **[剪辑]** — 等待完成、中间输出过长等，建议直接剪掉
- **[画中画]** — 需要同时展示 AI 对话和代码/终端时
- **[审计报告]** — 代码审计输出报告时，逐条展示可停留 2-3 秒，让观众看清每项问题
- **[重构过程]** — 多文件修改可加速展示，每改完一个文件停留一下展示编译结果

### 常见翻车点

1. **Python 编码问题** — 确保 PowerShell 中先执行 `$env:PYTHONIOENCODING='utf-8'`
2. **虚拟环境未激活** — 演示前确认 `venv\Scripts\activate` 已执行
3. **配置文件路径** — 手动配置时路径中的反斜杠要双写或使用正斜杠
4. **Delphi 编译器版本** — 不同 dproj 的 ProjectVersion 要匹配正确的 Delphi 版本
