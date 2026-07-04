<!-- @when: 修改代码后，提交前需格式化 -->
<!-- @chain: before=compile.md, after=writing.md -->

## ④ 格式化

```python
delphi_file(action="format", file_path="src/Unit1.pas")
```
自动处理泛型嵌套 `>>` 格式。
