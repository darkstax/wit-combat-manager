# WIT 桌面端到 Android 技术交接

## 1. 文档状态

- 交接日期：2026-07-22
- 桌面端基线：`wit-combat-manager`，`schema_version = 3`
- Android 端基线：`wit-combat-manager-android`
- 支持规则：v0.3、v1.2
- 桌面端回归基线：`pytest -q`，131 项通过

本文用于指导 Android 端对齐桌面端现行行为。完整字段、枚举、状态、元素、报告 DTO 与 JSON 格式见桌面仓库 `android/DATA_REFERENCE.md`。本文不重复规则正文，而聚焦模块映射、现存差距、迁移顺序和验收条件。

`工作资料/`、PDF 和 XLSX 原文属于受限资料。实现时可以对照，但不得把全文复制进源码、日志、测试输出或公开文档。

## 2. 权威来源与边界

| 能力 | 桌面端权威来源 | Android 对应位置 |
|---|---|---|
| 数据模型与规则版本 | `models.py` | `domain/Unit.kt`、`domain/CombatState.kt` |
| v1.2 战斗规则 | `combat.py` | `domain/CombatEngine.kt` |
| v0.3 战斗规则 | `combat_v03.py` | 尚未独立实现 |
| 结构化计算结果 | `combat_report.py` | 尚未实现 |
| 状态定义 | `models.py` | `domain/StatusDefinitions.kt` |
| 名单与战斗持久化 | `persistence.py`、`app_paths.py` | `data/UnitRepository.kt` |
| 角色卡与文本导入 | `character_card.py` | `ui/QuickImportDialog.kt`，XLSX 尚未接通 |
| 规则目录 | `rule_catalog.py` | 尚未实现 |
| 交互事务 | `ui/combat_panel.py` | `ui/MainViewModel.kt`、`ui/MainScreen.kt` |

桌面端当前公开 `apply_*` API 会直接修改 `Unit` 并返回中文消息；私有 `_calc_*` 才返回 Report。Android 推荐采用更清晰的 `calculate -> Report -> commit`，但这属于目标架构，不应误写成桌面端已有的公开函数签名。

## 3. 必须先修复的 P0 差距

### 3.1 禁止引擎代投骰

桌面端的骰子结果由玩家或 GM 填写。`DiceGroup` 和 `RollInput` 支持逐骰值或总值覆盖；没有输入时必须给出用户可见错误。

Android 当前 `traditionalInitiative()` 内部使用 `Random` 计算 `dN + speed`，与规则契约冲突。

验收条件：

- v1.2 传统先攻逐单位接收非负的反应机动检定总值。
- 缺少任一必需值时阻止开始战斗。
- 同检定且同速度时提示相关单位重新填写，不得后台随机重投。
- v0.3 仅在速度和反应机动都相同时收集 d100 对抗值。
- 领域测试中不允许依赖随机数。

### 3.2 对齐伤害、治疗、状态和元素报告

Android 当前伤害入口仅覆盖数值、类型和 `isAttack`，缺少攻击检定阈值、最终伤害、辅助骰伤害、伤害减半和结构化报告。

实现必须覆盖：

- 护盾只阻挡攻击，不阻挡环境或持续伤害。
- 真实攻击仍需遵守攻击相关入口语义。
- 屏障吸收、临时 HP、伤残、濒死和最大 HP 损伤按报告字段结算。
- 禁疗、濒死治疗限制、亲和消耗及治疗结束事件可解释、可测试。
- 状态升级链、X 计数、标记子触发、抵抗与豁免不可只返回模糊字符串。
- 元素爆发溢出与待填骰进入 `pending_rolls`，随后由显式 resolve API 补结；程序不得自行投骰。

建议公开 `DamageReport`、`HealingReport`、`StatusReport`、`ElementalReport`，由 ViewModel 统一格式化日志。

### 3.3 修正回合生命周期

Android 当前强制下一轮会批量处理所有单位，`nextActor()` 也没有完整清理失效 ID。目标行为应与桌面端 `advance_turn()`、`next_actor()` 一致：

- 当前行动者结束事件先结算，下一行动者开始事件随后结算。
- 删除当前单位、空顺序、重复 ID 和不存在的 ID 均不得崩溃或跳过幸存者。
- 迅捷与迟缓重叠时只在规定的下一轮重排。
- 爆发恢复发生在对应单位的生命周期节点，而非无条件批量恢复。
- 拖动顺序后保持当前行动者 ID，并立即持久化新顺序。

### 3.4 建立可靠快照持久化

Android 当前只直接写 `units.json`；没有原子替换、备份、战斗状态、战斗日志或 GM 日志持久化。

最低要求：

- 保存 `schema_version = 3`、当前规则版本及 v0.3/v1.2 独立名单。
- 保存并恢复 `CombatState`、战斗日志和 GM 日志。
- 使用临时文件、flush/fsync、最后有效备份和原子替换，或使用具备等价事务保证的 Room/DataStore。
- 主文件损坏时隔离损坏副本并恢复备份，同时向用户显示提示。
- 旧根数组或 `units` 格式只迁移到 v1.2 名单，并记录迁移警告。
- 通过 Storage Access Framework 导入导出，不依赖固定 Downloads 路径。
- 日志不自动分享或上传，导出必须由用户显式触发。

### 3.5 修正 ViewModel 对象一致性

Android 当前编辑单位后可能让 `targetUnit` 继续引用旧对象；普通改名也可能丢失临时 HP、爆发状态或状态层数。

验收条件：

