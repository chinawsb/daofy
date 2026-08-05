# 格式化示例

## 核心规则

- 缩进 2 空格，行宽 ≤120
- `begin` 独占一行；运算符/逗号后加空格，括号内侧不加
- `uses` 分组 + 组尾注释 + 组内字母序

## 正确示例

```pascal
unit CustomerUnit;

interface

uses
  System.SysUtils,        // 系统单元
  System.Classes,
  Vcl.Dialogs,            // VCL 单元
  Vcl.Forms;

type
  TCustomer = class
  private
    FName: string;
  public
    constructor Create(AName: string);
  end;

implementation

constructor TCustomer.Create(AName: string);
begin
  FName := AName;
end;

end.
```

## 常见错误与修正

```pascal
// ❌ begin 不独占一行；括号内侧加空格；运算符两侧无空格
procedure DoSomething( AValue :Integer);
begin
  if( AValue>0 )then
    ShowMessage(IntToStr( AValue ));
end;

// ✅ 修正后
procedure DoSomething(AValue: Integer);
begin
  if AValue > 0 then
    ShowMessage(IntToStr(AValue));
end;
```

## 格式化工具

```python
# 用 delphi_file 格式化（自动备份到 __history）
delphi_file(action="format", file_path="Unit1.pas")

# 只检查不修改
delphi_file(action="format", file_path="Unit1.pas", dry_run=True)
```

## 注意事项

- 格式化后文件标记为**脏**，再次 write 前必须先 read 或提供 old_content
- `uses` 用 `delphi_file(action="uses", ...)` 增删，不要手动算行号
- 写入时保持原始编码（`delphi_file` 自动检测 BOM/GBK）
