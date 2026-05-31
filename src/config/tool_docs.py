"""
Tool 完整文档字典 — 供 tool_help 工具按需查询

每个工具包含：简介、触发词、协作链、全部 action 说明、示例、降级策略等。
description 字段是精简版本的 1-2 句简介，其他字段都是 AI 按需获取的详细说明。
"""

TOOL_HELP_DOCS: dict = {
    "compile_project": {
        "summary": "编译 Delphi 项目(.dproj/.dpr/.dpk/.pas)。必填: project_path。",
        "description": "编译 Delphi 工程或检查 .pas 文件语法。",
        "triggers": [
            "编译、构建、生成exe、语法检查、编译报错、build、compile、msbuild、dcc32",
            "检查语法、编译验证、编译项目、dproj编译",
        ],
        "file_triggers": "看到 .dproj/.dpr/.dpk/.pas 文件时优先编译",
        "constraints": [
            "❌ 不得用 bash/cmd 运行 dcc32/msbuild（绕过 MSBuild/事件/依赖）",
            "✅ 编译 .dproj/.dpr/.dpk 或检查 .pas 语法必须用此",
        ],
        "workflow": "get_coding_rules → delphi_file → compile → 失败 → check_environment",
        "fallback": "MSBuild 不可用→dcc32；dry_run 预览参数",
        "actions": {
            "默认": "根据 project_path 编译项目或检查语法",
        },
        "examples": [
            'compile_project(build_configuration="Release")  编译Release版本',
            'compile_project(target_platform="win64")        生成64位exe',
            'compile_project(project_path="unit.pas")        检查语法',
            'compile_project(dry_run=True)                   只看参数不执行',
        ],
    },
    "delphi_kb": {
        "summary": "搜索 Delphi API/项目代码/文档(类/函数/语义搜索)，构建知识库。",
        "description": "知识库搜索/管理 — 查 Delphi API、项目代码、文档",
        "triggers": [
            "搜索类、搜索函数、查API、查定义、知识库、构建知识库、KB、语义搜索",
        ],
        "file_triggers": "写 .pas 代码前应先搜索 KB 查 API 定义",
        "workflow": "写代码前→delphi_kb查API→delphi_file(read)看定义→写代码→compile",
        "actions": {
            "search": '搜索类/函数/文档, kb_type=all/delphi/project/thirdparty/document, search_type=function/procedure/class/record/semantic/reference',
            "stats": "查看知识库统计(文件数、类数、函数数、末次构建时间)",
            "build": "构建/更新知识库（支持异步 async_mode=true）",
            "scan": "扫描目录添加文档(kb_type=document)",
            "web": "添加网页文档(kb_type=document)",
            "read": "读取文档内容(url/doc_id)或源码文件(file_path)",
            "build_embedding": "构建向量索引",
        },
        "examples": [
            'delphi_kb(query="TStringList")                                    搜索类',
            'delphi_kb(query="Create", search_type="function")                  搜索函数',
            'delphi_kb(action="stats")                                          查看统计',
            'delphi_kb(action="build", kb_type="project")                       构建项目知识库',
        ],
    },
    "delphi_file": {
        "summary": "Delphi 文件(.pas/.dfm/.dproj)专用操作。禁止用原生 read/write/edit！",
        "description": "Delphi 文件专用操作：读/写/格式化/备份管理（编码检测+自动备份+DFM转换）",
        "triggers": [
            "读文件、查看源码、打开文件、cat、写代码、编辑文件、改代码、修改代码",
            "新建文件、格式化、整理代码、恢复备份、回退修改、diff、差异对比",
            "查看备份、还原文件、增删uses、添加单元、删除单元",
        ],
        "file_triggers": "操作 .pas/.dfm/.dproj/.dpk/.fmx/.inc 文件时必须用此",
        "constraints": [
            "❌ 严禁使用 edit/write/bash echo 直接修改 .pas/.dfm 文件（会绕过备份+编码检测）",
        ],
        "features": [
            "自动编码检测(UTF-8/GBK/UTF-16)",
            "自动备份(__history)",
            "DFM二进制↔文本透明转换",
            "按类名/函数名搜索定位代码、部分写入、格式化、uses子句增删",
        ],
        "workflow": "get_coding_rules → delphi_file(read) → delphi_file(write) → delphi_file(format) → compile_project",
        "actions": {
            "read": "读文件，支持分段读取(start_line/limit/end_line)或按类名/函数名定位",
            "write": "写文件（自动备份到 __history），支持全文替换或部分写入(start_line/end_line)",
            "format": "使用 pasfmt 格式化代码",
            "backup": "备份管理（创建/列表/恢复）",
            "uses": "增删 uses 子句中的单元",
        },
        "examples": [
            'delphi_file(action="read", file_path="Unit1.pas")                                         读文件',
            'delphi_file(action="read", search_type="class", type_name="TForm1")                       搜索类定义',
            'delphi_file(action="write", file_path="src/Unit1.pas", content="...")                     写入文件',
            'delphi_file(action="write", file_path="src/Unit1.pas", content="替换", start_line=5, end_line=10)  部分写入',
            'delphi_file(action="format", file_path="src/Unit1.pas")                                   格式化',
            'delphi_file(action="backup", file_path="Unit1.pas")                                       创建备份',
            'delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")                 列出备份',
            'delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)   恢复',
            'delphi_file(action="uses", uses_action="add", unit_name="System.SysUtils", file_path="Unit1.pas")  增uses',
        ],
    },
    "manage_component": {
        "summary": "DFM 组件增/删/改/生成 + PAS 自动同步。",
        "description": "DFM 组件增/删/改/生成 + PAS 自动同步",
        "triggers": ["添加组件、删除组件、修改组件、生成DFM、组件同步、manage component"],
        "sync_rules": [
            "add:    新字段声明 + 事件方法桩 + uses 单元",
            "remove: 字段声明 + 事件方法(声明+实现) + 空引用的 uses",
            "modify: 事件属性变更 → 增/删/改事件方法声明",
        ],
        "actions": {
            "create": "生成组件 DFM（编译+运行序列化，原 generate_component_dfm 功能）",
            "add": "向现有 DFM 添加子组件，自动同步 PAS 字段+事件+uses",
            "remove": "从 DFM 删除组件（含子树），自动同步删除 PAS 字段+事件方法",
            "modify": "修改 DFM 中组件属性，事件变更时自动同步 PAS 声明",
        },
        "examples": [
            'create: code="function CreateComponent(AOwner: TComponent): TComponent; ...", uses=["Vcl.Forms","Vcl.StdCtrls"]',
            'add: action="add", target_dfm="Unit1.dfm", new_component_class="TButton", properties={"Caption": "OK"}',
            'remove: action="remove", target_dfm="Unit1.dfm", component_name="BtnCancel"',
            'modify: action="modify", target_dfm="Unit1.dfm", component_name="BtnOK", properties={"Caption": "确认"}',
        ],
    },
    "check_environment": {
        "summary": "诊断 Delphi 编译环境、检测编译器、安装 pasfmt。首次使用先 check。",
        "description": "环境检查 — 诊断 Delphi 编译环境、检测编译器、安装 pasfmt",
        "triggers": ["检查环境、检测编译器、诊断、环境状态、环境就绪、编译器找不到"],
        "workflow": "首次使用→check_environment(action=check)→compile→失败→check_environment(action=detect)",
        "actions": {
            "check": "默认 — 检查当前编译环境状态（有多少编译器可用）",
            "detect": "重新从注册表/指定路径检测 Delphi 编译器",
            "install": "下载并安装 pasfmt 格式化工具",
            "format_install": "安装 pasfmt RAD Studio 插件",
        },
        "examples": [
            'check_environment(action="check")                                  检查环境',
            'check_environment(action="detect", search_path="D:\\Delphi")       指定路径检测',
        ],
    },
    "async_task": {
        "summary": "管理后台构建知识库等耗时任务。通常 delphi_kb(action=build) 已自动触发。",
        "description": "异步任务管理 — 管理后台构建知识库等耗时任务",
        "triggers": ["任务状态、查看进度、后台任务、构建进度、取消任务"],
        "push_notification": (
            "code_hosting git 任务（git_clone/git_push/git_push_retry）"
            " 完成时自动推送 TaskStatusNotification 到 MCP 客户端。"
            " AI Agent 仍需通过 async_task 查询结果。"
        ),
        "actions": {
            "start": "启动异步任务（通常 delphi_kb(action=build) 已自动启动，无需手动调用）",
            "status": "查询任务状态（返回进度百分比和状态）",
            "result": "获取任务结果",
            "list": "列出所有任务",
            "cancel": "取消运行中的任务",
        },
        "examples": [
            'async_task(action="status", task_id="...")   查看任务进度',
            'async_task(action="list")                    列出所有任务',
        ],
    },
    "install_package": {
        "summary": "编译并安装 Delphi 组件包到 IDE。支持 .dproj/.dpk/.groupproj。",
        "description": "编译并安装 Delphi 组件包到 IDE",
        "triggers": ["安装组件、安装包、编译包、dpk安装、注册组件、install package"],
        "details": "自动将设计期包注册到 IDE，运行期包仅编译",
        "workflow": "install_package → list_installed_packages 验证安装",
        "examples": [
            'install_package(package_path="MyPackage.dpk")  安装组件包',
        ],
    },
    "list_installed_packages": {
        "summary": "列出已安装到 IDE 的 Delphi 组件包。",
        "description": "列出已安装到 IDE 的 Delphi 组件包",
        "triggers": ["已安装的包、列出组件、查看已安装、验证安装"],
        "workflow": "install_package 后调用此工具验证组件已成功注册",
    },
    "get_coding_rules": {
        "summary": "获取 Delphi 编码规范。写/改 Delphi 代码前必须先调用！",
        "description": "获取 Delphi 编码规则 — AI 写/改 Delphi 代码前必须先调用",
        "triggers": ["编码规则、编码规范、代码风格、命名规范、规则、coding rules"],
        "file_triggers": [
            "⚠️ 看到 .pas/.dfm/.dproj/.dpk/.dpr/.inc/.res 等 Delphi 文件时，必须先调用此工具",
            "⚠️ 在写/修改任何 Delphi 代码前，必须先 get_coding_rules 了解编码规范",
        ],
        "workflow": "任何 .pas/.dproj 操作前→get_coding_rules(section='workflow') 了解流程",
        "section_guide": {
            "workflow": "工作流总览（先看这个了解整体流程）",
            "writing": "写 Delphi 代码时的命名/格式/泛型规则",
            "review": "编译后审查代码（含完整审核表）",
            "safety": "安全敏感操作规则",
            "agent_rules": "Agent 操作硬规则",
        },
        "default_section": "不传 section=返回工作流总览+章节索引（推荐首次调用）",
    },
    "run_audit": {
        "summary": "Delphi 源码骨架解析(AST)/代码审计/runtime 注册检查。",
        "description": "Delphi 源码结构解析 / 代码审计 / Runtime 注册检查",
        "triggers": [
            "语法解析、AST解析、解析源码、查类结构、查函数定义",
            "审计代码、审查代码、review code、audit、安全检查",
            "漏洞扫描、安全隐患、security review、性能分析",
            "运行时检查、运行时注册",
        ],
        "modes": {
            "ast": "⭐ 推荐，AI Agent 摘要模式。代码骨架提取（daudit --mode skeleton --compact），输出预格式化文本: 单元名、uses、类/记录/接口、函数/过程、常量。专为 AI 设计，最省 token",
            "audit": "运行 50+ 条静态分析规则，审计代码质量",
            "runtime": "运行时注册检查，检测 uses 中是否遗漏必需单元（如 FireDAC.DApt）",
        },
        "notes": "audit/ast 模式自动检测项目目录下的 daudit.exe；runtime 模式无需 daudit。",
        "workflow": "run_audit(mode='ast') → AI 分析结构 → delphi_file 精准修改 → compile_project 验证",
        "examples": [
            'run_audit(mode="ast", base_dir="src")                    ⭐ 骨架摘要',
            'run_audit(mode="ast", file_path="Unit1.pas")             单文件骨架',
            'run_audit(base_dir="C:\\Project\\src")                   代码审计（默认）',
            'run_audit(mode="runtime", base_dir="src")                运行时注册检查',
        ],
    },
    "code_hosting": {
        "summary": "代码托管平台操作 + Git 本地操作。Gitea/GitHub/GitLab/Gitee/GitCode。",
        "description": "统一操作 Gitea/GitHub/GitLab/Gitee/GitCode 平台 + Git 本地操作",
        "triggers": [],
        "platforms": {
            "gitea": "自托管 Gitea",
            "github": "GitHub (github.com)",
            "gitlab": "GitLab CE/EE (gitlab.com)",
            "gitee": "Gitee 码云 (gitee.com)",
            "gitcode": "GitCode (gitcode.net)",
        },
        "actions": {
            "api": {
                "create_token": "创建访问令牌（仅 Gitea）",
                "init_labels": "批量初始化四维流程标签",
                "create_issue": "创建工单",
                "close_issue": "关闭工单",
                "add_comment": "添加评论",
                "list_issues": "查询工单列表",
            },
            "git_sync": {
                "git_status": "查看仓库状态",
                "git_add": "暂存文件",
                "git_commit": "创建提交",
            },
            "git_async": {
                "git_clone": "克隆远程仓库（支持 GitHub 镜像源）",
                "git_push": "推送到远程（单次尝试）",
                "git_push_retry": "后台自动重试推送",
            },
        },
        "china_access": "git_clone 支持 mirror 参数指定镜像源。推送依赖用户自身的 SSH/HTTPS 代理配置。",
    },
    "dproj_tool": {
        "summary": ".dproj 项目文件管理：创建/查看/修改工程配置。",
        "description": ".dproj 项目文件管理 — 创建/查看/修改工程配置",
        "triggers": ["项目文件、dproj、工程配置、创建项目、添加配置、删除配置", "添加源文件、删除源文件、查看项目信息、项目管理"],
        "workflow": "dproj_tool(action=info) → delphi_file → 编译 → compile_project",
        "actions": {
            "create": "创建新的 .dproj 文件",
            "info": "读取 .dproj 文件完整信息（配置/源文件/资源/编译事件）",
            "set": "设置属性值（PropertyGroup 元素），可指定 config/platform",
            "add_config": "添加一个新的编译配置（如 Staging）",
            "remove_config": "删除指定编译配置",
            "add_source": "向 ItemGroup 添加源文件引用（DCCReference）",
            "remove_source": "从 ItemGroup 删除源文件引用",
        },
        "examples": [
            'dproj_tool(action="create", project_path="MyApp.dproj", main_source="MyApp.dpr")  创建项目',
            'dproj_tool(action="info", project_path="MyApp.dproj")                             查看项目配置',
            'dproj_tool(action="set", project_path="MyApp.dproj", property_name="DCC_Define", value="DEBUG;TEST", config="Debug")  设置编译符号',
            'dproj_tool(action="add_config", config_name="Staging", base_config="Debug")       添加Staging配置',
            'dproj_tool(action="add_source", project_path="MyApp.dproj", source_file="Unit1.pas")  添加源文件',
            'dproj_tool(action="create", project_path="App.dproj", main_source="App.dpr", form_units=["Unit1","Unit2"])  创建项目+Form桩代码',
        ],
    },
    "tool_help": {
        "summary": "获取任意工具的完整帮助文档，包含参数说明、示例、触发词、协作链。",
        "description": "获取工具的完整帮助文档",
        "triggers": ["帮助、帮助文档、用法、如何使用、详细说明、全量帮助"],
        "usage": "当不确定某个工具的详细用法时调用此工具。输入 tool_name 即可返回触发词、action 说明、示例、协作链等所有详细信息。",
        "examples": [
            'tool_help(tool_name="compile_project")',
            'tool_help(tool_name="delphi_file")',
        ],
    },
    "experience": {
        "summary": "经验记忆管理：保存/搜索 AI 成功解决问题的做法，下次遇到类似问题自动复用。",
        "description": "经验记忆管理 — 保存/搜索/管理 AI 成功解决问题的经验",
        "triggers": ["经验、记忆、保存经验、搜索经验、之前怎么解决的、我记得"],
        "workflow": "任务成功 → experience(action=save, problem=..., solution=...) → 下次 experience(action=search, query=...) 自动命中",
        "actions": {
            "save": "保存经验。problem=问题描述, solution=解决步骤, tools_used=用到的工具列表, tags=标签",
            "search": "语义搜索经验。query=搜索关键词, top_k=返回条数, tags=按标签过滤",
            "get": "查看经验详情。id=经验ID",
            "list": "浏览经验列表。tags=过滤标签, sort_by=排序字段, limit=条数",
            "update": "更新经验。id=经验ID, solution/tags/problem 等",
            "delete": "删除经验。id=经验ID",
        },
    },
}

