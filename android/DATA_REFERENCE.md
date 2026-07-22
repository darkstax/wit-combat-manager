# WIT Android 数据契约

本文档描述桌面版 WIT 战斗管理器当前使用的数据模型、枚举、持久化格式和规则索引契约，供 Android 端重实现、迁移或共享数据时使用。

文档基线：`schema_version = 3`，规则版本 `v0.3` 与 `v1.2`。

## 1. 边界与数据来源

- 权威实现：`models.py`、`combat_report.py`、`persistence.py`、`character_card.py`、`rule_catalog.py`。
- 骰子由玩家或 GM 实际投掷，程序只接收逐骰结果或检定总值，不自动掷骰。
- 本文只记录稳定的数据结构、枚举、默认值和索引统计。
- 不复制 `工作资料/`、PDF、XLSX 正文、隐藏计算表或完整规则文本。
- 不读取或展示真实的 `data.json`、`combat_state.json`、设置、战斗日志和 GM 日志。
- 示例数据均为虚构内容。

## 2. 版本与兼容策略

```kotlin
enum class RuleMode(val wireValue: String) {
    V0_3("0.3"),
    V1_2("1.2")
}
```

可接受的输入别名：`0.3`、`03`、`v0.3`、`1.2`、`12`、`v1.2`。序列化时必须写标准值 `0.3` 或 `1.2`。

两版名单、状态集合、元素规则和计算流程相互独立；不能按同名字段静默混用。

## 3. 手填骰输入

### 3.1 DiceGroup

| 字段 | Kotlin 类型 | 默认值 | 约束 |
|---|---|---:|---|
| `count` | `Int` | 必填 | 不得小于 0 |
| `sides` | `Int` | 必填 | 必须大于 0 |
| `values` | `List<Int>` | `emptyList()` | 填写时数量必须等于 `count`，每项在 `1..sides` |
| `label` | `String` | `""` | 仅用于展示 |

`total = values.sum()`。

### 3.2 RollInput

| 字段 | Kotlin 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `groups` | `List<DiceGroup>` | 空列表 | 一组或多组手填骰 |
| `fixedModifier` | `Int` | `0` | 固定修正 |
| `totalOverride` | `Int?` | `null` | GM 直接填写的检定总值 |

若 `totalOverride != null`，最终值直接使用它；否则为所有骰值之和加 `fixedModifier`。两种输入都缺失时应提示使用者填写。

## 4. Unit 核心实体

Android 建议使用 Kotlin `data class`，JSON 字段名保持 snake_case，以便与桌面端直接交换。

| JSON 字段 | Kotlin 类型 | 默认值 | 说明与约束 |
|---|---|---:|---|
| `unit_id` | `String` | 自动生成 8 位 ID | 单位稳定主键 |
| `name` | `String` | `""` | 显示名称 |
| `unit_type` | `String` | `"player"` | `player` 或 `monster` |
| `current_hp` | `Int` | `10` | 归一化到 `0..max_hp` |
| `max_hp` | `Int` | `10` | 不得小于 0 |
| `initial_max_hp` | `Int` | `0` | 小于等于 0 时使用当前 `max_hp` |
| `speed` | `Int` | `10` | 速度 |
| `reaction_mobility` | `Int` | `0` | 反应机动 |
| `physical_resist` | `Int` | `0` | 物理抗性 |
| `magic_resist` | `Int` | `0` | 法术抗性 |
| `armor_type` | `String` | `"轻甲"` | 护甲类型 |
| `status_effects` | `List<StatusInstance>` | 空列表 | 当前状态 |
| `temp_hp` | `Int` | `0` | 临时 HP / 屏障数值 |
| `weight` | `Int` | `0` | 重量等级 |
| `elite_stage` | `Int` | `0` | `0`、`1`、`2` |
| `elemental_tenacity_current` | `Int` | `6` | 当前元素韧性 |
| `elemental_tenacity_max` | `Int` | `6` | 元素韧性上限 |
| `elemental_burst` | `String` | `""` | 当前爆发类型，空串表示无 |
| `elemental_burst_remaining` | `Int` | `0` | 剩余持续回合 |
| `current_sp` | `Int` | `0` | 归一化到 `0..max_sp` |
| `max_sp` | `Int` | `9` | 不得小于 0 |
| `current_stamina` | `Int` | `0` | 归一化到 `0..max_stamina` |
| `max_stamina` | `Int` | `0` | 不得小于 0 |
| `effect_die` | `String` | `""` | 例如 `d8` |
| `auxiliary_die` | `String` | `""` | 例如 `d6` |
| `profession` | `String` | `""` | 主职业或法术职业 |
| `subprofession` | `String` | `""` | 分支职业或流派 |
| `level` | `Int` | `1` | 最小为 1 |
| `pending_rolls` | `List<PendingRoll>` | 空列表 | 尚待使用者填写的爆发骰 |

