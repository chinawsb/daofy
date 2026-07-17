<!-- @title: 编码规则导航 -->
<!-- @purpose: 快速定位编码各阶段所需规则文件。首次阅读或走完一次完整流程后，按需调用 get_coding_rules(section=...) 获取详情。 -->

## 编码规则导航
> 最后更新: 2026-07-17 | 版本: 1.14.0

按流程选择入口：

## 基础编码
```
计划 → get_coding_rules(section="planning")    # P0 前置计划与审查（新功能必做）
流程 → get_coding_rules(section="workflow")     # 流程总览
查API → get_coding_rules(section="kb_search")   # 搜索定义
编码 → get_coding_rules(section="writing")      # 代码规范
改文件 → get_coding_rules(section="delphi_file_write_rule")  # 写入规则/脏标记
编译 → get_coding_rules(section="compile")      # 编译+run_verify
审核 → get_coding_rules(section="review")       # 审核检查表
清理 → get_coding_rules(section="cleanup")      # 最终清理+经验保存
```

## 异常诊断
```
get_coding_rules(section="human_collab")  # 六步法总纲
 ├─ DCC错误 → debugging/dcc-error-classification.md
 ├─ 崩溃 → debugging/runtime-crash-classification.md
 ├─ 3次失败 → debugging/escalation-checkpoints.md
 └─ 人工介入 → debugging/escalation-handover.md
```

## 自动化测试
```
方法论(AI框架) → get_coding_rules(section="automation")
布局审计 → get_coding_rules(section="ui_layout")  # DFM 静态布局规范 + delphi_project(action="layout")
工具参考 → read_mcp_resource("delphi://automation/script-schema")
```

## 其他
```
经验保存 → get_coding_rules(section="experience")
知识库 → get_coding_rules(section="kb_build")
Agent规范 → get_coding_rules(section="agent_rules")
```

`delphi://coding-rules` 是导航入口；完整规则正文通过 `get_coding_rules(section=...)` 按需读取。
