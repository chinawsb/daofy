<!-- @when: AI 生成或审核测试用例时，逐条对照质量清单 -->
<!-- @part-of: ui-testing -->

## 附录：黑盒测试编写核对表

AI 生成或审核测试用例时，逐条对照以下清单：

### 元数据核对

| # | 检查项 | 通过标准 | 检查方法 |
|---|--------|---------|---------|
| 1 | `test_level` 正确 | 纯黑盒（只用 UI 入口）→ `"black-box"`；用 RTTI 命令 → `"gray-box"` | 检查命令集符合黑盒边界 |
| 2 | `goal` 描述具体 | 写明"测试什么操作，验证什么结果" | 读 goal 字段，应有明确的双向描述 |
| 3 | `app_path` 和 `fixture_project` 存在 | 路径指向可执行文件和前置数据项目 | 检查路径存在性 |
| 4 | `source_files` 列出被测试的源码 | 列出本次测试涉及的主要 pas 文件 | 核对列出的文件是否覆盖了测试的路径 |
| 5 | `version` 递增 | 每次修改后 version+1 | 对比上一版 version |

### 结构核对

| # | 检查项 | 通过标准 | 检查方法 |
|---|--------|---------|---------|
| 6 | 步骤数合理 | 冒烟测试 5-15 步，功能测试 15-60 步 | 数 steps 条数 |
| 7 | 每步有 `expected` | 100% 步骤有人类可读的预期说明 | grep expected 覆盖率 |
| 8 | 关键步骤有 `assert_expr` | 验证状态/值的步骤必须断言 | 检查 rget/msgscan/capture 后的断言 |
| 9 | 每步有 `phase` | 使用 perceive/execute/verify/wait/rebuild | 检查 phase 字段完备性 |
| 10 | 操作后有时间间隔 | 异步命令后 `wait`/`waitfor` | 检查无连续异步命令无间隔 |

### 内容核对（基于 A-O 标准）

| # | 检查项 | 对应场景 | 通过标准 |
|---|--------|---------|---------|
| 11 | 坐标定位不裸用 `@x,y` | M1 | 优先使用控件名/`@文本`；不得只用 `@x,y` 而不配套校准 |
| 12 | 校准脚本存在 | M2 | 测试套件中必须有 00-calibration（验证 goto + rget + ClientWidth） |
| 13 | 固定 delay 改为条件等待 | N1 | 无 `{"cmd":"wait","ms":>1000}`，少数极短 delay 需带注释 |
| 14 | 控件重建后 `goto` 等待 | O1 | rescan/reload/切换操作后必须是 `goto TfrmMain` 而非直接 rget |
| 15 | 重建步骤标记 `phase: rebuild` | O2 | 重建后的等待/验证步骤标记 rebuild |
| 16 | 文件对话框有 `uia.xxx` 回退 | J0 | 涉及 Open/Save 回退的步骤使用 uia.goto/uia.click 兜底 |
| 17 | `msgscan` 断言内容具体 | G | `msgscan` 的 `assert_expr` 必须验证文本内容，不仅仅是 `actual != 'NOD'` |
| 18 | 每张截图有对应 OCR/diff 检测 | K7 | capture 后 Python 侧做了 recognize/detect/diff/color 分析 |
| 19 | 操作后验证 dirty 状态 | C/F/G | 数据变更操作后验证 `actSaveProject.Enabled` 或 `Project.Modified` |
| 20 | 运行在不同 DPI 下有变体 | M3/K4 | 跨 DPI 测试用 `coord_scale` 系数动态计算坐标 |
| 21 | 边界场景覆盖 | 全部 | 功能用例至少覆盖正常路径、失败/取消路径、关键输入边界和环境边界中的适用项；不适用项在 `note` 写明理由 |

### 质量门禁

| # | 检查项 | 一票否决 |
|---|--------|---------|
| 22 | 功能用例没有边界场景说明 | ❌ 否决（纯启动冒烟用例除外） |
| 23 | `wait ms` 超过 3000ms 无说明 | ❌ 否决 |
| 24 | 缺少 `phase` 字段的步骤占比 >20% | ❌ 否决 |
| 25 | 重建操作后无 `goto` 重建等待 | ❌ 否决 |
| 26 | `@x,y` 坐标在校准脚本未校准 | ❌ 否决 |
| 27 | 用例无 `assert_expr` 验证步骤 | ❌ 否决（纯记录型冒烟用例除外） |

**使用方式**：AI 生成测试用例 → 逐条过核对表 → 标记未通过项 → 修改后再提交。
