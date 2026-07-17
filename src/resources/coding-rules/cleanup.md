<!-- @when: 审核完成后，清理代码中遗留的冗余 -->
<!-- @chain: after=review-guide.md, before=ui-testing.md -->

## ⑦ 清理 & 验证

- **备份验证**：`delphi_file(action="write")` 默认自动备份到 `__history`，可用 `delphi_file(action="backup", backup_action="list", file_path=...)` 确认
- **整理**：删未用变量/导入/函数/类（直接删，无需确认）
- **遗留死代码**：标注废弃注释，留待人工清理
- **编码**：保持原始编码；修改后 `delphi_file(action="format", ...)`
