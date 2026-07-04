<!-- @when: 清理完成后，审查最终代码质量 -->
<!-- @chain: after=cleanup.md, before=ui-testing.md -->

## ⑦ 代码审核

**编译通过后按下方维度审查代码。**

| 维度 | 要点 |
|------|------|
| 一致性 | 命名/异常模式/排版统一性 |
| 完整性 | 分支覆盖/边界条件/输入验证/资源释放 |
| 资源泄露 | Create/Free 配对/句柄/接口释放 |
| Delphi 特有 | 引用计数/字符串/TComponent 所有权 |
| 代码质量 | 圈复杂度/魔法数字/重复代码 |
| 安全 | SQL 注入/硬编码凭据/缓冲区溢出 |

> 完整检查项见 `get_coding_rules(section="review")`。
