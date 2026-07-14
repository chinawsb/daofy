# v2026.07.14 Release Notes

自上一版本 v2026.07.13 以来的变更。

---

## 新增功能

### 客户端规则自动安装
- **`client_rules_installer.py`**: MCP 握手后自动将 Daofy 规则安装到所连客户端的规则目录（`.cursorrules`、`.claude/rules/` 等）
- 无需手动复制规则文件，Server 启动时静默完成
- 失败不影响 Server 正常运行

### CodeBuddy IDE 支持
- `install_mcp.py` 新增 CodeBuddy（腾讯云 AI 代码助手）自动安装
- 支持 stdio/sse/http 三种 MCP 传输类型

### 布局审计增强
- **LAYOUT-008**: 检测可调整大小的父容器使用绝对坐标但最小尺寸不足的问题
- 生成规范新增第 8 条：优先用 `Align` 和嵌套容器排布，保留绝对坐标时必须设置 `Constraints.MinWidth/MinHeight`

### 依赖更新
- `requirements.txt` 新增 `pyyaml>=6.0`

## 变更

### SKILL.md 重构为按需加载用法手册
- 路由规则由 Daofy Rule 与 `initialize.instructions` 常驻保证
- SKILL.md 只补充「客户端包装」与「工作流」，不再重复路由规则
- 避免与 Rule 重复注入，减少 token 消耗

### Server Instructions 精简
- `server.py` 中 `MCP_SERVER_INSTRUCTIONS` 移除重复路由规则
- 引导 Agent 通过 Daofy Rule 获取强制约束

### manage_component 原子更新
- `add` 操作改为内存中生成完整 DFM + PAS 更新
- 若 DFM 写入失败，PAS 保持不变
- 若 PAS 写入失败，自动恢复原 DFM，避免两份文件不同步

### 编码规则补充
- `.groupproj` 文件扩展名加入 Delphi 文件保护列表
- 禁止直接写入 `.groupproj` 文件

---

**版本标签**: `v2026.07.14`
**完整日志**: [CHANGELOG.md](CHANGELOG.md)
