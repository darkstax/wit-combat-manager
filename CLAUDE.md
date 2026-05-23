# WIT 战斗管理器 — 工作记录

## 项目状态

### 当前分支：master (PySide6 重构版)
- **已完成**：Tkinter → PySide6 完整迁移
  - `main.py` — QApplication + DPI fix
  - `ui/main_window.py` — QMainWindow + BackgroundWidget + 水印系统 + 战斗日志/GM日志双栏
  - `ui/unit_panel.py` — QTreeWidget + QuickImportDialog
  - `ui/unit_dialog.py` — QDialog 表单（精英阶段自动同步韧性）
  - `ui/combat_panel.py` — 先攻下拉栏 + 战斗操作合并面板
  - 数据层：`models.py` (含 THEME 颜色常量), `combat.py` (含 _calc_* 纯计算函数), `persistence.py` (原子保存), `character_card.py`
  - 新增：`combat_report.py` (结构化战斗结果), `test_combat.py` (59 个 pytest 用例)
- **背景功能**：BackgroundWidget 用 QPainter.setOpacity() 绘制水印，水印强度可调 (10%-70%)，设置持久化到 settings.json
- **导入功能**：xlsx 角色卡 + 骰娘快速文本导入
- **持久化**：单位数据原子保存 (data.json)，战斗日志/GM日志分别持久化 (combat_log.txt / gm_log.txt)
- **GitHub**: darkstax/wit-combat-manager, tag v2.1 已发布

### v2.1 备份
- Clone 到 `../wit_combat_manager_v2.1/` (tkinter 版本，e0c1f7c)

### 工作目录结构
```
trpg_manager/
├── 工作资料/            # 核心项目的资料 & 测试目录（数据样本、规则文档、临时测试脚本等）
├── main.py
├── models.py            # Unit / CombatState / 状态常量 / THEME
├── combat.py            # 战斗逻辑（_calc_* 纯计算 + 公开 API）
├── combat_report.py     # DamageReport / HealingReport / StatusReport / ElementalReport
├── persistence.py       # 原子保存 + .bak 备份
├── character_card.py
├── test_combat.py       # pytest (59 用例)
├── ui/
│   ├── main_window.py   # 主窗口 + 双日志栏 + 背景 + 菜单
│   ├── unit_panel.py    # 单位列表 + 筛选 + 详情
│   ├── unit_dialog.py   # 添加/编辑弹窗
│   └── combat_panel.py  # 先攻/战斗操作/行动顺序
├── combat_log.txt       # 战斗日志持久化
├── gm_log.txt           # GM日志持久化
└── data.json            # 单位数据
```

## 代码审查记录 (2026-05-11)

### 高优先级 ✅ 已全部修复
- ✅ **X_STATUSES 重复定义** — 已删除 `combat.py` 本地定义，统一从 `models` 导入。
- ✅ **编辑精英阶段不更新韧性** — `UnitDialog` 新增 `_on_elite_changed` 信号槽，切换精英阶段自动同步韧性上限。
- ✅ **无数据备份** — `persistence.py` 改为 `os.replace` 原子保存；JSON 损坏时自动重命名为 `.bak`。
- ✅ **HP归零不报濒死** — `apply_damage` / `_apply_true_damage` 中 HP 首次归零时追加濒死警告。

### 中优先级 ✅ 已全部修复
- ✅ **stdout 全局劫持** — 已移除，改为 `CombatPanel.set_log_callback` 显式回调。
- ✅ **零测试覆盖** — 新增 `test_combat.py`，59 个 pytest 用例覆盖伤害/治疗/状态/元素/先攻/回合。
- ✅ **逻辑/表现耦合** — 新增 `combat_report.py` 定义四个 Report dataclass，`combat.py` 提取 `_calc_*` 纯计算函数，公开 API 不变。

### 低优先级 ✅ 已全部修复（除快捷键外）
- ✅ **QTextEdit2 别名 hack** — 已删除，统一使用 `QTextEdit`。
- ✅ **_get_selected_unit 私有方法** — 已改为公开 `get_selected_unit()`。
- ✅ **README 依赖说明** — 已改为 `pip install PySide6`。
- ✅ **硬编码颜色** — `models.py` 新增 `THEME` dict，3 处 QColor 改为引用 `THEME["key"]`。
- ✅ **战斗日志导出** — 菜单栏新增"导出战斗日志..."，同时导出战斗+GM日志。
- ✅ **GUI 布局优化** — 先攻模式改为下拉栏、伤害/元素/状态合并为"战斗操作"、日志分栏+GM日志可编辑+持久化。

### 暂不做
- 键盘快捷键（用户跳过）
- 撤销功能（需命令栈架构，独立大功能）
- 暗色主题全量支持（`THEME` dict 已为后续做铺垫）

## 当前任务

