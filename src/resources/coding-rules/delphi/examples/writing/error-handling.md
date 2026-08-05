# 错误处理示例

## 核心原则

- `try...finally` 用于**资源释放**（文件/句柄/锁/内存）
- `try...except` 用于**异常处理**（转换/记录/重抛）
- `except` 内至少记录日志，**禁止空块吞异常**
- 用具体异常类型捕获，避免裸 `except`

## 资源释放：try...finally

```pascal
// ✅ 资源获取后立即 try，finally 中释放
var
  LFile: TFileStream;
begin
  LFile := TFileStream.Create(AFileName, fmOpenRead);
  try
    // 读取逻辑（异常也会走到 finally）
    ProcessStream(LFile);
  finally
    LFile.Free;   // 无论正常/异常路径都释放
  end;
end;
```

## 异常处理：try...except

```pascal
// ✅ 捕获具体异常类型 + 记录日志
try
  SaveToDatabase(ACustomer);
except
  on E: EDatabaseError do
  begin
    Logger.Error('保存客户失败: ' + E.Message);
    raise;  // 需要上层处理时重抛
  end;
  on E: Exception do
    Logger.Error('未知错误: ' + E.Message);
end;
```

## 反模式

```pascal
// ❌ 空 except 吞异常 —— 问题被静默掩盖，极难排查
try
  DoSomething;
except
end;

// ✅ 至少记录日志（尽量用具体异常类型，参考上方 try...except 示例）
try
  DoSomething;
except
  on E: EIOException do
    Logger.Error('DoSomething 失败: ' + E.Message);
end;

// ❌ 裸 except 捕获一切，掩盖编程错误（范围过宽）
try
  DoSomething;
except
  on E: Exception do
    Logger.Error('出错: ' + E.Message);
end;
```

## 防御式检查

```pascal
// ✅ 前置条件校验，快速失败
if AFileName = '' then
  raise EArgumentException.Create('AFileName 不能为空');

// ✅ 枚举/子范围 case 全覆盖（默认分支 raise）
case AAlign of
  taLeft:   DoLeft;
  taRight:  DoRight;
  taCenter: DoCenter;
else
  raise EArgumentException.CreateFmt('未知对齐方式: %d', [Ord(AAlign)]);
end;
```

## 检查清单

- [ ] 资源获取后是否立即 `try`，`finally` 是否释放
- [ ] `except` 是否为空块（禁止）
- [ ] 是否捕获了具体异常类型而非裸 `except`
- [ ] 错误信息是否包含足够的上下文（变量值/调用参数）
- [ ] 是否需要 `raise` 重抛给上层处理
