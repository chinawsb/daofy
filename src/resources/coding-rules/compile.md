<!-- @when: 完成编码，准备编译验证 -->
<!-- @chain: before=review-guide.md, after=format.md -->

## ⑤ 编译

```python
project(action="compile", project_path="Project.dproj")
project(action="compile", project_path="Unit1.pas")          # 语法检查
project(action="compile", project_path="Project.dproj", build_configuration="Release", target_platform="win64")
```

### 附加编译参数（extra_args）

`extra_args` 是完整参数数组，按实际编译后端解释，并在内建参数之后追加：

```python
# .dproj / 有同名 .dproj 的 .dpr：MSBuild 参数，请求生成 TDS/RSM
project(action="compile", project_path="Project.dproj",
        extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])

# 无同名 .dproj 的 .dpr：直接 DCC 参数
project(action="compile", project_path="Project.dpr", extra_args=["-VT", "-VR"])
```

每个数组元素是一个完整参数，不要自行添加外层引号。如果编译器生成 `.tds`/`.rsm`，它们会列入 `output_files`。

### 运行验证（run_verify）

```python
project(action="compile", project_path="Project.dproj", run_verify=True)
```

编译成功后自动启动 exe 检测运行时崩溃：

**① 注入 StackTrace** — 临时改 `.dproj`/`.dpr`，验证完自动恢复
**② 重新编译**（注入后）
**③ 运行 exe** — Popen + timeout(5s)，超时 kill
**④ 检查 exception.log** — 有则嵌入结果，无则 passed
**⑤ 恢复** — `.dproj`/`.dpr` 从 `.verify_bak` 还原

> StackTrace.pas 位于 tools/stacktrace/，run_verify 使用该内置诊断单元捕获调用栈；局部变量快照默认关闭。

### 编译失败处理流程

```
失败
 ├─ ① check_environment(action="check")
 ├─ ② 分类: Fatal → 先修 / Error → 主目标 / Warning → 暂缓
 ├─ ③ 首次失败 → 查最近修改；怀疑缓存→清 .dcu 全量编译
 ├─ ④ 路径/配置检查：搜索路径 / DCCReference / 条件编译
 ├─ ⑤ 单文件隔离：compile_file；海量错误从首个 Error 开始
 ├─ ⑥ 查经验库：experience(search, query="DCC {错误号}")
 ├─ ⑦ 假设驱动循环：2~3 假设 → 并行验证
 ├─ ⑧ 二分法隔离 / 回归定位
 ├─ ⑨ 维护调试日志
 └─ ⑩ 3 次失败仍不解 → 评估人工介入
```

> **事件**：PreBuildEvent/PostBuildEvent 自动执行。编译失败可临时注释 `<Event>` 行排除干扰。
> **安全**：`shell=True` 执行事件前记 `logger.warning`；长轮询 ≤30s。