- UI 提交 `UnitPatch` 或等价结构，只改变用户编辑的字段。
- 编辑后按 `unitId` 重新解析当前目标，不保留旧对象引用。
- 改名不得改变任何未编辑战斗字段。
- 每项业务动作统一执行：验证、计算、提交、日志、持久化。
- 所有 StateFlow 更新继续通过现有 `updateCounter` 辅助方法发布。

## 4. P1 模型与版本能力

Android `GameUnit` 需要补齐 `DATA_REFERENCE.md` 中的字段，重点包括：

- `initial_max_hp`、`reaction_mobility`
- `current_sp`、`max_sp`
- `current_stamina`、`max_stamina`
- `effect_die`、`auxiliary_die`
- `profession`、`subprofession`、`level`
- `pending_rolls`

`CombatState` 必须增加 `rule_mode`。状态加载时归一化旧名 `困倦 -> 困顿`，过滤未知待处理骰类型，修正 HP/SP/耐力范围和非法顺序下标。

v0.3 必须保留独立的入口和状态/元素集合，不能把同名规则静默映射到 v1.2 实现。

## 5. UI 与交互要求

Android 面向横屏平板，不需要移植 WinUI/Qt 的像素常量、Windows manifest 或 DPI API。应使用 Compose 的 dp/sp、系统复选框和可访问性语义。

- API 22 文本输入继续使用 `AppTextField`，不得换成不兼容的 Material3 `OutlinedTextField`。
- 骰子输入必须是一级流程，不藏在自动随机逻辑后。
- 目标始终是用户当前选择单位。
- “按攻击规则”启用时，攻击者是当前行动者；没有有效当前行动者时拒绝结算。
- 治疗、真实伤害等不适用场景应禁用对应选项。
- 一次操作完成后依次更新单位、写日志和保存；推进回合时先确认名单保存成功，再保存战斗状态。
- 单个 pane 只保留一个纵向滚动容器，避免 `Column.verticalScroll` 与 `LazyColumn` 同轴嵌套。
- 复选框整行可点击，触控目标至少 48dp；不要强制 20dp 的整体点击盒。
- 至少验证 600dp/840dp 宽度、fontScale 1.0/1.3/1.5、横竖屏和 API 22。

## 6. 推荐迁移顺序

1. 将桌面规则回归转成跨端行为用例和固定输入向量。
2. 升级 `GameUnit`、`CombatState`、状态定义和 schema 兼容读取。
3. 移除随机先攻，建立纯领域计算与 Report。
4. 对齐 v1.2 回合、伤害、状态和元素行为。
5. 独立实现 v0.3 分派与测试。
6. 实现完整、原子的仓储快照和损坏恢复。
7. 将 ViewModel 改为事务式业务入口并修复对象引用。
8. 重构自适应平板 UI 和手填骰流程。
9. 接入快速文本、XLSX/SAF 导入和规则目录。
10. 执行单测、仪器测试、API 22 实机检查并输出 APK。

不要先做大规模 UI 美化再补领域规则，否则会把错误契约固化进 ViewModel 和页面状态。

## 7. 测试与验收矩阵

Android 应逐步镜像以下桌面测试范围：

| 范围 | 桌面测试基线 | Android 目标 |
|---|---|---|
| 手填骰与模型 | `test_models.py` | 纯 Kotlin 模型测试 |
| v1.2 战斗 | `test_combat.py` | CombatEngine 报告与 mutation 测试 |
| v0.3/双版本 | `test_dual_rule_modes.py` | 独立版本参数化测试 |
| 持久化恢复 | `test_persistence.py`、`test_app_paths.py` | Repository/Room/DataStore 测试 |
| 角色卡 | `test_character_card_versions.py` | 导入 fixture 与版本拒绝测试 |
| 规则目录 | `test_rule_catalog.py` | 本地索引与搜索排序测试 |
| UI 行为 | `test_rule_browser.py`、`test_ui_motion.py` | ViewModel 与 Compose UI 测试 |

发布前必须通过：

```bash
./gradlew test
./gradlew assembleDebug
```

并人工验证：

- 进程重启后单位、战斗进度和双日志恢复。
- 删除当前行动者后顺序仍有效。
- 待处理爆发骰可关闭应用后继续补填。
- 编辑当前目标后继续结算作用于新对象并能持久化。
- 大字体下文本、复选框和按钮不被裁切。
- API 22 文本输入、中文字体和文件选择可用。

## 8. 近期桌面改动的 Android 影响

必须同步：

- schema 3、双版本独立名单、完整字段与 `pending_rolls`
- 手填骰、双规则分派、回合健壮性和报告结构
- 原子存储、损坏恢复、战斗/GM 日志持久化
- 规则查询的信息架构与显式导入版本校验

仅作交互参考，不直接移植：

- WinUI 风格布局、Qt 动画、集成标题栏和“更多”菜单实现
- Windows `PerMonitorV2` manifest 与 Qt DPI 处理
- Qt 复选框原生指标和 2px 绘制缓冲

Android 对应要求是自适应 Compose 布局、系统控件、dp/sp 和足够触控面积，而不是复制桌面像素值。

## 9. 完成定义

只有同时满足以下条件，Android 端才可声明与桌面端规则兼容：

- 不存在任何引擎自动掷骰路径。
- v0.3/v1.2 模型、名单和规则不会静默混用。
- 核心计算有结构化报告和跨端固定向量测试。
- 回合顺序在删除、空列表和速度状态重叠下稳定。
- 单位、战斗状态和双日志具备事务持久化与损坏恢复。
- 导入失败和公共战斗 API 错误均为用户可见状态，不造成崩溃。
- API 22、平板横屏、大字体和重启恢复均通过验收。

