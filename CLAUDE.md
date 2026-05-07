# WIT 战斗管理器 — 工作记录

## 项目状态

### 当前分支：master (PySide6 重构版)
- **已完成**：Tkinter → PySide6 完整迁移
  - `main.py` — QApplication + DPI fix
  - `ui/main_window.py` — QMainWindow + BackgroundWidget + 水印系统
  - `ui/unit_panel.py` — QTreeWidget + QuickImportDialog
  - `ui/unit_dialog.py` — QDialog 表单
  - `ui/combat_panel.py` — 战斗控制面板
  - 数据层不变：`models.py`, `combat.py`, `persistence.py`, `character_card.py`
- **背景功能**：BackgroundWidget 用 QPainter.setOpacity() 绘制水印，水印强度可调 (10%-70%)，设置持久化到 settings.json
- **导入功能**：xlsx 角色卡 + 骰娘快速文本导入
- **GitHub**: darkstax/wit-combat-manager, tag v2.1 已发布

### v2.1 备份
- Clone 到 `../wit_combat_manager_v2.1/` (tkinter 版本，e0c1f7c)

### 工作目录结构
```
trpg_manager/
├── 工作资料/          # 核心项目的资料 & 测试目录（数据样本、规则文档、临时测试脚本等）
├── main.py
├── ui/
├── models.py
├── combat.py
├── persistence.py
├── character_card.py
└── ...
```

## 当前任务

待定 — 准备开发新功能
