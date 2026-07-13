# v2026.07.13 Release Notes

自上一版本 v2026.07.07 以来的变更。

---

## 新增功能

### DFM 布局完整性检测模块 (`src/detection/`)
- **DFM 布局检测**: 支持 OpenCV/YOLO/合成数据生成
- **`layout_parser.py`**: DFM 文件解析器
- **`opencv_detector.py`**: OpenCV 检测器
- **`yolo_onnx.py`**: YOLO ONNX 推理
- **`synthetic_data_generator.py`**: 合成数据生成
- **`train_yolo.py`**: YOLO 训练脚本

### DaofyAutomation 三层架构更新
- Fmx/Vcl/Base 三层新增命令和改进
- 增强 GUI 自动化能力

### 新增测试文件
- `test_detection_module.py` (688 行)
- `test_file_tool_grep.py` (716 行)
- `test_automation_textbounds.py` (248 行)
- `test_project_compile_extra_args.py` (114 行)

## Bug 修复

- **`delphi_file` grep action 回退**: `file_path` 参数现在可选，未传时自动使用 `project_path` 或工作区根目录作为搜索范围
- **`add_source` 绝对路径归一化**: 接收绝对路径时自动 `os.path.relpath` 转为相对于 `.dproj` 目录的路径，避免项目不可移植
- **资源泄露修复**: `experience_service` 多线程连接泄露（单连接+锁模式）；`automation_service` 添加后台守护线程定时清理过期进程池
- **`tool_help` action_params 补齐**: `delphi_file` 6 个缺失的 action_params；11 个工具新增 action_params 文档；`delphi_rtti` 补充 pipe 参数
- **目录约束**: `coding-rules.md` 新增目录约束章节（标准结构、命名规范、清理规则）
- **管道故障诊断**: `automation/scenarios/base.md` 新增管道建立失败诊断流程

## 变更

- **`.gitignore` 更新**: 整个 `config/` 目录加入忽略，排除 ML 模型产物
- **文档同步**: `project.md`、`automation/`、`coding-rules/` 更新

---

**版本标签**: `v2026.07.13`
**完整日志**: [CHANGELOG.md](CHANGELOG.md)
