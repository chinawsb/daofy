# 文档注释示例

## 单元头注释

```pascal
{*************************************************************************}
{ 单元: CustomerUnit.pas                                                    }
{ 用途: 客户实体与仓储实现，业务层统一入口                                   }
{ 作者: TeamName                                                           }
{ 日期: 2026-07-17                                                          }
{ 版本: 1.0.0                                                               }
{*************************************************************************}
```

## 类与方法注释（XML Doc 风格）

```pascal
type
  /// <summary>客户实体，封装客户基本信息。</summary>
  TCustomer = class
  private
    FName: string;
    FAge: Integer;
  public
    /// <summary>创建客户实例。</summary>
    /// <param name="AName">客户姓名，不可为空</param>
    /// <param name="AAge">客户年龄，0-150</param>
    /// <returns>初始化完成的客户实例</returns>
    constructor Create(AName: string; AAge: Integer);

    /// <summary>计算客户显示名。</summary>
    /// <returns>姓名（年龄）格式的显示串</returns>
    function GetDisplayName: string;
  end;
```

## 复杂方法注释

```pascal
/// <summary>批量导入客户数据。</summary>
/// <param name="AFileNames">待导入的文件路径列表，至少一项</param>
/// <param name="AOverwrite">已存在时是否覆盖</param>
/// <returns>成功导入的客户数</returns>
/// <exception cref="EFileNotFoundException">任一文件不存在时抛出</exception>
function ImportCustomers(AFileNames: TArray<string>; AOverwrite: Boolean): Integer;
```

## 注释规范

| 场景 | 要求 |
|------|------|
| 公开 API（published/public 方法） | 必须写 `<summary>`，参数复杂时补 `<param>` |
| 抛出异常 | 用 `<exception>` 标注 |
| 私有辅助方法 | 单行注释说明用途即可 |
| 魔法数字/复杂逻辑 | 就地注释解释为什么，而不是重复代码 |
| 改动历史 | 重要逻辑变更在方法注释追加 `@since vX.Y` 说明 |

## 反模式

```pascal
// ❌ 注释重复代码（无信息量）
i := i + 1;  // i 加 1

// ✅ 注释解释意图
i := i + 1;  // 跳过已处理的记录，避免重复消费
```
