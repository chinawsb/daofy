<!-- @when: 自动化测试失败，需分析失败原因并修复后重试 -->
<!-- @chain: after=report-schema.md -->

# 失败修复循环

当 `report.first_failure` 不为 null 时执行此流程。

MCP resource URI: `delphi://automation/repair-loop`。

## 步骤

1. 停止依赖的自动化步骤。
2. 根据 `report.first_failure.signal` 分类失败类型。
3. 补充证据：
   - 目标/控件问题 → `formsum`/`dumpstate`
   - 非预期弹窗 → `msgscan`
   - 视觉证据 → `capture`
   - 属性/方法不匹配 → `rinspect`
4. 判定是脚本问题还是产品代码问题。
5. 脚本问题 → 更新缓存脚本并重跑。
6. 代码问题 → 切到编码模式，用 `delphi_file` 编辑 Delphi 文件，用 `delphi_project` 编译，重跑自动化。
7. 将稳定的事故恢复知识存入 `experience`。

## 脚本 vs 代码判定

| 判定 | 典型场景 |
|------|---------|
| **脚本问题** | 控件改名但行为正确；`assert_expr` 预期值错误；超时太短（证据显示应用仍在推进） |
| **代码问题** | 源码预期的行为未发生；必要控件未被创建；正确事件触发后 UI 属性值错误；有效输入导致弹出错误对话框 |

## 最终输出格式

```markdown
**自动化测试结果**
通过: N/M，耗时 Xs
执行模式: gui|console

**首个失败**
步骤 #、命令、目标、信号、实际值、期望值

**解决方案**
脚本修复或代码修复，附具体文件/步骤。

**验证**
编译结果和重跑结果。
```
