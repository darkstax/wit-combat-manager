"""TRPG 战斗管理器 - 单位列表面板 (PySide6)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QTreeWidgetItem, QTextEdit, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QDialog, QLabel, QLineEdit, QTextEdit,
    QDialogButtonBox,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QBrush
from models import Unit, THEME


class QuickImportDialog(QDialog):
    """快速导入弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速导入角色")
        self.setMinimumSize(500, 300)
        self.result_data = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("角色名称:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("粘贴骰娘导出文本:"))
        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)

        buttons = QDialogButtonBox()
        import_btn = QPushButton("导入")
        cancel_btn = QPushButton("取消")
        buttons.addButton(import_btn, buttons.ActionRole)
        buttons.addButton(cancel_btn, buttons.RejectRole)
        import_btn.clicked.connect(self._on_import)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _on_import(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请粘贴导入文本")
            return
        self.result_data = {
            "text": text,
            "name": self.name_edit.text().strip() or "快速导入角色",
        }
        self.accept()


class UnitPanel(QWidget):
    units_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.units: list[Unit] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 筛选
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        self.filter_group = QButtonGroup(self)
        for label, val in [("全部", "全部"), ("玩家", "player"), ("怪物", "monster")]:
            rb = QRadioButton(label)
            self.filter_group.addButton(rb)
            filter_layout.addWidget(rb)
            if val == "全部":
                rb.setChecked(True)
                rb.val = val
            else:
                rb.val = val
            rb.toggled.connect(self._refresh_tree)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 单位列表
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["类型", "名称", "HP", "速度", "韧性"])
        self.tree.setColumnWidth(0, 45)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 65)
        self.tree.setColumnWidth(3, 50)
        self.tree.setColumnWidth(4, 65)
        self.tree.setMaximumHeight(175)
        self.tree.currentItemChanged.connect(self._on_select)
        layout.addWidget(self.tree)

        # 详情
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(130)
        layout.addWidget(self.detail_text)

        # 按钮行 1
        btn1 = QHBoxLayout()
        for text, slot in [
            ("添加玩家", lambda: self._add_unit("player")),
            ("添加怪物", lambda: self._add_unit("monster")),
            ("编辑单位", self._edit_unit),
            ("删除单位", self._delete_unit),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn1.addWidget(btn)
        layout.addLayout(btn1)

        # 按钮行 2 — 导入
        btn2 = QHBoxLayout()
        import_btn = QPushButton("导入角色卡 (xlsx)")
        import_btn.clicked.connect(self._import_card)
        btn2.addWidget(import_btn)
        quick_btn = QPushButton("快速导入 (文本)")
        quick_btn.clicked.connect(self._import_quick_text)
        btn2.addWidget(quick_btn)
        layout.addLayout(btn2)

    # ============================================================
    # 数据
    # ============================================================

    def load_units(self, units: list[Unit]):
        self.units = units
        self._refresh_tree()

    def _refresh_tree(self):
        self.tree.clear()
        f = None
        for rb in self.filter_group.buttons():
            if rb.isChecked():
                f = rb.val
                break
        for u in self.units:
            if f != "全部" and u.unit_type != f:
                continue
            type_label = "玩家" if u.unit_type == "player" else "怪物"
            item = QTreeWidgetItem([
                type_label, u.name,
                f"{u.current_hp}/{u.max_hp}",
                str(u.speed),
                f"{u.elemental_tenacity_current}/{u.elemental_tenacity_max}",
            ])
            item.unit_id = u.unit_id
            if u.unit_type == "player":
                item.setBackground(0, QBrush(QColor(THEME["current_actor_bg"])))
            else:
                item.setBackground(0, QBrush(QColor(THEME["monster_row_bg"])))
            self.tree.addTopLevelItem(item)

    def get_selected_unit(self) -> Unit | None:
        item = self.tree.currentItem()
        if not item:
            return None
        for u in self.units:
            if u.unit_id == item.unit_id:
                return u
        return None

    def _on_select(self):
        self._show_detail(self.get_selected_unit())

    # ============================================================
    # 详情
    # ============================================================

    def _show_detail(self, unit: Unit | None):
        self.detail_text.clear()
        if not unit:
            self.detail_text.setPlainText("请选择一个单位")
            return

        type_label = "玩家" if unit.unit_type == "player" else "怪物"
        elite_labels = {0: "精零", 1: "精一", 2: "精二"}

        def fmt_status(s):
            return f"{s['name']}{s['stacks']}" if s["stacks"] > 0 else s["name"]

        status_text = "、".join(fmt_status(s) for s in unit.status_effects) if unit.status_effects else "无"
        burst_info = f"{unit.elemental_burst}（剩余{unit.elemental_burst_remaining}回合）" if unit.is_in_burst() else "无"

        lines = [
            f"名称: {unit.name}  [{type_label}]  {elite_labels.get(unit.elite_stage, '')}",
            f"ID: {unit.unit_id}",
            f"血量: {unit.current_hp}/{unit.max_hp}  临时HP: {unit.temp_hp}",
            f"速度: {unit.speed}  重量: {unit.weight}",
            f"物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  护甲: {unit.armor_type}",
            f"元素韧性: {unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}",
            f"当前爆发: {burst_info}",
            f"状态: {status_text}",
        ]
        self.detail_text.setPlainText("\n".join(lines))

    # ============================================================
    # 按钮操作
    # ============================================================

    def _add_unit(self, unit_type: str = "player"):
        from ui.unit_dialog import UnitDialog
        unit = Unit(unit_type=unit_type)
        dlg = UnitDialog(unit, self)
        if dlg.exec() == UnitDialog.Accepted and dlg.result:
            self.units.append(dlg.result)
            self._refresh_tree()
            self._notify_change()

    def _edit_unit(self):
        unit = self.get_selected_unit()
        if not unit:
            QMessageBox.information(self, "提示", "请先选择一个单位")
            return
        from ui.unit_dialog import UnitDialog
        dlg = UnitDialog(unit, self)
        if dlg.exec() == UnitDialog.Accepted and dlg.result:
            self._refresh_tree()
            self._show_detail(dlg.result)
            self._notify_change()

    def _delete_unit(self):
        unit = self.get_selected_unit()
        if not unit:
            QMessageBox.information(self, "提示", "请先选择一个单位")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除「{unit.name}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.units.remove(unit)
            self._refresh_tree()
            self._show_detail(None)
            self._notify_change()

    def _import_card(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择角色卡文件", "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            from character_card import import_character_card
            unit = import_character_card(filepath)
        except FileNotFoundError:
            QMessageBox.critical(self, "导入失败", f"文件不存在: {filepath}")
            return
        except ValueError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析角色卡:\n{e}")
            return

        if not unit.name or unit.name == "未命名角色":
            QMessageBox.warning(self, "警告", "未能读取到角色名称，请手动编辑")

        self.units.append(unit)
        self._refresh_tree()
        self._notify_change()
        QMessageBox.information(
            self, "导入成功",
            f"已导入角色: {unit.name}\n"
            f"HP: {unit.max_hp}  物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  "
            f"精英: {unit.elite_stage}"
        )

    def _import_quick_text(self):
        dlg = QuickImportDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result_data:
            return
        try:
            from character_card import import_from_quick_text
            unit = import_from_quick_text(dlg.result_data["text"], name=dlg.result_data["name"])
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析文本:\n{e}")
            return

        self.units.append(unit)
        self._refresh_tree()
        self._notify_change()
        QMessageBox.information(
            self, "导入成功",
            f"已导入角色: {unit.name}\n"
            f"HP: {unit.max_hp}  物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  "
            f"速度: {unit.speed}  重量: {unit.weight}\n"
            f"(精英化等级未包含在快速导入中，默认为0)"
        )

    def _notify_change(self):
        self.units_changed.emit(self.units)

    # ============================================================
    # 公共接口
    # ============================================================

    def get_players(self) -> list[Unit]:
        return [u for u in self.units if u.unit_type == "player"]

    def get_monsters(self) -> list[Unit]:
        return [u for u in self.units if u.unit_type == "monster"]

    def find_unit(self, unit_id: str) -> Unit | None:
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        return None
