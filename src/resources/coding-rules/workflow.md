<!-- @when: 首次编码/任务开始时，了解整体流程 -->
<!-- @chain: after=planning.md, before=writing.md -->

## 工作流总览

```
P0 → ① → ② → ③/④ → ⑤ → ⑥ → ⑦ → ⑧ → ⑨ → ⑩ → ⑪
                     ↑         │    │    │
                     └── 失败 ──┴────┴────┘ ← 回退到 ③

 P0 计划审查 → get_coding_rules(section="planning")   # 前置计划与审查（新功能必做）
 ① 环境检查 → check_environment / get_coding_rules
 ② 查KB     → delphi_kb / delphi_file(read)
 ③ 写代码   → delphi_file(action="write")
 ④ 格式化   → delphi_file(action="format")           # ③④ 循环：改完即格式化
 ⑤ 编译验证 → delphi_project(action="compile")       # 失败 → 回 ③
 ⑥ 清理     → 删未用变量/导入/死代码                  # 先清再审
 ⑦ 代码审核 → get_coding_rules(section="review")      # 不通过 → 回 ③
 ⑧ UI测试   → automate_delphi                         # 失败 → 回 ③
 ⑨ 控制台   → subprocess                               # 失败 → 回 ③
 ⑩ 文档同步 → 更新 README/CHANGELOG/API 文档
 ⑪ 经验沉淀 → experience(action="save")
 🔧 卡点介入 → get_coding_rules(section="human_collab")  # 任意步骤可触发
```
