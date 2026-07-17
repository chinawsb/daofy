<!-- @when: 代码编译完成准备审查，按此表逐项检查 -->
<!-- @chain: before=testing/ui.md, after=compile.md -->

## 审核

### 一致性
| 检查项 | 说明 |
|--------|------|
| `__history` 备份完整性 | 确认备份存在且版本号 ≥ 1 |
| 命名规范 | 类型/字段/方法/参数符合规则，新旧统一 |
| 异常模式 | 同一模块异常处理方式一致；`try...finally` 用于资源释放，`try...except` 用于异常处理 |
| 排版 | 缩进/空格/begin-end 与项目一致 |
| OleVariant vs Variant | COM 用 `OleVariant`，普通逻辑用 `Variant` |
| 平台兼容 | `SizeOf`/`Length`/`NativeInt`/字节序 |
| 事件释放（多线程） | 置 nil 时检查竞争条件 |

### 完整性
| 检查项 | 说明 |
|--------|------|
| 所有分支 | if/else、case/else、try/except 全覆盖 |
| 边界条件 | 空数组/nil/空字符串/MaxInt |
| 输入验证 | 外部参数/文件/流做合法性检查 |
| 资源释放 | finally 确保异常路径也释放 |
| 并发安全 | 锁保护，死锁风险，线程退出清理 |
| 函数返回值 | 显式返回，禁止隐式未初始化 Result |
| const/out/var 参数 | 正确标注，`const` 禁止修改 |
| Assert 使用 | 前置/后置条件检查；注意 Release 下被剔除 |
| initialization/finalization | 泄漏/顺序依赖 |
| 日志输出 | 区分级别，含时间戳和上下文 |

### 资源泄露
| 检查项 | 说明 |
|--------|------|
| Create/Free 配对 | 每个 Create 有对应 Free/FreeAndNil |
| try/finally | 资源获取后立即 try，finally 释放 |
| 文件/句柄 | TFileStream/THandle/TMemoryStream 用完关闭 |
| 数据库连接 | TSQLConnection/TADOConnection 用完释放 |
| GDI/系统资源 | TFont/TBitmap/HPEN/HBRUSH |
| 接口引用 | 出作用域前确保释放，避免循环引用 |
| 大字符串/数组 | 不再使用时清空（`SetLength(s, 0)`） |
| TObjectList | `OwnsObjects` 设置正确 |

### Delphi 特有陷阱
| 检查项 | 说明 |
|--------|------|
| 接口引用计数 | 自动 `_AddRef`/`_Release`，避免手动干预 |
| 循环引用 | 接口互相引用导致泄漏，用 `[weak]` 破除 |
| TComponent 所有权 | Owner 接收 Free 通知，不要重复 Free |
| 字符串类型 | string=UnicodeString 自动管理；AnsiString 注意编码 |
| 字符串拼接 | 循环内用 `TStringBuilder` |
| Variant | 尽量用具体类型；COM 时注意引用计数 |
| published 区 | 流式加载的属性/事件保持 public/published |
| RTTI | `TRttiContext` 用完 Release |
| 平台兼容 | Win32/Win64 指针/句柄大小差异 |
| Record 值语义 | 方法内修改字段仅对副本生效 |
| 枚举/子范围 | case 覆盖全部（加 `else raise`） |
| Set 类型 | 上限 256 元素；空 Set 用 `[]` |
| Class Helper 冲突 | 命名唯一性 |
| 委托生命周期 | 匿名方法捕获变量防悬空指针 |

### 常见错误模式
| 检查项 | 说明 |
|--------|------|
| 空 except | `except` 内至少记日志，禁止空块吞异常 |
| 类型转换安全 | `is` 确认再 `as`；避免硬转 `Type(x)` |
| 事件释放 | 对象释放前 `OnClick := nil` |
| 匿名方法捕获 | 循环内用局部变量拷贝捕获值 |
| 线程访问 VCL | 必须 `TThread.Queue`/`Synchronize` |
| `with` 语句 | 避免使用 |
| 动态数组 | 明确 `array of T`/`TArray<T>`/open array 区别 |
| record 管理字段 | `string`/`TArray`/`IInterface` 赋值非引用 |

### 代码质量
| 检查项 | 说明 |
|--------|------|
| 方法规模 | ≤80 行，职责单一 |
| 圈复杂度 | 嵌套 ≤3 层；用卫语句/抽取方法简化 |
| 魔法数字 | 提取为具名常量 |
| 注释规范 | 关键逻辑/算法/TODO 需注释；清理误导注释 |
| 代码重复 | DRY 原则，抽取公共方法 |
| 测试命名 | `Test_[方法]_[条件]_[预期]` |

### 数据转换
| 检查项 | 说明 |
|--------|------|
| 转换隔离 | 专用层处理 JSON/XML/二进制转换 |
| 字段映射 | 优先声明式映射，避免手写逐字段 |
| 输入校验 | 反序列化时做结构和范围验证 |
| 编码一致 | 明确指定字符编码 |

### 安全
| 检查项 | 说明 |
|--------|------|
| SQL 注入 | 参数化查询，禁止字符串拼接 |
| 硬编码凭据 | 密码/密钥/API Key 用配置或环境变量 |
| i18n | 用户可见字符串用 `resourcestring` |
| 缓冲区溢出 | Move/CopyMemory 检查边界 |
| 输入消毒 | 外部数据做格式和范围校验 |

### 性能
| 检查项 | 说明 |
|--------|------|
| 循环内分配 | 禁止循环内创建对象/分配大内存 |
| 字符串操作 | 长拼接用 `TStringBuilder` |
| 不必要的类型转换 | 避免循环内重复 `as`/`Type()` |
| RTTI 开销 | 高频路径缓存 `TRttiContext` |

### 审核结果确认
| 分类 | 处理方式 |
|------|---------|
| 🔴 影响逻辑/架构 | 标注「需用户确认」，等确认再改 |
| 🟡 设计歧义 | 列出选项让用户选择 |
| 🟢 明显编码错误 | 先修后报，注明已修复 |
