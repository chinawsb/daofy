"""
Tool 完整文档字典 — 供 tool_help 工具按需查询

每个工具包含：简介、触发词、协作链、全部 action 说明、示例、降级策略等。
description 字段是精简版本的 1-2 句简介，其他字段都是 AI 按需获取的详细说明。
"""

TOOL_HELP_DOCS: dict = {
    "project": {
        "summary": "项目全生命周期管理：编译/配置查看/审计代码。合并自 compile_project + dproj_tool + run_audit。",
        "description": "项目全生命周期管理 — 编译/配置/审计",
        "triggers": [
            "编译、构建、生成exe、语法检查、编译报错、build、compile、msbuild、dcc32",
            "项目文件、dproj、工程配置、创建项目、添加配置、删除配置",
            "语法解析、AST解析、审计代码、审查代码、review code、audit",
        ],
        "constraints": [
            "❌ 不得用 bash/cmd 运行 dcc32/msbuild（绕过 MSBuild/事件/依赖）",
        ],
        "workflow": "tool_help(project) → project(action=...) 查看各 action 参数 → 调用",
        "actions": {
            "compile": "编译 .dproj/.dpr/.dpk 项目",
            "compile_file": "检查 .pas 文件语法（快捷方式，等价于 compile + .pas）",
            "dry_run": "预览编译参数，不实际执行",
            "info": "读取 .dproj 文件完整信息（配置/源文件/资源/编译事件）",
            "create": "创建新的 .dproj 文件",
            "set": "设置 .dproj 属性值（PropertyGroup），可指定 config/platform",
            "add_config": "添加新的编译配置（如 Staging）",
            "remove_config": "删除指定编译配置",
            "add_source": "向 ItemGroup 添加源文件引用",
            "remove_source": "从 ItemGroup 删除源文件引用",
            "audit": "运行 50+ 条静态分析规则",
            "ast": "⭐ 代码骨架提取（daudit --mode skeleton --compact），最省 token",
            "runtime": "运行时注册检查，检测 uses 中是否遗漏必需单元",
        },
        "action_params": {
            "compile": {
                "description": "编译 Delphi 项目",
                "required": ["project_path"],
                "optional": {
                    "target_platform": "目标平台(win32/win64/osx64/...)，默认 win32",
                    "build_configuration": "Debug/Release，默认 Debug",
                    "compiler_version": "编译器版本，不传则自动检测最新",
                    "conditional_defines": "条件编译符号数组，如 ['DEBUG','TEST']",
                    "unit_search_paths": "额外单元搜索路径数组",
                    "resource_search_paths": "资源搜索路径数组",
                    "optimize": "是否优化，默认 true",
                    "debug": "是否生成调试信息，默认 true",
                    "warning_level": "警告级别 0-4，默认 2",
                    "disabled_warnings": "禁用的警告编号，如 ['W1000']",
                    "output_type": "gui/console/dll，默认 gui",
                    "runtime_library": "static/dynamic，默认 static",
                    "timeout": "超时秒数，默认 600",
                    "auto_install": "仅 .dpk 有效，是否自动安装到 IDE，默认 true",
                    "run_verify": "编译后启动 3 秒验证是否崩溃，默认 false",
                    "output_path": "编译输出目录",
                },
                "examples": [
                    'project(action="compile", project_path="App.dproj", build_configuration="Release")',
                    'project(action="compile", project_path="unit.pas")',
                ],
            },
            "dry_run": {
                "description": "预览编译参数，不实际执行",
                "optional": {
                    "project_path": "项目文件路径",
                    "target_platform": "目标平台",
                    "build_configuration": "构建配置",
                    "compiler_version": "编译器版本",
                    "conditional_defines": "条件编译符号",
                    "unit_search_paths": "单元搜索路径",
                    "optimize": "是否优化",
                    "debug": "是否调试",
                    "output_type": "输出类型",
                    "runtime_library": "运行时库",
                },
                "examples": [
                    'project(action="dry_run", project_path="App.dproj")',
                ],
            },
            "compile_file": {
                "description": "检查 .pas 文件语法",
                "required": ["project_path"],
                "optional": {
                    "unit_search_paths": "单元搜索路径",
                    "conditional_defines": "条件编译符号",
                    "compiler_version": "编译器版本",
                },
                "examples": [
                    'project(action="compile_file", project_path="unit.pas")',
                ],
            },
            "info": {
                "description": "读取 .dproj 文件完整信息",
                "required": ["project_path"],
                "examples": [
                    'project(action="info", project_path="App.dproj")',
                ],
            },
            "create": {
                "description": "创建新的 .dproj 项目文件",
                "required": ["project_path", "main_source"],
                "optional": {
                    "project_guid": "项目 GUID，自动生成",
                    "framework_type": "VCL/FMX，默认 VCL",
                    "unit_search_paths": "初始单元搜索路径",
                    "namespace": "命名空间",
                    "configs": "编译配置列表，默认 ['Debug','Release']",
                    "sources": "初始源文件列表",
                    "form_units": "同时生成 Form 桩代码，如 ['Unit1','Main']",
                },
                "examples": [
                    'project(action="create", project_path="App.dproj", main_source="App.dpr")',
                    'project(action="create", project_path="App.dproj", main_source="App.dpr", form_units=["Unit1"])',
                ],
            },
            "set": {
                "description": "设置 .dproj 属性值",
                "required": ["project_path", "property_name", "value"],
                "optional": {
                    "config": "编译配置，如 Debug/Release",
                    "platform": "目标平台，如 Win32/Win64",
                },
                "examples": [
                    'project(action="set", project_path="App.dproj", property_name="DCC_Define", value="DEBUG;TEST", config="Debug")',
                ],
            },
            "add_config": {
                "description": "添加新的编译配置",
                "required": ["project_path", "config_name"],
                "optional": {
                    "base_config": "从哪个现有配置复制属性",
                    "defines": "条件编译符号",
                    "optimize": "是否启用优化",
                    "debug_info": "是否生成调试信息",
                },
                "examples": [
                    'project(action="add_config", project_path="App.dproj", config_name="Staging", base_config="Debug")',
                ],
            },
            "remove_config": {
                "description": "删除编译配置",
                "required": ["project_path", "config_name"],
                "examples": [
                    'project(action="remove_config", project_path="App.dproj", config_name="Staging")',
                ],
            },
            "add_source": {
                "description": "向项目添加源文件",
                "required": ["project_path", "source_file"],
                "optional": {
                    "main_source_flag": "true=添加为主源文件，false=添加到 DCCReference",
                },
                "examples": [
                    'project(action="add_source", project_path="App.dproj", source_file="Unit1.pas")',
                ],
            },
            "remove_source": {
                "description": "从项目删除源文件引用",
                "required": ["project_path", "source_file"],
                "examples": [
                    'project(action="remove_source", project_path="App.dproj", source_file="Unit1.pas")',
                ],
            },
            "audit": {
                "description": "运行 50+ 条静态分析规则",
                "optional": {
                    "base_dir": "审计基准目录",
                    "file_path": "单文件审计",
                    "rules": "规则集 P0/P1，默认 P0",
                    "severity": "最低严重级别 suggestion/warning/critical",
                    "output_format": "report/json，默认 report",
                },
                "examples": [
                    'project(action="audit", base_dir="src")',
                    'project(action="audit", file_path="Unit1.pas")',
                ],
            },
            "ast": {
                "description": "⭐ 代码骨架提取，最省 token",
                "required": ["base_dir"],
                "optional": {
                    "file_path": "单文件解析",
                },
                "examples": [
                    'project(action="ast", base_dir="src")',
                    'project(action="ast", file_path="Unit1.pas")',
                ],
            },
            "runtime": {
                "description": "运行时注册检查，检测遗漏的 uses 单元",
                "optional": {
                    "base_dir": "项目基准目录",
                },
                "examples": [
                    'project(action="runtime", base_dir="src")',
                ],
            },
        },
        "workflow_hints": {
            "创建项目": "project(action=create, ...) → project(action=info) → project(action=compile)",
            "日常编译": "project(action=compile, project_path=...) 自动检测 .pas 或 .dproj",
            "审计代码": "project(action=ast, base_dir=src) → 分析结构 → delphi_file → project(action=compile)",
            "改配置": "project(action=set, property_name=...) → project(action=compile) 验证",
        },
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
            "read": "读文件，支持分段读取(start_line/limit/end_line)或按类名/函数名定位。start_line 为 0-indexed（第 1 行=0）",
            "write": "写文件，支持全文替换或部分写入(start_line/end_line)。start_line/end_line 为 0-indexed 左闭右开。每次部分写入后会返回偏移量，用于后续编辑的行号调整",
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
            "所有异步任务（知识库构建、文档扫描、embedding 等）"
            " 完成/失败/取消时自动推送 TaskStatusNotification 到 MCP 客户端，无需轮询。"
            " AI Agent 可通过 async_task 查询任务结果。"
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
    "package": {
        "summary": "编译/安装/管理 Delphi 组件包。支持 .dproj/.dpk/.groupproj。",
        "description": "组件包管理 — 编译安装/列出已安装",
        "triggers": ["安装组件、安装包、编译包、dpk安装、注册组件、列出已安装、install package"],
        "details": "自动将设计期包注册到 IDE，运行期包仅编译",
        "workflow": "package(action=install) → package(action=list) 验证安装",
        "actions": {
            "install": "编译并安装组件包。package_path 必需。",
            "list": "列出已安装到 IDE 的组件包。无参数。",
        },
        "examples": [
            'package(action="install", package_path="MyPackage.dpk")  安装组件包',
            'package(action="list")                                    验证安装',
        ],
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
    "code_hosting": {
        "summary": "Git 本地操作 + 代码托管平台。必须使用此工具进行所有 Git 操作，禁止用 bash 直接执行 git。",
        "description": "所有 Git 操作(status/add/commit/push/clone/push_retry)都必须通过此工具，不要用 bash 直接执行 git 命令。code_hosting 自动格式化输出、处理异步推送重试，比原始 bash git 更省 token。同时支持 Gitea/GitHub/GitLab/Gitee/GitCode 平台 API 操作。",
        "triggers": ["git", "status", "add", "commit", "push", "clone", "pull", "提交", "推送", "暂存", "仓库"],
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
        "summary": "经验记忆管理：保存/搜索 AI 成功解决问题的做法，下次遇到类似问题自动复用。save 自动去重。",
        "description": "经验记忆管理 — 保存/搜索/管理 AI 成功解决问题的经验，save 时自动去重合并",
        "triggers": ["经验、记忆、保存经验、搜索经验、之前怎么解决的、我记得"],
        "workflow": "任务成功 → experience(action=save, ...) → 自动去重(>0.85 合并非新增) → 定期 experience(action=prune) 清理低价值条目",
        "actions": {
            "save": "保存经验（自动去重：embedding 相似度 >0.85 时合并非新增）。problem=问题描述, solution=解决步骤, tools_used=用到的工具列表, tags=标签",
            "search": "语义搜索经验。query=搜索关键词, top_k=返回条数, tags=按标签过滤",
            "get": "查看经验详情。id=经验ID",
            "list": "浏览经验列表。tags=过滤标签, sort_by=排序字段, limit=条数",
            "update": "更新经验。id=经验ID, solution/tags/problem 等",
            "merge": "合并多条经验为一条。ids=[id1,id2,...] 至少2个, keep=保留的ID(可选)",
            "prune": "列出低价值经验（按价值升序），供 AI 检查后删除。limit=返回条数",
            "delete": "删除经验。id=经验ID",
        },
    },
}

# 工具名列表（保持顺序，用于 list_tools 和 tool_help 的 enum）
TOOL_NAMES: list = [
    "project",
    "delphi_kb",
    "delphi_file",
    "manage_component",
    "check_environment",
    "async_task",
    "package",
    "get_coding_rules",
    "code_hosting",
    "tool_help",
    "experience",
]

# 精简版 descriptions（用于 list_tools 的 description 字段）
# 规则：一句话用途 + 硬约束（不遵守会报错的规则）
TOOL_SHORT_DESC: dict = {
    "project": (
        "项目全生命周期管理: 编译(compile)/配置(info/set/create)/审计(audit/ast/runtime)。"
        " 用 tool_help('project') 查看各 action 的详细参数。禁止手动 dcc32/msbuild。"
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
    "package": (
        "编译/安装/管理 Delphi 组件包。action=install 安装，action=list 列出已安装。"
    ),
    "get_coding_rules": (
        "获取 Delphi 编码规则。修改 .pas 代码前必须先调用此工具。"
    ),
    "code_hosting": (
        "Git 本地操作(status/add/commit/push/clone) + 代码托管平台(Gitea/GitHub/GitLab/Gitee/GitCode)。"
        " 所有 Git 操作必须使用此工具，禁止用 bash 直接执行 git 命令（更省 token）。"
    ),
    "tool_help": (
        "获取任意工具的完整帮助文档(参数说明/示例/触发词/协作链)。"
        " 不确定某个工具用法时调用此工具。"
    ),
    "experience": (
        "经验记忆管理: 保存/搜索 AI 成功解决问题的做法(语义搜索)。"
        " save 自动去重(>0.85 合并到旧记录)。"
        " 支持 merge(合并多条为一条) / prune(列出低价值条目) 等维护操作。"
    ),
}
