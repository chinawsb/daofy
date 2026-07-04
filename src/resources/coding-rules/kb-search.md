---
source: coding-rules
section: kb_search
---

## ② KB 搜索（编码前必做）

编码前先查 API 定义，避免凭记忆修改 Delphi 代码。

### 推荐顺序

| 优先级 | 查询 | 使用场景 |
|---|---|---|
| 1 | `delphi_kb(query="TStringList")` | 已知类名、函数名或常量名 |
| 2 | `delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")` | 搜索当前项目源码 |
| 3 | `delphi_kb(query="E2003", kb_type="document", search_type="semantic")` | 查询编译器错误或官方文档 |
| 4 | `delphi_file(action="read", search_type="function", function_name="...")` | 已定位到项目符号后读取源码 |

### 约束

- Delphi API、VCL/FMX/RTL 类型和第三方组件用法不确定时，先查 KB 再改代码。
- 项目源码搜索优先显式传 `project_path`，避免 CWD 变化导致搜索到错误项目。
- 搜索结果不足时，缩小关键词到类名、函数名、错误号或单元名。
