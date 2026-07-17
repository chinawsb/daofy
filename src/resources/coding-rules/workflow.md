<!-- @when: 首次编码/任务开始时，了解整体流程 -->
<!-- @chain: after=planning.md, before=writing.md -->

## 工作流总览

```
① → ② → ③/④ → ⑤ → ⑥ → ⑦      可选: ⑧/⑨
         ↑      │    │    │
         └── 失败 ──┴────┴────┘ ← 回退到 ③

 ① 环境检查 → check_environment / get_coding_rules
 ② 查KB     → delphi_kb / delphi_file(read)
 ③ 写代码   → delphi_file(action="write")
 ④ 格式化   → delphi_file(action="format")           # ③④ 循环：改完即格式化
 ⑤ 编译验证 → delphi_project(action="compile")       # 失败 → 回 ③
 ⑥ 代码审核 → get_coding_rules(section="review")      # 不通过 → 回 ③
 ⑦ 清理     → 删未用变量/导入/死代码                  # 先审再清
 ⑧ UI测试   → automate_delphi                         # 失败 → 回 ③
 ⑨ 控制台   → subprocess                               # 失败 → 回 ③
 §⑩ 前置自检 → get_coding_rules(section="human_collab")  # 任意步骤可触发
 §⑪ 经验沉淀 → experience(action="save")
```
