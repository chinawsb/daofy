<!-- @when: 规划自动化测试步骤，需要分层降级策略、动作序列规范或失败处理模式时 -->

# 规划方法论

MCP resource URI: `delphi://automation/planning-methodology`。

## 1. 分层降级策略

### 感知优先级
```
① RTTI（rget/rinspect/dumpstate）→ 微秒级
② 结构化扫描（msgscan/listwnd/dlgscan）→ 毫秒级
③ OCR 视觉识别（capture/ocr）→ 百毫秒级
```

### 执行优先级
```
黑盒首选：真实 UI 操作（goto→click/type/key）
灰盒/白盒：RTTI 调用（rcall/rset），仅用于夹具/诊断
兼容模式：坐标操作（move+click），DPI 敏感
```

### 验证优先级
```
① RTTI 属性验证（rget）——最精确
② 结构化等待（waitfor/msgscan）
③ 视觉验证（capture+OCR）——兜底
```

## 2. 动作序列规划

每步明确标注阶段（perceive/execute/verify）、工具、目标、期望结果、失败处理：

```json
{
  "phase": "perceive | execute | verify",
  "cmd": "rget | click | waitfor",
  "target": "控件名.属性",
  "expected": "人工可读预期",
  "assert_expr": "actual == '期望值'",
  "note": "源码推导的上下文",
  "timeout": 10000
}
```

## 3. 失败处理模式

| 信号 | 可能原因 | 恢复动作 |
|------|---------|---------|
| waitfor 超时 | 控件未出现/操作未生效 | capture → 分析 → 重试或上报 |
| click 返回 error | 控件被遮挡/Disabled | dumpstate 检查 Enabled/Visible |
| 意外弹窗 | 业务逻辑异常 | msgscan → msgclick → capture 新状态 |
| OCR 结果不符 | OCR 精度不足/值实际不符 | 先用 rget 确认精确值 |
| RTTI 调用异常 | 对象不存在/方法签名变化 | 降级到 goto+click 操作 |