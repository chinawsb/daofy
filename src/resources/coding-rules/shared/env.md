<!-- @when: 首次运行/环境异常时，需确认编译器状态 -->
<!-- @chain: after=workflow.md, before=kb-search.md -->

## ① 环境检查
```python
check_environment(action="check")       # 确认编译器状态
get_coding_rules()                       # 获取工作流总览 + 章节索引（默认）
get_coding_rules(section="writing")      # 编码前：拉取编码规范
get_coding_rules(section="review")       # 编译后：拉取审核表
get_coding_rules(section="list")         # 列出所有可用章节名
```
