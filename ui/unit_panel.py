"""TRPG 战斗管理器 - 单位列表面板 (PySide6)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QTreeWidgetItem, QTextEdit, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QDialog, QLabel, QLineEdit,
    QDialogButtonBox, QMenu, QComboBox,
)
from PySide6.QtCore import QPoint, Signal, QTimer
from PySide6.QtGui import QColor, QBrush
from models import RuleMode, Unit, THEME
from ui.fluent import fade_in, section_label, set_button_role


class QuickImportDialog(QDialog):
    """快速导入弹窗"""

    def __init__(self, parent=None, rule_mode: RuleMode | str = RuleMode.V1_2):
        super().__init__(parent)
        self.rule_mode = RuleMode.coerce(rule_mode)
        self.setWindowTitle("快速导入角色")
        self.setMinimumSize(560, 390)
        self.result_data = None
        self._last_report = None
        self._type_manually_edited = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("快速导入角色")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        layout.addWidget(QLabel("角色名称"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("未填写时自动从文本提取")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("类型"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("玩家", "player")
        self.type_combo.addItem("怪物", "monster")
        self.type_combo.addItem("友方", "ally")
        self.type_combo.setCurrentIndex(0)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        layout.addWidget(QLabel("骰娘导出文本"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "粘贴骰娘导出文本，例如：\n"
            "名称：干员A\n职业：先锋\n分支：冲锋手\n等级：10\n"
            "HP：35\nSP：4/12\n耐力上限：8\n护甲：轻甲"
        )
        layout.addWidget(self.text_edit)

        layout.addWidget(QLabel("解析预览"))
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(110)
        self.preview_edit.setPlaceholderText("输入文本后自动解析预览")
        layout.addWidget(self.preview_edit)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self.text_edit.textChanged.connect(self._preview_timer.start)

        buttons = QDialogButtonBox()
        import_btn = QPushButton("导入")
        set_button_role(import_btn, "primary")
        cancel_btn = QPushButton("取消")
        buttons.addButton(import_btn, buttons.ActionRole)
        buttons.addButton(cancel_btn, buttons.RejectRole)
        import_btn.clicked.connect(self._on_import)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, index):
        """用户手动修改类型后，不再被自动识别覆盖"""
        self._type_manually_edited = True

    def _refresh_preview(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            self.preview_edit.clear()
            self._last_report = None
            return
        try:
            from character_card import import_from_quick_text
            report = import_from_quick_text(text, self.rule_mode, report=True)
        except Exception as e:
            self.preview_edit.setPlainText(f"解析失败: {e}")
            self._last_report = None
            return
        self._last_report = report
        unit = report.unit
        if not self._type_manually_edited:
            index = self.type_combo.findData(unit.unit_type)
            if index >= 0:
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(index)
                self.type_combo.blockSignals(False)
        type_labels = {"player": "玩家", "monster": "怪物", "ally": "友方"}
        lines = [
            f"名称: {unit.name}  类型: {type_labels.get(unit.unit_type, unit.unit_type)}（自动识别）",
            f"HP: {unit.max_hp}  SP: {unit.current_sp}/{unit.max_sp}",
            f"职业: {unit.profession or '未识别'}  分支: {unit.subprofession or '未识别'}  等级: {unit.level}",
            f"耐力: {unit.current_stamina}/{unit.max_stamina}  护甲: {unit.armor_type}",
        ]
        if report.warnings:
            lines.append("提示: " + "；".join(report.warnings))
        self.preview_edit.setPlainText("\n".join(lines))

    def _on_import(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请粘贴导入文本")
            return
        self._refresh_preview()  # 确保 report 与当前文本一致（防抖可能尚未触发）
        self.result_data = {
            "text": text,
            "name": self.name_edit.text().strip(),
            "unit_type": self.type_combo.currentData(),
            "report": self._last_report,
        }
        self.accept()


class UnitPanel(QWidget):
    units_changed = Signal(list)
    selection_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavigationPane")
        self.units: list[Unit] = []
        self.last_persist_ok = True
        self.rule_mode = RuleMode.V1_2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel("单位")
        title.setObjectName("PageTitle")
        heading.addWidget(title)
        heading.addStretch()
        self.count_label = QLabel("0 个单位")
        self.count_label.setObjectName("SecondaryText")
        heading.addWidget(self.count_label)
        layout.addLayout(heading)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)
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
        layout.addLayout(filter_layout)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["类型", "名称", "HP", "速度", "韧性"])
        self.tree.setColumnWidth(0, 42)
        self.tree.setColumnWidth(1, 92)
        self.tree.setColumnWidth(2, 60)
        self.tree.setColumnWidth(3, 44)
        self.tree.setColumnWidth(4, 58)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_select)
        layout.addWidget(self.tree, 3)

        self.detail_heading = section_label("单位信息")
        self.detail_heading.setVisible(False)
        layout.addWidget(self.detail_heading)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(104)
        self.detail_text.setMaximumHeight(148)
        self.detail_text.setPlaceholderText("选择单位后显示属性与状态")
        self.detail_text.setVisible(False)
        layout.addWidget(self.detail_text)

        command_bar = QHBoxLayout()
        command_bar.setSpacing(6)

        self.add_btn = QPushButton("添加")
        set_button_role(self.add_btn, "primary")
        add_menu = QMenu(self.add_btn)
        add_menu.addAction("添加玩家", lambda: self._add_unit("player"))
        add_menu.addAction("添加怪物", lambda: self._add_unit("monster"))
        self.add_btn.clicked.connect(
            lambda: add_menu.popup(
                self.add_btn.mapToGlobal(QPoint(0, self.add_btn.height() + 4))
            )
        )
        command_bar.addWidget(self.add_btn, 1)

        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._edit_unit)
        command_bar.addWidget(edit_btn, 1)

        delete_btn = QPushButton("删除")
        set_button_role(delete_btn, "danger")
        delete_btn.clicked.connect(self._delete_unit)
        command_bar.addWidget(delete_btn, 1)

        self.import_btn = QPushButton("导入")
        import_menu = QMenu(self.import_btn)
        self.card_import_action = import_menu.addAction("v1.2 角色卡")
        self.card_import_action.triggered.connect(self._import_card)
        import_menu.addAction("文本导入", self._import_quick_text)
        self.import_btn.clicked.connect(
            lambda: import_menu.popup(
                self.import_btn.mapToGlobal(QPoint(0, self.import_btn.height() + 4))
            )
        )
        command_bar.addWidget(self.import_btn, 1)
        layout.addLayout(command_bar)

    # ============================================================
    # 数据
    # ============================================================

    def load_units(self, units: list[Unit]):
        self.units = units
        self._refresh_tree()

    def _refresh_tree(self):
        had_selection = self.tree.currentItem() is not None
        self.tree.clear()
        if had_selection:
            self.selection_changed.emit(None)
        self.count_label.setText(f"{len(self.units)} 个单位")
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
            if u.unit_type == "monster":
                brush = QBrush(QColor(THEME["monster_row_bg"]))
                for column in range(self.tree.columnCount()):
                    item.setBackground(column, brush)
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
        unit = self.get_selected_unit()
        self._show_detail(unit)
        self.selection_changed.emit(unit)
        if unit is not None:
            fade_in(self.detail_text, duration=130, start_opacity=0.76)

    # ============================================================
    # 详情
    # ============================================================

    def _show_detail(self, unit: Unit | None):
        self.detail_text.clear()
        if not unit:
            self.detail_heading.setVisible(False)
            self.detail_text.setVisible(False)
            return

        self.detail_heading.setVisible(True)
        self.detail_text.setVisible(True)

        type_label = "玩家" if unit.unit_type == "player" else "怪物"
        elite_labels = {0: "精零", 1: "精一", 2: "精二"}

        def fmt_status(s):
            return f"{s['name']}{s['stacks']}" if s["stacks"] > 0 else s["name"]

        status_text = "、".join(fmt_status(s) for s in unit.status_effects) if unit.status_effects else "无"
        burst_info = f"{unit.elemental_burst}（剩余{unit.elemental_burst_remaining}回合）" if unit.is_in_burst() else "无"
        pending_info = f"{len(unit.pending_rolls)} 项" if unit.pending_rolls else "无"

        stage_text = (
            elite_labels.get(unit.elite_stage, "")
            if self.rule_mode == RuleMode.V1_2 else ""
        )
        lines = [
            f"名称: {unit.name}  [{type_label}]  规则 v{self.rule_mode.value}  {stage_text}",
            f"ID: {unit.unit_id}",
            f"职业: {unit.profession or '未填写'}  分支: {unit.subprofession or '未填写'}  等级: {unit.level}",
            f"血量: {unit.current_hp}/{unit.max_hp}  初始上限: {unit.initial_max_hp}  临时HP: {unit.temp_hp}",
            f"伤残等级: {unit.injury_level()}  SP: {unit.current_sp}/{unit.max_sp}  耐力: {unit.current_stamina}/{unit.max_stamina}",
            f"速度: {unit.speed}  反应机动: {unit.reaction_mobility}  重量: {unit.weight}",
            f"效能骰: {unit.effect_die or '--'}  辅助骰: {unit.auxiliary_die or '--'}",
            f"物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  护甲: {unit.armor_type}",
            f"元素韧性: {unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}",
            f"当前爆发: {burst_info}  待结算骰: {pending_info}",
            f"状态: {status_text}",
        ]
        self.detail_text.setPlainText("\n".join(lines))

    # ============================================================
    # 按钮操作
    # ============================================================

    def _add_unit(self, unit_type: str = "player"):
        from ui.unit_dialog import UnitDialog
        if self.rule_mode == RuleMode.V0_3:
            unit = Unit(
                unit_type=unit_type,
                elemental_tenacity_current=10,
                elemental_tenacity_max=10,
                current_sp=0,
                max_sp=0,
            )
        else:
            unit = Unit(unit_type=unit_type)
        dlg = UnitDialog(unit, self, self.rule_mode)
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
        dlg = UnitDialog(unit, self, self.rule_mode)
        if dlg.exec() == UnitDialog.Accepted and dlg.result:
            self._refresh_tree()
            self._show_detail(dlg.result)
            fade_in(self.detail_text, duration=130, start_opacity=0.76)
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
            self.selection_changed.emit(None)
            self._notify_change()

    def _import_card(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择角色卡文件", "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            from character_card import import_character_card_with_report
            report = import_character_card_with_report(filepath, self.rule_mode)
            unit = report.unit
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
            f"规则: v{report.detected_rule_mode.value}  精英: {unit.elite_stage}"
            + (f"\n提示: {'；'.join(report.warnings)}" if report.warnings else "")
        )

    def _import_quick_text(self):
        dlg = QuickImportDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result_data:
            return
        data = dlg.result_data
        try:
            from character_card import import_from_quick_text
            report = data.get("report")
            if report is None:
                # 向后兼容：没有 report 时自行解析
                report = import_from_quick_text(
                    data["text"],
                    rule_mode=self.rule_mode,
                    name=data.get("name", ""),
                    report=True,
                )
            unit = report.unit
            if data.get("unit_type") and data["unit_type"] != unit.unit_type:
                unit.unit_type = data["unit_type"]
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析文本:\n{e}")
            return

        self.units.append(unit)
        self._refresh_tree()
        self._notify_change()
        type_labels = {"player": "玩家", "monster": "怪物", "ally": "友方"}
        details = "\n".join([
            f"类型: {type_labels.get(unit.unit_type, unit.unit_type)}  "
            f"职业: {unit.profession or '未填写'}  分支: {unit.subprofession or '未填写'}  等级: {unit.level}",
            f"耐力: {unit.current_stamina}/{unit.max_stamina}  护甲: {unit.armor_type}",
        ])
        message = (
            f"已导入角色: {unit.name}\n"
            f"HP: {unit.max_hp}  物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  "
            f"速度: {unit.speed}  重量: {unit.weight}\n"
            + details
            + "\n(精英化等级未包含在快速导入中，默认为0)"
            + (f"\n提示: {'；'.join(report.warnings)}" if report.warnings else "")
        )
        QMessageBox.information(self, "导入成功", message)

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

    def set_rule_mode(self, rule_mode: RuleMode | str):
        self.rule_mode = RuleMode.coerce(rule_mode)
        if hasattr(self, "card_import_action"):
            self.card_import_action.setText(f"v{self.rule_mode.value} 角色卡")
        self._refresh_tree()

    def commit_changes(self):
        """Refresh combat mutations and persist them through the public signal."""
        selected = self.get_selected_unit()
        selected_id = selected.unit_id if selected else None
        self._refresh_tree()
        if selected_id:
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                if getattr(item, "unit_id", None) == selected_id:
                    self.tree.setCurrentItem(item)
                    break
        self._show_detail(self.find_unit(selected_id) if selected_id else None)
        self._notify_change()
        return self.last_persist_ok
