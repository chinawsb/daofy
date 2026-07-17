<!-- @when: 修复 bug 后，需要总结规则沉淀 -->
<!-- @chain: after=experience.md -->

## ⑫ 规则维护

修复 bug 后总结为规则加入项目规则文件。添加前检查是否已有相同规则。修改后更新版本号。

### 新增规则模板
```markdown
#### [类别] [标题]
- **问题**：此规则要防范什么
- **规则**：具体的约束或做法
- **正例**：```delphi {符合规则的代码} ```
- **反例**：```delphi {违反规则的代码} ```
```
示例：
```markdown
#### 常见错误模式 空 except 块
- **问题**：空 `except...end` 吞噬所有异常
- **规则**：`except` 内至少记录日志并重新抛出，或有意义地处理
- **正例**：`except on E: Exception do Logger.Error(E); raise; end;`
- **反例**：`except end;`
```