```kotlin
data class StatusInstance(
    val name: String,
    val stacks: Int = 0
)

data class PendingRoll(
    val kind: String,          // elemental_burst | v03_elemental_burst
    val element_type: String,
    val instances: Int,
    val rule_mode: String
)
```

`濒死` 状态存在时 `current_hp` 必须为 0。`pending_rolls` 中 `instances <= 0` 或未知 `kind` 的记录应在加载时丢弃。

### 4.1 派生值

- `effectiveHp = current_hp + temp_hp`
- `isDying = current_hp <= 0 || 存在“濒死”`
- `isDead = max_hp <= 0`
- 伤残等级：生命上限未下降为 0；低于初始上限 50% 为 2；低于 10% 为 3；其余为 1。
- v1.2 精英韧性上限：精零 6、精一 9、精二 12。
- 默认 SP 上限：精零 9、精一 12、精二 15。

## 5. CombatState

| JSON 字段 | Kotlin 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `turn` | `Int` | `0` | 当前轮次，不得小于 0 |
| `now_index` | `Int` | `0` | 当前行动者在顺序中的下标 |
| `turn_order` | `List<String>` | 空列表 | `unit_id` 顺序 |
| `initiative_mode` | `String` | `traditional` | `team`、`traditional`、`manual`；v0.3 使用 `v03_speed` |
| `initiative_rolls` | `Map<String, Int>` | 空映射 | 单位 ID 到手填检定结果 |
| `active` | `Boolean` | `false` | 战斗是否进行中 |
| `first_team` | `String?` | `null` | `player` 或 `monster` |
| `rule_mode` | `String` | `1.2` | 标准规则版本值 |
| `pending_reorder` | `Boolean` | `false` | 迅捷/迟缓导致下一轮重排 |

加载时必须过滤空 ID。若顺序为空，`now_index` 归零；否则夹取到有效范围。

## 6. 状态数据

状态定义结构：

```kotlin
data class StatusDefinition(
    val name: String,
    val polarity: Polarity,   // POSITIVE | NEGATIVE
    val endEvent: EndEvent,
    val counter: Boolean,
    val upgradeTo: String? = null,
    val aliases: List<String> = emptyList()
)
```

结束事件值：`manual`、`attack`、`turn_end`、`heal_received`、`heal_effect`、`activation`、`counter`、`move_prep`。

### 6.1 v1.2 正面状态

`伤害强化、精准、魅影、嘲讽、被嘲讽、迅捷、护盾、屏障、隐匿、迷彩、抵抗、元素屏障、暴击、免疫、穿透、亲和`

### 6.2 v1.2 负面状态

`脆弱、失能、失能后效、标记、麻痹、眩晕、寒冷、冻结、困顿、睡眠、停顿、束缚、失重、浮空、沉默、战栗、禁疗、迟缓、恐惧、目盲、濒死`

### 6.3 v0.3 正面状态

`力量、穿甲、庇护、迅捷、免疫、隐匿、亲和`

### 6.4 v0.3 负面状态

`易伤、虚弱、失能、失能后效、标记、寒冷、冻结、震慑、眩晕、困顿、睡眠、停顿、束缚、失重、浮空、禁疗、迟缓、濒死`

### 6.5 升级与计数规则

| 版本 | 升级链 |
|---|---|
| v1.2 | 麻痹→眩晕、寒冷→冻结、困顿→睡眠、停顿→束缚 |
| v0.3 | 寒冷→冻结、震慑→眩晕、困顿→睡眠、停顿→束缚、失重→浮空 |

