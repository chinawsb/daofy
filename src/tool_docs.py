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
            "创建项目": "project(create) → project(info) → project(compile)",
            "日常编译": "project(compile, project_path=...) 自动识别 .pas/.dproj",
            "审计代码": "project(ast) → 分析 → delphi_file → project(compile)",
            "改配置": "project(set, property_name=...) → project(compile) 验证",
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
            "search": "搜索类/函数/文档(query必需)，kb_type限定范围，search_type限定类型",
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
        "summary": "Delphi 文件(.pas/.dfm/.dproj/.dpr/.dpk/.fmx/.inc)专用操作。禁止用原生 read/write/edit！",
        "description": "Delphi 文件专用操作：读/写(edits)/格式化/备份管理/uses子句增删（编码检测+自动备份+DFM转换）",
        "triggers": [
            "读文件、查看源码、打开文件、cat、写代码、编辑文件、改代码、修改代码",
            "新建文件、格式化、整理代码、恢复备份、回退修改、diff、差异对比",
            "查看备份、还原文件、增删uses、添加单元、删除单元",
            "批量写入、批量修改、多处修改、多 edit、write edits",
        ],
        "file_triggers": "操作 .pas/.dfm/.dproj/.dpk/.fmx/.inc 文件时必须用此",
        "constraints": [
            "❌ 严禁 edit/write/bash echo 直接改 .pas/.dfm（绕过备份+编码检测）",
            "🚫 禁止对同一个文件并行写入，多处修改合并到一次 write(edits=[...])",
            "🚫 format/uses/write 标记脏，需 read 后才能再 write",
        ],
        "features": [
            "自动编码检测(UTF-8/GBK/UTF-16)，自动备份(__history)",
            "DFM二进制↔文本透明转换",
            "1-indexed 行号（参数和输出一致），脏标记机制",
        ],
        "workflow": "get_coding_rules → delphi_file(read)规划修改→ write(edits=[...])一次性写出 → format → compile。write/format/uses 标记脏，需 read 后才能再 write。不同文件可并行。",
        "actions": {
            "read": "读文件，支持分段读取(start_line/end_line)或按类名/函数名定位。所有行号为 1-indexed inclusive。读取时自动清除脏标记。",
            "write": "⭐ 唯一写入接口（已合并 batch_write）。接收 edits 数组，内部自动排序+累积偏移，一次性写出。edits=[{start_line:1, content:'...'}] 全量替换；edits=[{start_line:5, end_line:10, content:'...'}] 部分替换。支持 preview 预览 diff。写入后标记脏。",
            "batch_write": "⚠️ 已废弃，作为 write 的别名保留。请改用 action=write(edits=[...])。",
            "format": "使用 pasfmt 格式化代码。格式化后标记脏。",
            "backup": "备份管理（创建/列表/恢复）",
            "uses": "增删 uses 子句中的单元。成功后标记脏。",
        },
        "examples": [
            'delphi_file(action="read", file_path="Unit1.pas")                                         读文件',
            'delphi_file(action="read", search_type="class", type_name="TForm1")                       搜索类定义',
            'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)              读取第5~15行',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:1,content:"unit ..."}])             全量替换',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:10,end_line:12,content:"替换内容"}])  部分替换第10~12行',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:5,content:"新内容"}], preview=true)   预览 diff（从第5行到末尾）',
            'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"..."},{start_line:18,end_line:21,content:"..."}])  批量替换两处',
            'delphi_file(action="format", file_path="src/Unit1.pas")                                   格式化',
            'delphi_file(action="backup", file_path="Unit1.pas")                                       创建备份',
            'delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")                 列出备份',
            'delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)   恢复',
            'delphi_file(action="uses", uses_action="add", unit_name="System.SysUtils", file_path="Unit1.pas")  增uses',
        ],
        "action_params": {
            "read": {
                "description": "读取文件，支持分段读取或按类名/函数名定位。所有行号为 1-indexed inclusive。",
                "required": ["file_path"],
                "optional": {
                    "start_line": "起始行号（1-indexed inclusive, 默认1）",
                    "end_line": "结束行号（1-indexed inclusive），不传则 start_line+limit-1",
                    "limit": "最大返回行数（默认500，上限1000）",
                    "show_line_numbers": "是否显示 1-indexed 行号前缀（默认 false）",
                    "search_type": "读取模式: path/class/function/record",
                    "type_name": "类名/接口名",
                    "function_name": "函数/过程名",
                },
                "examples": [
                    'delphi_file(action="read", file_path="Unit1.pas")',
                    'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)',
                ],
            },
            "write": {
                "description": "唯一写入接口。edits 内行号为 1-indexed inclusive。全量: [{start_line:1, content:'...'}]；部分: [{start_line:5, end_line:10, content:'...'}]。edits 顺序不限，内部自动排序+累积偏移。相邻区间不能重叠。写入后标记脏。",
                "required": ["file_path", "edits"],
                "optional": {
                    "backup": "写入前自动备份，默认 true",
                    "encoding": "写入编码 auto/utf-8/gbk/utf-16，默认 auto",
                    "auto_format": "写入后自动调用 pasfmt 格式化，默认 false。返回的偏移量已包含格式化造成的行数变化",
                    "force": "跳过续重行检测（默认 false 时检测到重复仅警告不阻断写入）",
                    "preview": "预览模式，只计算 diff 不写盘（不备份、不写入、不格式化），默认 false。预览后清除脏标记，允许继续编辑",
                    "allow_dirty": "跳过脏标记检查（默认 false）。脏标记阻止对未重新读取的文件再次写入，防止 AI 使用过期行号。设 true 可绕过（风险自负）",
                },
                "examples": [
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"新行"},{start_line:18,end_line:21,content:"新行"}])',
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:7,end_line:10,content:"新代码"}], preview=true)',
                ],
            },
            "format": {
                "description": "使用 pasfmt 格式化代码。格式化成功后标记文件脏。",
                "required": ["file_path"],
                "optional": {
                    "mode": "格式化模式: file/code/check，默认 file",
                    "code": "mode=code 时待格式化的代码文本",
                    "config_path": "pasfmt 配置文件路径",
                    "uses_style": "uses子句风格: compact/pasfmt_default",
                    "dry_run": "true=仅检查格式不修改文件",
                },
            },
        },
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
            "异步任务完成/失败时自动推送通知到 MCP 客户端，无需轮询。"
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
        "description": "所有 Git 操作(status/add/commit/push/clone) + 代码托管平台 API。禁止用 bash 执行 git（code_hosting 更省 token 且自动处理异步推送）。",
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
                "create_token": "创建令牌(仅Gitea)", "init_labels": "初始化标签",
                "create_issue": "创建工单", "close_issue": "关闭工单",
                "add_comment": "评论工单", "list_issues": "查询工单",
            },
            "git_sync": {
                "git_status": "仓库状态", "git_add": "暂存文件", "git_commit": "提交",
            },
            "git_async": {
                "git_clone": "克隆(支持 GitHub 镜像)", "git_push": "推送",
                "git_push_retry": "推送(后台自动重试)",
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
            'tool_help(tool_name="delphi_file")',
            'tool_help(tool_name="project")',
        ],
    },
    "delphi_rtti": {
        "summary": "Delphi RTTI 桥接 — 通过 RTTI 发现和调用 Delphi 应用程序的运行时能力。三步法: discover→发现能力, call→调用方法, guide→使用指南。",
        "description": "Delphi RTTI 桥接 — 通过 Enhanced RTTI 发现/调用 Delphi 应用能力",
        "triggers": [
            "RTTI、运行时发现、调用Delphi方法、发现Delphi能力、发布published+public方法",
            "delphi rtti、rtti bridge、运行时类型信息",
        ],
        "constraints": [
            "❌ 需要 Delphi 应用已链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）",
            "❌ 需要 Delphi 2010+ (Enhanced RTTI)",
            "⚠️ 不能发现 protected 和 private 区段的方法/属性",
        ],
        "auto_unit_paths": [
            "VCL 项目 → Vcl.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "FMX 项目 → Fmx.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "以上文件均在 $(DaofyRoot)\\tools\\auto\\，将此路径加入项目 Search path 即可编译",
        ],
        "workflow": "delphi_rtti(action='guide') → discover → call",
        "features": [
            "三步法：guide(使用指南) → discover(能力扫描) → call(方法调用)",
            "自动 JSON Schema 类型映射（15 类 Delphi 类型）",
            "5 分钟缓存，同一应用生命周期内不重复扫描",
            "进程池复用，keep_alive 支持多次调用",
            "AI 注解支持：AIDescription / AIResultDescription / AIExample / AIParamDescription",
        ],
        "actions": {
            "guide": "返回完整使用指南（含类型映射表、最佳实践、故障排除）",
            "discover": "扫描并返回 Delphi 应用所有类的 published+public 方法/属性，含 JSON Schema 参数定义及 AI 注解描述",
            "call": "调用指定类的指定方法，params 为可选参数 dict",
        },
        "action_params": {
            "guide": {
                "description": "获取 delphi_rtti 工具的使用指南",
                "optional": {},
            },
            "discover": {
                "description": "扫描 Delphi 应用的 RTTI 能力",
                "required": ["app_path"],
                "optional": {
                    "class_name": "限定的类名，空串扫描所有",
                    "force": "true 强制刷新缓存（默认 false）",
                    "keep_alive": "true 保持进程运行供后续复用（默认 false）",
                },
            },
            "call": {
                "description": "调用 Delphi 应用的 RTTI 暴露方法",
                "required": ["app_path", "class_name", "method"],
                "optional": {
                    "params": "参数 dict，键名需与 discover 返回的 Schema 一致",
                },
            },
        },
        "examples": [
            'delphi_rtti(action="guide")                                                        获取使用指南',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe")                      扫描所有类',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe", class_name="TMainForm")  扫描指定类',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe", keep_alive=True)      扫描并保持进程',
            'delphi_rtti(action="call", app_path="C:\\App\\MyApp.exe", class_name="TMainForm", method="CreateOrder", params={"customerName":"张三"})  调用方法',
        ],
        "workflow_hints": {
            "首次使用": "delphi_rtti(action='guide') 查看完整使用说明",
            "连接应用": "delphi_rtti(action='discover', app_path='...') → 自动连接 → 发现能力",
            "调用方法": "delphi_rtti(action='call', app_path='...', class_name='...', method='...')",
            "批量调用": "首次使用 keep_alive=True → 多次 call → 自动复用进程",
        },
        "type_mapping": {
            "string": "String/UnicodeString/AnsiString → string",
            "integer": "Integer/Int64/Cardinal/Byte/Word → integer(无符号加minimum:0)",
            "number": "Single/Double/Currency → number",
            "boolean": "Boolean/ByteBool/WordBool/LongBool → boolean",
            "datetime": "TDateTime → string with format:date-time",
            "enum": "枚举类型 → string with enum约束",
            "array": "动态数组/TArray → array, 元素类型递归映射",
            "object": "TObject子类 → object",
            "variant": "Variant → [string,number,boolean,null]",
        },
    },
    "experience": {
        "summary": "经验记忆管理：保存/搜索 AI 成功解决问题的做法，下次遇到类似问题自动复用。save 自动去重。",
        "description": "经验记忆管理 — 保存/搜索/管理 AI 成功解决问题的经验，save 时自动去重合并",
        "triggers": ["经验、记忆、保存经验、搜索经验、之前怎么解决的、我记得"],
        "workflow": "任务成功 → experience(action=save, ...) → 自动去重(>0.85 合并非新增) → 定期 experience(action=prune) 清理低价值条目",
        "actions": {
            "save": "保存经验(自动去重：相似度>0.85时合并)。必要: problem+solution",
            "search": "语义搜索经验。query+top_k",
            "get": "查看经验详情。id=经验ID",
            "list": "浏览列表。tags+sort_by+limit",
            "update": "更新经验。id+要改的字段",
            "merge": "合并多条经验。ids=[id1,id2,...] 至少2个",
            "prune": "列出低价值经验供检查删除",
            "delete": "删除经验。id=经验ID",
            "rebuild_embedding": "重建缺失向量。需先 delphi_kb(build_embedding) 加载模型",
        },
    },
    "daofy_update": {
        "summary": "检查 Daofy 版本更新、执行 git pull 更新（类似 code_hosting 异步模式）。",
        "description": "Daofy 自身更新管理 — 版本检查 / git pull 更新（后台异步+自动重试）",
        "triggers": ["更新、升级、新版本、检查更新、daofy 版本、update、upgrade"],
        "workflow": "启动时后台自动检查 → 智能提示通知 AI → AI 询问用户 → daofy_update(action='update') → async_task 查进度 → 通知重启",
        "actions": {
            "check": "先快速检查（缓存/同步），失败后自动提交后台重试任务（返回 task_id）",
            "check_retry": "强制提交后台自动重试版本检查任务，返回 task_id",
            "update": "提交后台 git pull 任务（单次），返回 task_id",
            "update_retry": "提交后台自动重试 git pull 任务（类似 git_push_retry），返回 task_id",
            "version": "显示当前版本号和安装方式（git/pip）",
        },
        "notes": (
            "启动时服务器会自动在后台检查更新，有新版本时会通过工具响应智能提示通知 AI。\n"
            "check/update 返回 task_id 时，使用 async_task(action=status, task_id=...) 查看进度。\n"
            "任务完成时会自动推送通知到 MCP 客户端。\n"
            "更新完成后需要重启 Daofy 或 AI Agent 使新版本生效。\n"
            "pip 安装用户使用: pip install --upgrade daofy-for-delphi"
        ),
        "examples": [
            'daofy_update(action="check")           检查版本（快速/后台重试）',
            'daofy_update(action="check_retry")     强制后台重试检查',
            'daofy_update(action="update")          后台 git pull 更新',
            'daofy_update(action="update_retry")    后台自动重试 git pull',
            'async_task(action=status, task_id=...) 查询异步任务进度',
            'daofy_update(action="version")         显示当前版本',
        ],
    },
    "generate_copyright": {
        "summary": "生成软著文档（源代码+说明书+汇总表）。",
        "description": "软著文档生成 — 源代码/说明书/汇总表",
        "triggers": ["软著、版权、著作权登记、copyright"],
        "constraints": ["需要 Edge/Chrome 浏览器 headless"],
        "actions": {
            "generate": "生成文档", "validate": "检查配置",
            "update_config": "更新配置(config字典)", "status": "检查浏览器",
            "list": "列出已生成文件", "generate_content": "生成草稿",
            "audit": "审计草稿驳回风险",
        },
        "examples": [
            'generate_copyright(action="validate")',
            'generate_copyright(action="update_config", config={"contact_person":"张三"})',
            'generate_copyright(action="generate")',
            'generate_copyright(action="audit")',
        ],
    },
    "automate_delphi": {
        "summary": "驱动 Delphi 程序自动化测试（GUI 截图 + 控制台交互）。",
        "description": "Delphi 自动化测试(GUI+控制台)",
        "triggers": ["自动化测试、截图、Delphi自动化、控制台测试、automate"],
        "constraints": ["gui 模式需要 Delphi 程序已链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）；console 模式无需 Delphi 端改造"],
        "auto_unit_paths": [
            "VCL 项目 → Vcl.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "FMX 项目 → Fmx.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "以上文件均在 $(DaofyRoot)\\tools\\auto\\，将此路径加入项目 Search path 即可编译",
        ],
        "modes": {
            "gui": {
                "description": "通过命名管道驱动 GUI 程序执行操作并截图。",
                "needs_auto_unit": True,
                "protocol": {
                    "transport": "命名管道 JSON 请求/响应",
                    "async_cmds": "click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type",
                    "sync_cmds": "其它命令",
                },
                "commands": {
                    "goto/click/rclick/dblclick": "激活/点击控件",
                    "hover/move/drag": "鼠标操作",
                    "type/key": "输入/按键",
                    "wait/waitfor": "等待(ms/条件)",
                    "capture/listwnd/dumpstate": "截图/枚举/控件树",
                    "dlgscan/dlgclick/msgscan/msgclick": "弹窗/菜单操作",
                    "rget/rset/rcall/rinspect": "RTTI 读写属性/方法",
                    "dlgfile/snapdir": "文件对话框/截图画目录",
                    "exit": "退出进程",
                },
            },
            "console": {
                "description": "通过 subprocess stdin/stdout 驱动控制台程序交互。无需 Delphi 端改造。",
                "needs_auto_unit": False,
                "params": {
                    "input": "发送到 stdin 的文本",
                    "expect": "等待的 stdout 正则模式",
                    "timeout": "超时秒数（默认 30）",
                    "args": "额外命令行参数数组",
                },
            },
        },
        "examples": [
            'automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"goto","target":"TMainForm"},{"cmd":"capture","target":"main"}])',
            'automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"listwnd"}])',
            'automate_delphi(action="console", app_path="Tool.exe", input="Y\\n", expect="Continue?", timeout=10)',
            'automate_delphi(action="console", app_path="Deploy.exe", input="\\n", expect="success", args=["--silent"])',
        ],
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
    "daofy_update",
    "automate_delphi",
    "generate_copyright",
    "delphi_rtti",
]
# 规则：一句话用途 + 硬约束（不遵守会报错的规则）
TOOL_SHORT_DESC: dict = {
    "project": (
        "项目全生命周期管理: 编译(compile)/配置(info/set/create)/审计(audit/ast/runtime)。"
        " 禁止手动 dcc32/msbuild。详情 tool_help('project')。"
    ),
    "delphi_kb": (
        "搜索 Delphi API/项目代码/文档: 类/函数/语义搜索，构建知识库。"
    ),
    "delphi_file": (
        "Delphi 文件专用操作: read/write(edits格式)/format/backup/uses。"
        " 禁止原生 read/write/edit 修改 .pas/.dfm。"
        " 🚫 同文件多处修改必须合并到一次 write(edits=[...])，不得分多次。"
    ),
    "manage_component": (
        "DFM 组件增/删/改/生成 + PAS 自动同步。"
    ),
    "check_environment": (
        "诊断 Delphi 编译环境: 检测编译器/安装 pasfmt。首次使用或编译前先调用。"
    ),
    "async_task": (
        "管理后台异步任务(知识库构建等): 查进度/获取结果/取消。"
    ),
    "package": (
        "编译/安装 Delphi 组件包。action=install 装，action=list 查已装。"
    ),
    "get_coding_rules": (
        "获取 Delphi 编码规则。写/改 Delphi 代码前必须先调用！"
    ),
    "code_hosting": (
        "所有 Git 操作(status/add/commit/push/clone) + 代码托管平台 API。"
        " 禁止用 bash 执行 git（必须用此工具）。"
    ),
    "tool_help": (
        "获取工具完整帮助文档: 参数说明/示例/触发词。用法不清时调用。"
    ),
    "experience": (
        "经验记忆管理: 保存/搜索 AI 经验(save自动去重)。支持 merge/prune/rebuild_embedding 维护。"
    ),
    "daofy_update": (
        "检查 Daofy 版本更新/执行 git pull。支持后台异步+自动重试（类似 code_hosting）。"
        " action=check(快速/后台重试)/check_retry/update(后台git pull)/update_retry/version。"
    ),
    "automate_delphi": (
        "Delphi 自动化测试(action=gui: GUI操作+截图/action=console: 控制台交互)。"
        " gui 需 Delphi 端链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）；console 无需改造。支持 keep_alive。"
    ),
    "generate_copyright": (
        "生成软著文档(源代码+说明书+汇总表)，浏览器 PDF 渲染+自动校验。"
    ),
    "delphi_rtti": (
        "Delphi RTTI 桥接 — 通过 RTTI 发现和调用 Delphi 应用程序的运行时能力。"
        " 三步法: discover→发现能力, call→调用方法, guide→使用指南。"
        " 首次使用先 action='guide' 获取完整说明。"
        " 需要链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）。"
    ),
}
