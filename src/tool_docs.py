"""
Tool 完整文档字典 — 供 tool_help 工具按需查询

每个工具包含：简介、触发词、协作链、全部 action 说明、示例、降级策略等。
description 字段是精简版本的 1-2 句简介，其他字段都是 AI 按需获取的详细说明。
"""

TOOL_HELP_DOCS: dict = {
    "delphi_project": {
        "summary": "Delphi 项目全生命周期管理：编译/配置查看/代码与 UI 布局审计。支持 .dproj/.dpr/.dpk。",
        "description": "Delphi 项目全生命周期管理 — 编译/配置/审计",
        "triggers": [
            "【仅限 Delphi】编译、构建、生成exe、语法检查、编译报错、build、compile、msbuild、dcc32",
            "【仅限 Delphi】项目文件、dproj、工程配置、创建项目、添加配置、删除配置",
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
            "layout": "静态 DFM UI 布局审计，基于 DFM 几何和属性检测重叠、越界、对齐、间距、文本标签-字段配对和 TabOrder",
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
                    "target_platform": "目标平台快捷参数，如 win32/win64；create 时等价于 platforms 单项",
                    "platforms": "目标平台列表，如 ['Win32','Win64']；默认 ['Win32']",
                    "sources": "初始源文件列表",
                    "form_units": "同时生成 Form 桩代码，如 ['Unit1','Main']",
                },
                "examples": [
                    'project(action="create", project_path="App.dproj", main_source="App.dpr")',
                    'project(action="create", project_path="App64.dproj", main_source="App64.dpr", target_platform="win64")',
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
            "layout": {
                "description": "静态审计 .dfm 布局质量，适合 AI 生成窗体后立即检查。",
                "optional": {
                    "base_dir": "递归扫描目录下的 .dfm 文件",
                    "file_path": "单个 .dfm 文件",
                    "output_format": "report/json，默认 report",
                },
                "examples": [
                    'project(action="layout", base_dir="src")',
                    'project(action="layout", file_path="MainForm.dfm", output_format="json")',
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
        "summary": "搜索 Delphi API/项目代码/三方库/文档(类/函数/语义搜索)，构建知识库。",
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
            'delphi_kb(query="TfrxReport", kb_type="thirdparty")                搜索三方库(如 FastReport)',
            'delphi_kb(action="stats")                                          查看统计',
            'delphi_kb(action="build", kb_type="project")                       构建项目知识库',
        ],
    },
    "delphi_file": {
        "summary": "Delphi 文件(.pas/.dfm/.dproj/.dpr/.dpk/.fmx/.inc)专用读写/搜索/替换入口。Delphi 文件必须用 delphi_file，不要用内置 Read/Edit/Write/grep。",
        "description": "Delphi 文件专用操作：读/写(edits)/replace/insert/delete/格式化/备份管理/encoding转换/uses子句增删（编码检测+自动备份+DFM转换）。AI 工具路由规则：读取或修改 Delphi 文件都必须选 delphi_file。",
        "triggers": [
            "读文件、查看源码、打开文件、cat、Agent内置Read、built-in Read、写代码、编辑文件、改代码、修改代码、Agent内置Edit/Write",
            "新建文件、格式化、整理代码、恢复备份、回退修改、diff、差异对比",
            "查看备份、还原文件、增删uses、添加单元、删除单元",
            "批量写入、批量修改、多处修改、多 edit、write edits",
        ],
        "file_triggers": "看到 .pas/.dfm/.dproj/.dpk/.dpr/.fmx/.inc 文件路径时必须用此；读取也算",
        "constraints": [
            "❌ Delphi 文件必须用 delphi_file 读写/搜索/正则匹配+替换，不要用内置 Read/Edit/Write/grep",
            "🚫 禁止对同一个文件并行写入，多处修改合并到一次 write(edits=[...])",
            "🚫 format/uses/write 标记脏，需 read 后才能再 write",
        ],
        "features": [
            "自动编码检测(UTF-8/GBK/UTF-16)，自动备份(__history)",
            "DFM二进制↔文本透明转换",
            "1-indexed 行号（参数和输出一致），脏标记机制",
        ],
        "workflow": "get_coding_rules → delphi_file(read)规划修改→ replace/insert/delete/write(edits=[...])一次性写出 → format → compile。write/replace/insert/delete/format/uses 标记脏，需 read 或 old_content 校验后才能继续写。不同文件可并行。",
        "client_wrappers": [
            "直接暴露 MCP 工具的客户端：调用 delphi_file 时只传 Daofy 参数，例如 action/file_path/start_line/end_line。",
            "Trae 等只暴露 run_mcp 的客户端：外层传 server_name 和 tool_name，内层 args 才放 Daofy 参数；server_name 是该客户端 MCP 配置里的 Daofy 服务别名，按实际配置填写，不是 Daofy 固定值。",
            "不要把 server_name/tool_name 混进 delphi_file 的参数对象，也不要把 action/file_path/start_line/end_line 平铺到 run_mcp 外层。",
            'Trae 示例：run_mcp({"server_name":"<client-configured-daofy-server-name>","tool_name":"delphi_file","args":{"action":"read","file_path":"C:\\\\path\\\\Unit1.pas","start_line":1,"end_line":100}})',
        ],
        "actions": {
            "read": "读文件，支持分段读取(start_line/end_line)或按类名/函数名定位。所有行号为 1-indexed inclusive。项目源码搜索用 search_in='project' + project_path。读取时自动清除脏标记。",
            "write": "兼容写入接口（旧语义）。接收 edits 数组，内部自动排序+累积偏移，一次性写出。edits=[{start_line:1, content:'...'}] 全量替换；edits=[{start_line:5, end_line:10, content:'...'}] 部分替换。支持 dry_run 预览 diff。写入后标记脏。",
            "replace": "按行范围替换。现有文件中每个 edit 必须提供非空 old_content，工具用行号+旧内容校验命中范围。",
            "insert": "按 start_line 锚点插入。现有文件中每个 edit 必须提供非空 old_content（单行锚点，无需带换行符），position=before/after。",
            "delete": "按行范围删除。现有文件中每个 edit 必须提供非空 old_content，content 可省略。",
            "format": "使用 pasfmt 格式化代码。格式化后标记脏。",
            "backup": "备份管理（创建/列表/恢复）",
            "encode": "文件编码转换。自动检测源编码，写入目标编码。支持 utf-8/utf-8-sig/gbk/utf-16/utf-16-le/utf-16-be/ansi。自动备份。转换后标记脏。",
            "uses": "增删 uses 子句中的单元。成功后标记脏。",
            "grep": "正则搜索+多级过滤+替换。pattern 支持行内 /xxx/i 语法指定 flag。filter_pattern 二级 AND 过滤，exclude_pattern NOT 排除。replace 参数切换为替换模式（dry_run 默认 True）。context/count 控制输出。多行 flag(/m)或 dotall(/s)自动切换全文搜索。",
            "fix_garbled": "修复中文乱码：自动检测 U+FFFD 替换字符、缺失 UTF-8 BOM、编码误检测并修复。支持 backup 备份。",
        },
        "examples": [
            'delphi_file(action="read", file_path="Unit1.pas")                                         读文件',
            'delphi_file(action="read", search_type="class", type_name="TForm1")                       搜索类定义',
            'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)              读取第5~15行',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:1,content:"unit ..."}])             全量替换',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:10,end_line:12,content:"替换内容"}])  部分替换第10~12行',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:5,content:"新内容"}], dry_run=true)   预览 diff（从第5行到末尾）',
            'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"..."},{start_line:18,end_line:21,content:"..."}])  批量替换两处',
            'delphi_file(action="replace", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧代码",content:"新代码"}])  按原文替换',
            'delphi_file(action="insert", file_path="Unit1.pas", edits=[{start_line:10,position:"before",old_content:"  OldCall;",content:"  NewCall;\\n"}])  锚点插入',
            'delphi_file(action="delete", file_path="Unit1.pas", edits=[{start_line:10,end_line:12,old_content:"  OldCall;\\n  OtherCall;\\n"}])  按原文删除',
            'delphi_file(action="format", file_path="src/Unit1.pas")                                   格式化',
            'delphi_file(action="backup", file_path="Unit1.pas")                                       创建备份',
            'delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")                 列出备份',
            'delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)   恢复',
            'delphi_file(action="uses", uses_action="add", unit_name="System.SysUtils", file_path="Unit1.pas")  增uses',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i")                          正则搜索(不区分大小写)',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/^procedure/m", context=2)             多行模式+上下文的搜索',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i", replace="TNewClass", dry_run=True)  替换预览',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8-sig")                       添加 UTF-8 BOM',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="gbk")                             转为 GBK',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8", from_encoding="gbk")      指定 GBK→UTF-8',
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
                    "search_in": "搜索范围 all/delphi/project/thirdparty；project 需要 project_path",
                    "project_path": "项目文件路径，用于 search_in=project 或限制写入路径",
                    "type_name": "类名/接口名",
                    "function_name": "函数/过程名",
                },
                "examples": [
                    'delphi_file(action="read", file_path="Unit1.pas")',
                    'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)',
                    'delphi_file(action="read", search_type="class", type_name="TMainForm", search_in="project", project_path="App.dproj")',
                ],
            },
            "write": {
                "description": "兼容写入接口。新调用优先使用 replace/insert/delete。edits 内行号为 1-indexed inclusive，写入后标记脏。",
                "required": ["file_path", "edits"],
                "optional": {
                    "backup": "写入前自动备份，默认 true",
                    "encoding": "写入编码 auto/utf-8/gbk/utf-16，默认 auto",
                    "auto_format": "写入后自动调用 pasfmt 格式化，默认 false。返回的偏移量已包含格式化造成的行数变化",
                    "force": "跳过重复检测和脏标记检查（默认 false 时检测到重复仅警告不阻断写入）",
                    "dry_run": "设为 true 时只预览 diff 不写盘（不备份、不写入、不格式化），默认 false。dry_run 不清除脏标记，后续 write 仍需 read 或 old_content。",
                    "old_content": "写在每个 edit 内；将被替换区间的非空旧内容。写入前忽略字符串外空白后比较，避免行号错位。注意：不要带尾部 \\r\\n 换行符，工具会自动忽略",
                    "allow_dirty": "跳过脏标记检查（默认 false）。优先使用每个 edit 的非空 old_content；裸 allow_dirty 风险自负",
                    "project_path": "可选；提供时限制 file_path 必须位于项目目录内",
                },
                "examples": [
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"新行"},{start_line:18,end_line:21,content:"新行"}])',
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧行",content:"新行"}])',
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:7,end_line:10,content:"新代码"}], dry_run=true)',
                ],
            },
            "replace": {
                "description": "替换一个或多个行范围。现有文件中每个 edit 必须提供非空 old_content，工具用行号+旧内容校验命中范围。",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "设为 true 时只预览 diff 不写盘，默认 false。推荐使用",
                },
                "examples": [
                    'delphi_file(action="replace", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧代码",content:"新代码"}])',
                ],
            },
            "insert": {
                "description": "以 start_line 指向的锚点行为基准插入内容。old_content 必填，用来校验锚点行（单行内容，无需带换行符）；position=before/after。",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "设为 true 时只预览 diff 不写盘，默认 false。推荐使用",
                },
                "examples": [
                    'delphi_file(action="insert", file_path="Unit1.pas", edits=[{start_line:10,position:"before",old_content:"  OldCall;",content:"  NewCall;\\n"}])',
                ],
            },
            "delete": {
                "description": "删除一个或多个行范围。每个 edit 必须提供非空 old_content；content 可省略。",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "设为 true 时只预览 diff 不写盘，默认 false。推荐使用",
                },
                "examples": [
                    'delphi_file(action="delete", file_path="Unit1.pas", edits=[{start_line:10,end_line:12,old_content:"旧代码"}])',
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
            "encode": {
                "description": "文件编码转换。支持自动检测源编码（from_encoding='auto'）。转换前自动备份，转换后标记脏。",
                "required": ["file_path", "to_encoding"],
                "optional": {
                    "from_encoding": "源编码（auto=自动检测，推荐始终用 auto；如需显式指定，请确保编码名称准确无误，否则会导致解码失败或乱码）",
                    "backup": "转换前是否备份到 __history（默认 true）",
                    "dry_run": "预览模式: 只输出转换信息不写盘（默认 false）",
                },
                "examples": [
                    'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8-sig")',
                    'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="gbk")',
                    'delphi_file(action="encode", file_path="Unit1.pas", from_encoding="gbk", to_encoding="utf-8")',
                ],
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
        "description": "所有 Git 操作(status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/stash/tag/push/clone) + 代码托管平台 API。禁止用 bash 执行 git（code_hosting 更省 token 且自动处理异步推送）。",
        "triggers": ["git", "status", "diff", "show", "log", "add", "commit", "push", "clone", "pull", "branch", "stash", "提交", "推送", "暂存", "仓库"],
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
                "create_issue": "创建工单", "get_issue": "查看工单",
                "edit_issue": "修改工单", "set_labels": "设置工单标签",
                "close_issue": "关闭工单", "add_comment": "评论工单",
                "list_issues": "查询工单",
                "create_pull": "创建 PR/MR", "get_pull": "查看 PR/MR",
                "list_pulls": "查询 PR/MR", "edit_pull": "修改 PR/MR",
                "merge_pull": "合并 PR/MR", "close_pull": "关闭 PR/MR",
                "reopen_pull": "重开 PR/MR",
                "create_release": "创建 Release", "get_release": "查看 Release",
                "list_releases": "查询 Release", "edit_release": "修改 Release",
                "delete_release": "删除 Release",
            },
            "git_sync": {
                "git_status": "仓库状态", "git_diff": "查看差异", "git_show": "查看提交/对象",
                "git_log": "提交历史", "git_add": "暂存文件", "git_commit": "提交",
                "git_fetch": "拉取远程引用(支持 async_mode)", "git_pull": "拉取并合并(支持 async_mode)",
                "git_branch": "分支列表/创建/删除", "git_switch": "切换/创建分支",
                "git_merge": "合并分支(支持 async_mode)", "git_restore": "恢复显式文件",
                "git_unstage": "取消暂存", "git_stash": "stash 管理", "git_tag": "标签列表/创建/删除",
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
            'tool_help(tool_name="delphi_project")',
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
    "ocr": {
        "summary": "图像分析：PP-OCRv6 文字识别 + 截图差异对比 + 颜色分析 + 图标匹配。",
        "description": "图像分析 — 文字识别/截图对比/颜色分析/模板匹配",
        "triggers": [
            "OCR、文字识别、图片文字、识别图片、提取文字、图像文字",
            "图片转文字、截图识别、ocr识别、optical character recognition",
            "截图对比、图像差异、diff、颜色分析、图标匹配、模板匹配",
        ],
        "constraints": [
            "❌ image_path 必须为本地存在的文件路径",
            "❌ 不支持 base64 编码图片（需先保存为文件）",
            "⚠️ 首次调用时会自动下载模型（~65MB），可能需要等待",
            "⚠️ 模型缓存到 data/ocr-models/，后续调用无需下载",
            "⚠️ diff/color/match 使用 OpenCV/Pillow，不需要 OCR 模型",
        ],
        "workflow": "ocr(action=status) → 确认模型就绪 → ocr(action=recognize, image_path=...)",
        "auto_backend": (
            "自动选择推理后端:\n"
            "  Intel CPU + openvino → OpenVINO（利用 VNNI/AMX 加速）\n"
            "  AMD / 其他 CPU       → ONNX Runtime\n"
            "  Python ≥ 3.14        → ONNX Runtime（PaddlePaddle 不兼容）"
        ),
        "actions": {
            "recognize": "完整 OCR 管线：检测 → 方向分类 → 文字识别 → 返回结构化结果",
            "detect": "仅文本框检测，不识别文字（返回 box + score）",
            "status": "查询模型加载状态和后端信息",
            "diff": "截图差异对比：两张图片的像素级对比，返回变化区域",
            "color": "区域颜色分析：指定区域的 RGB 平均色/主色/亮度/灰度判断",
            "match": "图标模板匹配：在截图中查找指定图标/图案的位置",
        },
        "action_params": {
            "recognize": {
                "description": "检测并识别图片中所有文字",
                "required": ["image_path"],
                "optional": {},
                "examples": [
                    'ocr(action="recognize", image_path="C:\\screenshot.png")',
                    'ocr(action="recognize", image_path="data/test_img.png")',
                ],
            },
            "detect": {
                "description": "仅检测文本框位置",
                "required": ["image_path"],
                "examples": [
                    'ocr(action="detect", image_path="screenshot.png")',
                ],
            },
            "status": {
                "description": "查询服务状态（后端类型、模型是否已加载）",
                "examples": [
                    'ocr(action="status")',
                ],
            },
            "diff": {
                "description": "比较两张截图，找出视觉差异区域",
                "required": ["baseline", "current"],
                "optional": {"threshold": "像素差异阈值 0-255（默认 10）",
                             "output_dir": "差异图输出目录（可选）"},
                "examples": [
                    'ocr(action="diff", baseline="before.png", current="after.png")',
                    'ocr(action="diff", baseline="100%.png", current="150%.png", threshold=5)',
                ],
            },
            "color": {
                "description": "分析图片指定区域的颜色特征",
                "required": ["image_path"],
                "optional": {"region": "分析区域 [x,y,w,h]，不传则全图"},
                "examples": [
                    'ocr(action="color", image_path="screenshot.png", region=[10,20,100,25])',
                    'ocr(action="color", image_path="button.png")',
                ],
            },
            "match": {
                "description": "在截图中查找指定图标/图案",
                "required": ["image_path", "template_path"],
                "optional": {"threshold": "匹配阈值 0-1（默认 0.8）"},
                "examples": [
                    'ocr(action="match", image_path="screenshot.png", template_path="save_icon.png")',
                ],
            },
        },
        "examples": [
            'ocr(action="status")                                                   查询模型状态',
            'ocr(action="recognize", image_path="screenshot.png")                   完整OCR识别',
            'ocr(action="detect", image_path="screenshot.png")                      仅文本框检测',
            'ocr(action="diff", baseline="base.png", current="new.png")             截图差异对比',
            'ocr(action="color", image_path="btn.png", region=[0,0,50,20])          区域颜色分析',
            'ocr(action="match", image_path="shot.png", template_path="icon.png")   图标匹配',
        ],
        "response_format": {
            "recognize": (
                "{\n"
                '  "status": "ok",\n'
                '  "action": "recognize",\n'
                '  "count": 3,\n'
                '  "results": [\n'
                "    {\n"
                '      "text": "确定",\n'
                '      "confidence": 0.97,\n'
                '      "box": [[10,20],[100,20],[100,50],[10,50]],\n'
                '      "det_score": 0.85\n'
                "    },\n"
                "    ...\n"
                "  ]\n"
                "}"
            ),
            "status": (
                "{\n"
                '  "backend": "onnxruntime",\n'
                '  "model_size": "medium",\n'
                '  "loaded": true,\n'
                '  "models_available": {"det": true, "rec": true, "cls": true}\n'
                "}"
            ),
            "diff": (
                "{\n"
                '  "changed": true,\n'
                '  "diff_pixels": 1234,\n'
                '  "diff_percent": 0.52,\n'
                '  "regions": [{"bbox": [10,20,100,60], "area_pct": 0.3, "mean_diff": 45.3}]\n'
                "}"
            ),
            "color": (
                "{\n"
                '  "avg_color": {"r": 255, "g": 0, "b": 0},\n'
                '  "is_grayscale": false,\n'
                '  "brightness": 0.33\n'
                "}"
            ),
            "match": (
                "{\n"
                '  "found": true,\n'
                '  "match_count": 1,\n'
                '  "matches": [{"bbox": [100,200,130,230], "confidence": 0.92}]\n'
                "}"
            ),
        },
        "workflow_hints": {
            "首次使用": "ocr(action='status') 检查模型是否已下载好",
            "日常识别": "ocr(action='recognize', image_path='...') 直接识别",
            "快速检测": "ocr(action='detect', image_path='...') 先看文本框位置",
            "截图对比": "ocr(action='diff', baseline='...', current='...') 检查 UI 是否变化",
            "颜色验证": "ocr(action='color', image_path='...', region=[...]) 检查按钮颜色",
            "图标查找": "ocr(action='match', image_path='...', template_path='icon.png') 确认图标出现",
        },
    },
    "automate_delphi": {
        "summary": "驱动 Delphi 程序自动化测试（GUI 截图 + 控制台交互）。支持感知-规划-执行-反馈循环。",
        "description": "Delphi 自动化测试 — 感知·规划·执行·反馈",
        "triggers": ["自动化测试、截图、Delphi自动化、控制台测试、automate"],
        "constraints": ["gui 模式需要 Delphi 程序已链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）；console 模式无需 Delphi 端改造"],
        "auto_unit_paths": [
            "VCL 项目 → Vcl.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "FMX 项目 → Fmx.DaofyAutomation.pas（自动引用 DaofyAutomation.Base / RttiAttributes / RttiDiscovery）",
            "callgraph 可选诊断 → 额外 uses DaofyAutomation.CallGraph，并确保 tools\\stacktrace 在 Search path 中",
            "核心自动化文件在 $(DaofyRoot)\\tools\\auto\\，callgraph 实现在 $(DaofyRoot)\\tools\\stacktrace\\；使用 action=prepare 自动注册所需全局搜索路径",
        ],
        "architecture": {
            "pattern": "感知 → 规划 → 执行 → 反馈（循环）",
            "brain": "大模型负责决策和规划",
            "hands": "MCP 工具负责感知和执行",
            "see_also": "脚本生成流程: MCP Resource delphi://automation/script-generation-workflow；资源索引: delphi://resources；详细方法论 + 提示词模板 + 经验优化闭环 + 脚本缓存: get_coding_rules(section=\"automation\")",
            "self_learning": (
                "通过 experience 工具 + delphi://coding-rules / get_coding_rules(section=\"automation\") 实现："
                "测试前检索经验 → 测试中记录失败/恢复 → 测试后保存经验 → "
                "定期合并抽象为通用模式。让大模型从每次测试中学习进化。"
            ),
        },
        "modes": {
            "gui": {
                "description": "通过命名管道驱动 GUI 程序执行操作并截图。",
                "needs_auto_unit": True,
                "stop_on_failure": "默认 true。首个失败后停止执行后续依赖步骤，并在 report.steps 中标记 skip；需要全量探索时可显式设 false。",
                "script_shape": (
                    "script 可为文件路径、JSON 字符串、步骤数组，或推荐的完整脚本对象 "
                    '{"test_name":"smoke","steps":[...]}；对象内除 steps 外的字段会作为 script_metadata 返回。'
                ),
                "environment": (
                    "Optional `env` / `environment` top-level script fields inject temporary child-process "
                    "environment variables. Values are applied only at tested-process startup, are not persisted, "
                    "and reports redact values to {count, names}. Changing env for a keep_alive process restarts "
                    "the tested app; the MCP server itself does not need to restart."
                ),
                "callgraph_diagnostics": (
                    "完整脚本对象可设 callgraph_diagnostics=true，并在失败步骤声明 handler/entry/callgraph_target；"
                    "报告会附加 diagnostics.callgraph，默认关闭。"
                ),
                "protocol": {
                    "transport": "命名管道 JSON 请求/响应",
                    "async_cmds": "click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type",
                    "sync_cmds": "goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception",
                },
                "commands_by_phase": {
                    "perception": {
                        "description": "获取 UI 当前状态",
                        "cmds": {
                            "capture": "截取当前窗口截图（验证状态/对比预期）",
                            "dumpstate": "导出完整控件树JSON（含所有RTTI属性，定位控件路径）",
                            "formsum": "窗体摘要JSON — 从 dumpstate 提炼纯净结构：关键字段展平，Controls 嵌套层级，省 token",
                            "listwnd": "枚举所有顶层窗口（新窗口出现时获取句柄）",
                            "callgraph": "获取函数调用关系图（direction=callees/callers；max_depth 控制 BFS；project_only/exclude_prefixes/include_prefixes 过滤；edge_limit 控制输出上限并返回 edge_count/returned_count/truncated；边包含 call_addr/call_file/call_line/category；需额外 uses DaofyAutomation.CallGraph + Detailed .map）",
                            "callgraph_diff": "对 baseline 与当前 callgraph 做边级 added/removed/unchanged 对比（默认 compare_by=name，可选 addr/full；可用 save_as 保存快照，路径限制在 snapshots_dir；Python 侧命令，管道内仍请求 callgraph）",
                            "callgraph_path": "查询 source 到 target 的调用路径（max_depth/max_paths/include_prefixes 控制范围；返回 found 和 paths；Delphi 侧命令）",
                            "callgraph_impact": "变更影响分析：对 functions/targets 或 file+line/locations 批量查询 callers，汇总入口候选和 unresolved（Python 侧命令，管道内仍请求 callgraph）",
                            "callgraph_select_tests": "根据 callgraph_impact 和测试 handler 映射推荐回归脚本（Python 侧命令）",
                            "callgraph_failure_diag": "把失败步骤和 callgraph 摘要组合成 diagnostics.callgraph（Python 侧命令）",
                            "callgraph_boundary_check": "按前缀规则检查架构边界违规调用（Python 侧命令）",
                            "callgraph_refactor_check": "重构前列出受影响调用者并标注静态图盲区（Python 侧命令）",
                            "callgraph_orphan_candidates": "从符号表和 direct call 图生成低置信孤岛候选（Python 侧命令）",
                            "callgraph_explain_exception": "用 callgraph/impact 解释异常栈顶函数的上下游影响（Python 侧命令）",
                            "msgscan": "扫描 MessageBox 弹窗（同步，每步执行后必做）",
                            "dlgscan": "扫描文件对话框状态（同步）",
                            "rinspect": "RTTI 成员发现：列出控件的属性名+类型+方法（非属性值）",
                        },
                    },
                    "execution": {
                        "description": "对 UI 执行操作",
                        "cmds": {
                            "goto": "导航到目标控件（先定位再操作）",
                            "click": "单击（异步）",
                            "rclick": "右键单击（异步）",
                            "dblclick": "双击（异步）",
                            "type": "输入文本（异步）",
                            "key": "按键 Tab/Enter/Esc（异步）",
                            "hover": "鼠标悬停（异步）",
                            "move": "鼠标移动到坐标（异步）",
                            "drag": "拖拽操作（异步）",
                            "msgclick": "点 MessageBox 按钮 确认/取消（异步）",
                            "dlgclick": "点文件对话框按钮 打开/保存（异步）",
                            "dlgfile": "文件对话框输入路径（同步）",
                            "rcall": "RTTI 调用方法（异步，首选降级方案）",
                            "rset": "RTTI 设置属性值（异步）",
                            "uiaclick": "UIA 单击（按 Name 属性匹配，步 step 添加 via:'uia' 可复用 click/goto/get 命令）",
                            "uiagoto": "UIA 导航到控件",
                            "uiaget": "UIA 读取控件 Name",
                            "uiascan": "UIA 扫描控件树",
                        },
                        "uia_note": "通过 step 中加 via:'uia' 字段可将 click/goto/get/set/wait 命令路由到 Python UIA（uiautomation 库），绕过 Delphi 管道和主线程死锁问题。当前台有 IFileDialog / DirectUI / #32770 等 Win32 消息无法穿透的对话框时，使用 UIA 命令。",
                    },
                    "verification": {
                        "description": "验证执行结果。新脚本用 assert_expr 写 Python 表达式；自然语言预期写 expected/note：{'cmd':'rget','target':'btnSave.Enabled','assert_expr':\"actual=='True'\"}",
                        "cmds": {
                            "capture": "操作后截图对比",
                            "waitfor": "等待条件满足（控件可见/消失）",
                            "wait": "固定时间等待（毫秒）",
                            "rget": "RTTI 读属性值（同步，首选结果断言）",
                            "rinspect": "RTTI 成员发现（同步，查看属性名/类型/方法，非值）",
                        },
                    },
                },
                # Legacy flat commands for backward compat
                "commands": {
                    "goto/click/rclick/dblclick": "激活/点击控件",
                    "hover/move/drag": "鼠标操作",
                    "type/key": "输入/按键",
                    "wait/waitfor": "等待(ms/条件)",
                    "capture/listwnd/dumpstate/formsum": "截图/枚举/控件树/窗体摘要",
                    "dlgscan/msgscan/msgclose": "弹窗/菜单扫描与关闭（同步）",
                    "dlgclick/msgclick": "弹窗/菜单点击（异步）",
                    "rget": "RTTI 读属性值（同步）",
                    "callgraph": "获取函数调用关系图（direction=callees/callers；max_depth 控制 BFS；project_only/exclude_prefixes/include_prefixes 过滤；edge_limit 控制输出上限并返回 edge_count/returned_count/truncated；边包含 call_addr/call_file/call_line/category）",
                    "callgraph_diff": "对 baseline 与当前 callgraph 做边级 added/removed/unchanged 对比（默认 compare_by=name，可选 addr/full；save_as/baseline_path 限制在 snapshots_dir）",
                    "callgraph_path": "查询 source 到 target 的调用路径，支持 max_depth/max_paths/include_prefixes",
                    "callgraph_impact": "对变更函数或 file/line 位置批量查询 callers，汇总入口候选和 unresolved",
                    "callgraph_select_tests": "根据 impact 和测试元数据选择建议回归脚本",
                    "callgraph_failure_diag": "为失败步骤生成 callgraph 诊断摘要",
                    "callgraph_boundary_check": "按前缀规则检查架构边界",
                    "callgraph_refactor_check": "重构安全检查，输出受影响调用者和盲区提示",
                    "callgraph_orphan_candidates": "死代码/孤岛候选，结果仅作候选不可自动删除",
                    "callgraph_explain_exception": "异常栈扩展解释，输出上下游调用摘要",
                    "rset/rcall": "RTTI 写属性/调用方法（异步）",
                    "rinspect": "RTTI 成员发现（同步）",
                    "dlgfile/snapdir": "文件对话框/截图目录（同步）",
                    "exit": "退出进程",
                    "uiaclick/uiagoto/uiaget/uiascan/uiaset/uiawait": "UIA 自动化（Python 端执行，按 Name/ClassName 匹配控件，不受 Delphi 管道/线程限制）",
                    "via:'uia'": "路由字段：对 click/goto/get/set/wait 加 via:'uia' 可改用 Python UIA 执行（如 {\"cmd\":\"click\",\"target\":\"打开(&O)\",\"via\":\"uia\"}）",
                },
            },
            "prepare": {
                "description": "将 DaofyAutomation 路径注册到 Delphi 全局 Library Search Path（注册表）。一劳永逸，此后任何项目无需额外配置即可 uses DaofyAutomation。",
                "needs_auto_unit": False,
                "params": {},
                "effect": "读取 HKCU\\SOFTWARE\\Embarcadero\\BDS\\{version}\\Library\\{platform} 的 Search Path，若 tools/auto/ 或 tools/stacktrace/ 不在其中则追加。影响 Win32 + Win64 双平台。",
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
        "planning_guide": {
            "principle": "每步明确标注阶段（perceive/execute/verify），「一步一验证」",
            "prefer_order": ["RTTI 调用（最稳定）", "控件级 goto+click（最常用）", "坐标级 move+click（兼容模式）"],
            "failure_recovery": {
                "waitfor_timeout": "capture 当前状态 → 分析原因 → 重试或上报",
                "click_error": "dumpstate 查 Enabled/Visible → 降级 RTTI 或上报",
                "unexpected_dialog": "msgscan → msgclick(OK/Cancel) → capture 新状态",
                "rtti_exception": "降级到 goto+click 操作",
            },
            "prompt_templates": (
                "delphi://coding-rules / get_coding_rules(section=\"automation\") 提供 4 个可复用的提示词模板："
                "F1=测试规划模板（从目标到步骤序列），"
                "F2=单步执行协议（前置感知→执行→等待→验证），"
                "F3=失败恢复模板（诊断→决策→恢复→学习），"
                "F4=经验保存模板（将测试成果沉淀为经验）。"
                "\n用法: get_coding_rules(section=\"automation\") 获取完整模板。"
            ),
            "experience_optimization": (
                "通过 experience 工具实现持续自我进化（见 delphi://coding-rules / get_coding_rules(section=\"automation\")）："
                "\n1) 测试前: experience/search 检索同类场景的历史经验 → 调整策略"
                "\n2) 测试中: 遇到失败按 F3 恢复，记录学习"
                "\n3) 测试后: experience/save 按 F4 模板保存经验（自动去重）"
                "\n4) 定期: experience/merge 合并同类经验 → experience/prune 淘汰低价值记录"
            ),
        },
        "examples": [
            'automate_delphi(action="prepare")  # ← 首次使用前先注册全局搜索路径',
            'automate_delphi(action="gui", app_path="App.exe", script={"test_name":"main-smoke","steps":[{"cmd":"goto","target":"TMainForm"},{"cmd":"capture","target":"main"}]})',
            'automate_delphi(action="gui", app_path="App.exe", stop_on_failure=true, script=[{"cmd":"rget","target":"StatusBar.Caption","assert_expr":"actual==\'OK\'"}])',
            'automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"listwnd"}])',
            'automate_delphi(action="console", app_path="Tool.exe", input="Y\\n", expect="Continue?", timeout=10)',
            'automate_delphi(action="console", app_path="Deploy.exe", input="\\n", expect="success", args=["--silent"])',
            '# 感知-规划-执行-反馈 完整循环示例见 get_coding_rules(section="automation")',
        ],
    },
}

# 工具名列表（保持顺序，用于 list_tools 和 tool_help 的 enum）
TOOL_NAMES: list = [
    "delphi_project",
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
    "ocr",
]
# 规则：一句话用途 + 硬约束（不遵守会报错的规则）
TOOL_SHORT_DESC: dict = {
    "delphi_project": (
        "Delphi 项目生命周期: 编译/配置/审计。"
        " compile(编译)/info(配置查看)/set(修改)/add_config/remove_config/"
        "add_source/remove_source/audit(静态分析50+规则)/ast(代码骨架)/runtime(注册表检查)/layout(UI布局审计)。"
        " 仅支持 Delphi 项目文件(.dproj/.dpr/.dpk)。"
        " 禁止手动 dcc32/msbuild。"
    ),
    "delphi_kb": (
        "搜 Delphi API/项目代码/文档。"
        " search_type=class(类)/function(函数)/semantic(语义)/reference(引用)/unit(单元)/all。"
        " kb_type=delphi(官方)/project(项目)/thirdparty(三方库)/document(文档)/example(示例代码)。"
        " search_in=all(默认)/delphi/project/thirdparty。"
        " ⚠️ Delphi 文件必须用 delphi_file 读写/搜索/正则匹配+替换，不要用内置 Read/Edit/Write/grep。"
    ),
    "delphi_file": (
        "Delphi 文件专用读写入口: read/write(edits)/replace/insert/delete/format/backup/encode/uses。"
        " 看到 .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx 时，即使只是读取也用本工具。"
        " Delphi 文件必须用 delphi_file，不要用内置 Read/Edit/Write/grep/apply_patch/PowerShell/Python。"
        " 内置工具和外部写入只能由 edit guard 事后兜底，不能作为主编辑路径。"
        " 🚫 同文件多处修改必须合并到一次 write(edits=[...])。"
    ),
    "manage_component": (
        "DFM 组件管理: create(生成DFM+代码)/add(添加组件)/remove/modify(属性)。自动同步PAS。"
    ),
    "check_environment": (
        "诊断编译环境: check(检查状态)/detect(重检测编译器)/install(安装pasfmt)。首次编译前调用。"
    ),
    "async_task": (
        "管理后台异步任务: start(启动)/status(进度)/result(结果)/list/cancel。知识库构建等耗时操作。"
    ),
    "package": (
        "编译安装 Delphi 组件包: install(编译安装)/list(查已装)。"
    ),
    "get_coding_rules": (
        "获取 Delphi 编码规范。写/改 Delphi 代码前必须先调用；具体 .pas/.dfm/.dproj 读取和修改仍路由到 delphi_file。"
    ),
    "code_hosting": (
        "Git 操作: status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/unstage/stash/tag/push/clone"
        " + 平台API(issue/PR/MR/release)。"
        " 禁止用 bash 执行 git。"
    ),
    "tool_help": (
        "获取任意工具的完整帮助文档（参数/示例/触发词）。用法不清时先调这个。"
    ),
    "experience": (
        "经验记忆: save(保存,自动去重)/search/get/list/update/merge/prune/delete/rebuild_embedding。"
        " AI 问题解决后保存经验，下次同类问题直接复用。"
    ),
    "daofy_update": (
        "检查和更新 Daofy 版本: check(快速检查)/update(git pull)/version(当前版本)。"
    ),
    "automate_delphi": (
        "Delphi 自动化测试: gui(命名管道GUI操作+截图)/console(stdin/stdout交互)/auto(自动检测)/prepare(注册全局搜索路径)。"
        " gui需链接DaofyAutomation(uses Vcl/Fmx.DaofyAutomation)；console无需改造；prepare一劳永逸。"
        " 支持 keep_alive 复用进程。cmd: formsum/dumpstate/capture/goto/click/type/rget/rinspect/rcall/rset/waitfor/msgscan/listwnd/exit/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception。callgraph 需额外 uses DaofyAutomation.CallGraph，支持 edge_limit/include_prefixes/category；callgraph_path 支持 source/target/max_depth/max_paths/include_prefixes；callgraph_diff 默认 compare_by=name，可选 addr/full，save_as/baseline_path 限制在 snapshots_dir。"
    ),
    "generate_copyright": (
        "生成软著文档: generate(源代码+说明书)/validate(检查配置)/audit(审计草稿)。浏览器PDF渲染+自动校验。"
    ),
    "delphi_rtti": (
        "Delphi RTTI 桥接: discover(扫描能力)/call(调用方法)/guide(使用指南)。"
        " 三步法: discover→call，无需UI操作。需链接DaofyAutomation。"
    ),
    "ocr": (
        "图像分析: recognize(文字识别)/detect(文本框)/diff(截图对比)/color(颜色分析)/match(图标匹配)/status(模型状态)。"
        " 纯ONNX+OpenCV+Pillow。diff需两张截图；match需模板图；color支持区域分析。"
    ),
}