v1.2 带 X 计数器：`伤害强化、护盾、屏障、抵抗、元素屏障、脆弱、失重`。v0.3 当前没有通用 X 状态。

兼容别名：旧数据中的 `困倦` 归一化为 `困顿`。

## 7. 元素数据

### 7.1 元素类型

- v1.2：`凋亡损伤、组织损伤、毒性损伤、侵蚀损伤、灼燃损伤、神经损伤`
- v0.3：上述类型加 `结晶损伤`

### 7.2 v1.2 爆发结构

| 元素 | 真实伤害倍率 | 附加规则 | 状态 |
|---|---:|---|---|
| 凋亡损伤 | 2 | 失去 3 SP；无 SP 可失去时额外造成一次真实伤害 | 迟缓 |
| 组织损伤 | 3 | 无 | 迟缓 |
| 毒性损伤 | 2 | 爆发期间施加禁疗 | 迟缓、禁疗 |
| 侵蚀损伤 | 2 | 爆发期间受到物理伤害时增加 1 辅助骰 | 迟缓 |
| 灼燃损伤 | 2 | 爆发期间受到法术伤害时增加 1 辅助骰 | 迟缓 |
| 神经损伤 | 1 | 爆发期间施加眩晕 | 迟缓、眩晕 |

## 8. 战斗报告 DTO

Android 计算层应返回结构化 DTO，再由 UI 格式化消息。

```kotlin
data class DamageReport(
    val attackMissed: Boolean = false,
    val blockedByShield: Boolean = false,
    val shieldRemaining: Int = 0,
    val rawAmount: Int = 0,
    val damageType: String = "",
    val resistance: Int = 0,
    val resistReduced: Int = 0,
    val dmgBoostAdded: Int = 0,
    val vulnAdded: Int = 0,
    val auxiliaryAdded: Int = 0,
    val finalMultiplier: Double = 1.0,
    val barrierAbsorbed: Int = 0,
    val tempHpAfter: Int = 0,
    val barrierDepleted: Boolean = false,
    val finalDamage: Int = 0,
    val hpBefore: Int = 0,
    val hpAfter: Int = 0,
    val maxHpBefore: Int = 0,
    val maxHpAfter: Int = 0,
    val maxHpDamage: Int = 0,
    val isDying: Boolean = false,
    val wasDying: Boolean = false,
    val isDead: Boolean = false,
    val sleepBroken: Boolean = false
)
```

```kotlin
data class HealingReport(
    val blockedByRegenBlock: Boolean = false,
    val blockedByDying: Boolean = false,
    val invalidAmount: Boolean = false,
    val affinityConsumed: Boolean = false,
    val hpBefore: Int = 0,
    val hpAfter: Int = 0,
    val healed: Int = 0,
    val healEffectCleared: List<String> = emptyList()
)
```

`StatusReport` 字段：`blockedByImmune`、`blockedByResist`、`blockedBySave`、`invalidStatus`、`resistRemaining`、`isMark`、`markSubTriggers`、`upgraded`、`upgradedFrom`、`upgradedTo`、`stacked`、`stacksBefore`、`stacksAfter`、`simpleApplied`、`alreadyExists`、`statusName`、`requestedName`、`stacksDelta`、`markConsumed`。

`ElementalReport` 字段：`isBurstPeriod`、`trueDmgDealt`、`barrierAbsorbed`、`barrierDepleted`、`tenacityReduced`、`tenacityBefore`、`tenacityAfter`、`burstTriggered`、`burstType`、`burstStatuses`、`overflow`、`invalidType`、`invalidAmount`、`burstRollRequired`、`burstRoll`、`burstDamageInstances`、`burstTrueDamage`、`spSpent`。

## 9. 规则目录与搜索

```kotlin
data class RuleEntry(
    val version: String,
    val category: String,
    val title: String,
    val body: String,
    val source: String,
    val keywords: List<String>
)
```

搜索文本由 `title + category + version + source + body + keywords` 组成，大小写不敏感；查询中的每个词都必须出现。优先级依次为：标题完全匹配、标题前缀、标题包含、分类、关键词、正文。

