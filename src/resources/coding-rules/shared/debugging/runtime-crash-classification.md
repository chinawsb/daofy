<!-- @when: 程序运行时崩溃，需分类排查根因 -->
<!-- @chain: before=escalation-checkpoints.md, after=post-mortem.md -->

### 8.13 运行时崩溃分类排查

Delphi 运行时崩溃有 4 种不同根因模式：

#### A：AV — 接口引用计数问题
**特征**：调用接口方法时 AV，调用对象方法正常。
**排查**：
① 确认是否接口调用（调用栈是否经过 Interface Dispatch）
② 检查接口来源：是否从已 Free 的对象获取？跨线程传递？
③ 修复：确保对象生命周期 ≥ 接口使用周期；或弱引用

#### B：AV — TComponent 所有权违规
**特征**：Form 关闭后或析构链中 AV。
**排查**：
① 检查 AV 地址对应的源码行
② 确认组件是否已 Free
③ 检查事件注册/注销是否配对（Timer/Socket 回调访问已释放对象）
④ 修复：OnDestroy 注销回调；检查 Assigned(Self)/csDestroying

#### C：DFM 流式错误
**特征**：打开 Form 报错或运行期 DFM 流化异常。
**排查**：
```
Class TMyFrame not found      → 缺 uses 或未 RegisterClass
Property Caption does not exist → DFM 属性名拼写或类型不匹配
Error reading X: ...          → 二进制数据损坏或版本不兼容
```
① 检查 uses 子句、RegisterClass、DFM 类名与 PAS 一致
② published 区声明、属性名/类型匹配
③ DFM 损坏 → 另存为文本 DFM 或从 __history 恢复

#### D：包/动态库加载错误
**特征**：启动或加载 BPL/DLL 时报错。
```
"Cannot load package XXX"       → BPL 不在路径或版本不匹配
"entry point YYY not found"    → 导出函数签名不匹配
"Runtime error 216/217"        → 初始化异常
```
排查：check_environment → delphi_project(info) → 检查 PATH/RuntimePackages

#### 崩溃分类决策树
```
运行时崩溃
 ├─ 异常类型明确 → 跳对应 A/B/C/D
 ├─ 调用栈经过 Interface Dispatch → A
 ├─ 在 TComponent.Notification/Form 析构 → B
 ├─ 含 "Class not found"/"Property" → C
 ├─ 含 "Cannot load package"/"entry point"/"216"/"217" → D
 └─ 无法分类 → StackTrace.pas 获取完整调用栈后重分类
```
