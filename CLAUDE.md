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

待定 — 准备开发新功能