# 工具名列表（保持顺序，用于 list_tools 和 tool_help 的 enum）
TOOL_NAMES: list = [
    "compile_project",
    "delphi_kb",
    "delphi_file",
    "manage_component",
    "check_environment",
    "async_task",
    "install_package",
    "list_installed_packages",
    "get_coding_rules",
    "run_audit",
    "code_hosting",
    "dproj_tool",
    "tool_help",
    "experience",
]

# 精简版 descriptions（用于 list_tools 的 description 字段）
# 规则：一句话用途 + 硬约束（不遵守会报错的规则）
TOOL_SHORT_DESC: dict = {
    "compile_project": (
        "编译 Delphi 项目(.dproj/.dpr/.dpk/.pas)。必填: project_path。"
        " 禁止手动 dcc32/msbuild，必须使用此工具。"
    ),
    "delphi_kb": (
        "搜索 Delphi API/项目代码/文档(类/函数/语义搜索)，构建知识库。"
    ),
    "delphi_file": (
        "Delphi 文件(.pas/.dfm/.dproj)专用操作: 读/写/格式化/备份/uses管理。"
        " 禁止用原生 read/write/edit 修改 .pas/.dfm 文件。"
    ),
    "manage_component": (
        "DFM 组件增/删/改/生成 + PAS 自动同步。"
    ),
    "check_environment": (
        "诊断 Delphi 编译环境(检测编译器/安装 pasfmt)。"
        " 首次使用或编译失败时先调用此工具。"
    ),
    "async_task": (
        "管理后台任务(构建知识库等)。查看进度/获取结果/取消任务。"
        " AI Agent 需通过此工具查询异步任务结果。"
    ),
    "install_package": (
        "编译并安装 Delphi 组件包(.dproj/.dpk/.groupproj)到 IDE。"
    ),
    "list_installed_packages": (
        "列出已安装到 IDE 的 Delphi 组件包。"
    ),
    "get_coding_rules": (
        "获取 Delphi 编码规则。修改 .pas 代码前必须先调用此工具。"
    ),
    "run_audit": (
        "Delphi 源码骨架解析(AST)/代码审计/runtime 注册检查。"
    ),
    "code_hosting": (
        "代码托管平台操作(Gitea/GitHub/GitLab/Gitee/GitCode) + Git 本地操作(git_status/add/commit/push/clone)。"
    ),
    "dproj_tool": (
        ".dproj 项目文件管理: 创建/查看/修改工程配置。"
    ),
    "tool_help": (
        "获取任意工具的完整帮助文档(参数说明/示例/触发词/协作链)。"
        " 不确定某个工具用法时调用此工具。"
    ),
    "experience": (
        "经验记忆管理: 保存/搜索 AI 成功解决问题的做法(语义搜索)。"
        " 任务成功后调用 save 保存经验，下次遇到类似问题前调用 search 查找可复用的解法。"
    ),
}
