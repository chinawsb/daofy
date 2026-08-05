# 命名规范示例

## 基础前缀

| 类别 | 约定 | ✅ 正确 | ❌ 错误 |
|------|------|---------|---------|
| 类/接口/异常 | T/I/E/P 前缀 | `TMyClass`, `IMyInterface` | `MyClass`, `MyInterface` |
| 字段 | F 前缀 | `FName: string;` | `Name: string;` |
| 属性/方法 | 大驼峰 | `property Name` / `procedure CalculateTotal` | `property name` / `procedure calculateTotal` |
| 事件 | On→Form 后缀 | `Form1Create` | `CreateForm1` |
| 参数 | A 前缀 | `procedure SetName(AName: string);` | `procedure SetName(Name: string);` |
| 枚举 | 类型前缀缩写 | `taLeft, taRight, taCenter` | `Left, Right, Center` |
| 常量 | 全大写 | `MAX_BUFFER_SIZE` | `MaxBufferSize` / `max_buffer_size` |

## 完整示例

```pascal
type
  // 类：T 前缀
  TCustomer = class
  private
    FName: string;      // 字段：F 前缀
    FAge: Integer;
  public
    constructor Create(AName: string; AAge: Integer);  // 参数：A 前缀
    function GetDisplayName: string;                   // 方法：大驼峰
    property Name: string read FName write FName;      // 属性：大驼峰
    property Age: Integer read FAge write FAge;
  end;

  // 接口：I 前缀
  IRepository = interface
    function FindById(AId: Integer): TCustomer;
  end;

  // 异常：E 前缀
  ECustomerNotFound = class(Exception);

  // 枚举：类型前缀缩写
  TAlignment = (taLeft, taCenter, taRight);

const
  MAX_RETRY_COUNT = 3;   // 常量：全大写
```

## 命名检查清单

- [ ] 新类是否有 T/I/E/P 前缀
- [ ] 私有字段是否 F 前缀
- [ ] 方法参数是否 A 前缀
- [ ] 属性/方法是否为大驼峰
- [ ] 常量是否全大写（下划线分隔）
- [ ] 事件处理器是否 Form/Control 后缀