### 任务 3：元素爆发溢出损伤未转换 🔴
**规则依据**：`工作资料/元素损伤.txt` — "若元素爆发期间的单位受到了（也包括令元素爆发时超出的）元素损伤，则会改为受到损伤数额×3的真实伤害。"

**当前行为**：`Unit.reduce_tenacity()` 返回溢出值，但 `_apply_elemental_mutations` 丢弃了它。韧性 3、受 10 点损伤时，3 点扣韧性触发爆发，7 点溢出静默消失。

**目标行为**：溢出部分 `overflow * 3` 转为真实伤害，调用 `_apply_true_damage`。

**涉及文件**：`combat.py`（`_apply_elemental_mutations` 约 370 行）

---

## 代码审计报告 (2026-05-19)

> 基于全量代码审查 + `工作资料/元素损伤.txt` 和 `buff.txt` 规则对照。
> 注：`true_dmg_mult`（2/3/2/2/2/1）是触发爆发瞬间的 N×辅助骰初始伤害，程序不跟踪攻击者辅助骰故交由 GM 手动输入 —— 设计正确，非 bug。

### 🔴 严重（2项）— ✅ 已全部修复 (2026-05-20)

#### 1. ✅ 元素爆发溢出损伤未转为真实伤害
- **修复**：`ElementalReport` 新增 `overflow` 字段；`_calc_elemental` 记录溢出值；`_apply_elemental_mutations` 爆发触发后 `overflow × 3` 转真伤

#### 2. ✅ 迅捷+迟缓共存 → `_apply_speed_reorder` 崩溃
- **修复**：去重 — 重叠 uid 从 swifts/slows 双列表移除（抵消，原位不动），状态照常清除
- **附加**：6 个公开战斗 API (`apply_damage/healing/elemental_damage/status` + `advance_turn`/`next_actor`) 加 try-catch 安全网，异常返回 `[错误] ...` 消息指引主持手动干预

### 🟡 中等（5项）— ✅ 已全部修复 (2026-05-20)

#### 3. ✅ UnitDialog 允许 current_hp > max_hp
- **修复**：`_on_save` 追加 `current_hp > max_hp` 校验

#### 4. ✅ 战斗中删除单位：幽灵 ID 残留在 turn_order
- **修复**：`next_actor` 开头用 `valid_ids` 集合过滤掉已不存在的 unit_id

#### 5. ✅ 战斗状态不持久化
- **修复**：`persistence.py` 新增 `save_combat_state` / `load_combat_state` / `delete_combat_state`；`combat_panel.py` 每次状态变更自动保存，`_end_combat` 时删除，`_start_combat` 时检测未完成战斗并提示恢复

#### 6. ✅ closeEvent 保存失败阻塞窗口关闭
- **修复**：`_save()` 和 `_save_logs()` 分别包 try-catch

#### 7. ✅ _load_logs 仅捕获 FileNotFoundError
- **修复**：except 扩展为 `(FileNotFoundError, PermissionError, OSError)`

### 🟢 轻微（6项）

#### 8. 死代码：_apply_mark() 函数（76行）
- **文件**：`combat.py` 约 570-595 行
- **说明**：`apply_status` 通过 `StatusReport.is_mark` 分支在 `_apply_status_mutations` 中内联处理，该函数从未调用，可安全删除

#### 9. 团队先攻平局永远玩家先动
- **文件**：`combat.py` `team_initiative()`
- **现状**：`if player_score >= monster_score`（>= 偏袒玩家），无随机因素

#### 10. .bak 备份被反复覆盖
- **文件**：`persistence.py` `load_data()`
- **现状**：连续两次 JSON 损坏时，第二次 `os.replace` 覆盖第一次的 `.bak`

#### 11. turn_order 为空时无限空转
- **文件**：`combat.py` `next_actor()`
- **现状**：所有单位删除后 turn_order=[]，每次点"下一行动" Turn+1 但无事发生

#### 12. 真伤模式"攻击"复选框无效果
- **文件**：`combat.py` `apply_damage()` / `ui/combat_panel.py`
- **现状**：真伤路径不走 `is_attack` 参数，复选框可勾选但无效 → 建议真伤时禁用

#### 13. 元素韧性溢出损伤静默丢弃
- **文件**：`combat.py` `_apply_elemental_mutations()`
- **说明**：与 #1 同一位置，溢出值被丢弃（#1 已作为严重问题单独追踪）

---

### 📊 审计评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 规则还原度 | ⭐⭐⭐⭐ | 除溢出损伤外，与 `元素损伤.txt` / `buff.txt` 高度一致 |
| 逻辑正确性 | ⭐⭐⭐⭐ | 2 严重 + 5 中等均已修复 |
| 代码架构 | ⭐⭐⭐⭐⭐ | 纯计算分离、Report dataclass、信号驱动日志、DI 注入 |
| 测试覆盖 | ⭐⭐⭐⭐ | 59 用例覆盖核心路径 |
| 文档 | ⭐⭐⭐⭐ | CLAUDE.md 详尽，规则对照清晰 |