展示目录：

- 战斗规则：按详细分类分组。
- 职业与战技：职业 → 战技 / 被动。
- 源石技艺：流派 → 法术与技艺 / 被动 / 召唤物。
- v0.3 源石技艺：大类 → 小类。

数量校验基线：内置摘要 29 条；当前四份配套工作簿可建立 874 条外部索引，读取错误为 0。外部索引正文不得直接固化进 Android 源码。

## 10. 角色卡与快速文本导入

Android 若不直接读取 XLSX，可先实现以下快速文本标签：

| 可识别标签 | Unit 字段 |
|---|---|
| 生命值上限、生命值 | `max_hp` |
| 物理抗性 | `physical_resist` |
| 法术抗性 | `magic_resist` |
| 元素韧性 | `elemental_tenacity_current/max` |
| 反应机动、速度 | `speed` 与 `reaction_mobility` |
| 重量等级 | `weight` |
| SP上限、技力上限 | `max_sp` |
| SP、技力 | `current_sp` |

未读取到生命值时使用 10。v0.3 默认韧性 10；v1.2 默认韧性 6、默认速度 5、默认 SP 上限 9。

## 11. 持久化格式

### 11.1 data.json

```json
{
  "schema_version": 3,
  "active_rule_mode": "1.2",
  "rosters": {
    "0.3": [],
    "1.2": [
      {
        "unit_id": "demo0001",
        "name": "示例单位",
        "unit_type": "player",
        "current_hp": 10,
        "max_hp": 10,
        "initial_max_hp": 10,
        "speed": 5,
        "reaction_mobility": 5,
        "physical_resist": 0,
        "magic_resist": 0,
        "armor_type": "轻甲",
        "status_effects": [],
        "temp_hp": 0,
        "weight": 0,
        "elite_stage": 0,
        "elemental_tenacity_current": 6,
        "elemental_tenacity_max": 6,
        "elemental_burst": "",
        "elemental_burst_remaining": 0,
        "current_sp": 0,
        "max_sp": 9,
        "current_stamina": 0,
        "max_stamina": 0,
        "effect_die": "d8",
        "auxiliary_die": "d6",
        "profession": "示例职业",
        "subprofession": "示例分支",
        "level": 1,
        "pending_rolls": []
      }
    ]
  }
}
```

### 11.2 combat_state.json

```json
{
  "schema_version": 3,
  "combat_state": {
    "turn": 1,
    "now_index": 0,
    "turn_order": ["demo0001"],
    "initiative_mode": "traditional",
    "initiative_rolls": {"demo0001": 12},
    "active": true,
    "first_team": null,
    "rule_mode": "1.2",
    "pending_reorder": false
  }
}
```

兼容旧格式：根节点为单位数组，或使用旧的 `units` 字段时，统一迁移到 v1.2 名单并产生迁移提示。

桌面端采用临时文件写入、`fsync`、旧文件 `.bak`、原子替换。Android 端应提供等价的事务保证。

## 12. Android 存储建议

- `Unit`、`StatusInstance`、`PendingRoll`：Room；状态和待处理骰可用关联表，或使用受版本管理的 JSON TypeConverter。
- 当前规则版本、动画偏好、背景设置：DataStore Preferences。
- `CombatState`：Room 单行表或 Proto DataStore；顺序和检定映射必须事务更新。
- 战斗日志与 GM 日志：应用内部存储，不参与自动导出，分享前必须由用户显式确认。
- 数据库迁移必须以 `schema_version` 为依据，不以应用版本号替代。
- 导入文件通过 Storage Access Framework 获取，不依赖固定 Downloads 路径。

## 13. 维护与校验

以下数据应从 Python 权威实现自动生成或对照测试：

- `RuleMode`、`Unit`、`CombatState` 字段与默认值。
- 两版状态集合、升级链、X 状态和元素集合。
- `ELEMENTAL_BURST_EFFECTS`。
- 四类战斗报告 DTO。
- 快速文本标签映射。
- `RuleEntry` 分类数量统计。

规则说明正文、工作簿单元格内容和人工裁定仍需单独授权与人工审阅，不属于此数据契约。
