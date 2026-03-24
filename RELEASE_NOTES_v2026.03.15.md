# v2026.03.15 - 编码规则查询接口

## 新增功能

### 编码规则查询接口
- **工具名称**: `get_coding_rules`
- **功能**: 获取 Delphi 源码编码规则，供智能体用于代码审核和生成
- **特性**:
  - 支持默认编码规则（config/CODING_RULES.mdc）
  - 支持项目自定义规则（项目目录下的 CODING_RULES.mdc）
  - 用户自定义规则优先于默认规则
  - 返回规则来源、文件路径等详细信息

## 技术改进

- 新增 `src/tools/coding_rules.py` 模块
- 更新 `src/server.py` 集成新工具
- 添加 `config/CODING_RULES.mdc` 默认编码规则文件
- 完整的文档和使用说明

## 文档

- `docs/CODING_RULES_USAGE.md` - 编码规则接口使用说明
- `docs/INTEGRATION_TEST_REPORT.md` - 集成测试报告
- `README.md` - 更新项目文档，添加编码规范功能说明

## 测试

- 所有现有测试通过（4/4）
- 新功能集成测试通过（4/4）
- 无功能冲突或兼容性问题

## 使用示例

```python
# 获取默认编码规则
result = await get_coding_rules()

# 获取项目自定义编码规则
result = await get_coding_rules(project_path="项目路径")
```

## 影响

- ✅ 不影响现有功能
- ✅ 完全向后兼容
- ✅ 提升智能体代码质量

---

## Git 操作

### 已完成
- ✅ 创建提交: `dce6d7f`, `7b609c5`, `0e6fa0f`
- ✅ 推送到远程: 所有提交已推送到 `origin/main`
- ✅ 创建并推送 tag: `v2026.03.15` 已推送到远程仓库

### Release 创建

**方式一：使用 GitHub CLI（如果可用）**

```bash
gh release create v2026.03.15 --title "v2026.03.15 - 编码规则查询接口" --notes-file RELEASE_NOTES_v2026.03.15.md
```

**方式二：在 GitHub 网页上手动创建（推荐）**

1. 访问: https://github.com/chinawsb/delphi-complier-mcp-server/releases/new
2. 选择 tag: `v2026.03.15`
3. 标题: `v2026.03.15 - 编码规则查询接口`
4. 复制本文件内容到描述中
5. 点击 "Publish release"

---

**完整更新日志**: 查看 [CHANGELOG.md](CHANGELOG.md)
