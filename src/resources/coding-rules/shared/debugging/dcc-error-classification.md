<!-- @when: DCC 编译报错，需定位错误原因和修复方案 -->
<!-- @chain: before=binary-search-isolation.md, after=hypothesis-driven-debugging.md -->

### 8.8 DCC 编译错误分类与解码

#### 文档知识库搜索（首选）
Delphi CHM 文档包含 1278 个 DCC 错误/警告 HTML 文件（875 EXXXX + 20 FXXXX + W/H 系列）。
```python
# 构建一次后即可搜索
delphi_kb(action="build", kb_type="document", async_mode=true)

# 查具体错误号
delphi_kb(query="E2003", kb_type="document", search_type="semantic")
delphi_kb(query="F2613 unit not found", kb_type="document", search_type="semantic")
```

#### 错误级别速查
| 级别 | 前缀 | 策略 |
|------|------|------|
| Fatal | Fxxxx | 先修复路径/配置 |
| Error | Exxxx | 读错误行 → 查文档 KB → 修复 |
| Warning | Wxxxx | 评估影响；已知可忽略 |
| Hint | Hxxxx | 整理时处理，调试跳过 |

#### 常见 DCC 错误速查表
| 错误号 | 常见原因 | 解决方向 |
|--------|---------|---------|
| E2003 | 缺 uses / 拼写错误 | 检查 uses + 大小写 |
| E2010 | 类型不匹配 | 检查赋值/参数类型 |
| E2029 | 语法结构错误 | 检查括号/分号/begin..end |
| E2037 | 非对象类型用 '.' | 检查变量类型声明 |
| E2066 | 前一行漏分号 | 回溯前一行末尾 |
| E2251 | 重载匹配歧义 | 显式类型转换 |
| E2506 | DCU 缓存过期 | 全量编译或删 .dcu |
| F2613 | 搜索路径不含目标单元 | 检查 DCC_UnitSearchPath |

#### 处理流程
```
失败
 ├─ ① 分类级别: Fatal先→Error主→Warning暂缓
 ├─ ② 单文件/全量: 增量出错先clean再全量；少量→compile_file；大量→首个Error
 ├─ ③ Error定位:
 │   1. delphi_kb(query="{错误号}", kb_type="document")
 │   2. delphi_kb(query="{关键词}", kb_type="document")
 │   3. 对照速查表 + 读源码上下文
 │   4. delphi_kb(search_type="function") 查API
 └─ ④ 疑难: 二分法隔离 → 查经验库 → 3次失败介入
```

#### 增量缓存问题
- `.dcu`/`.map`/`.dres` 缓存损坏导致幽灵错误
- 症状：修复仍报相同错，或指向已删代码
- 解决：清缓存全量编译（Windows 上先关 IDE）
