"""TRPG 战斗管理器 - 单位编辑弹窗 (PySide6)"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QSpinBox, QPushButton, QScrollArea, QWidget,
    QCheckBox, QLabel, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt
from models import Unit, POSITIVE_BUFFS, NEGATIVE_BUFFS


class UnitDialog(QDialog):
    Accepted = QDialog.Accepted

    def __init__(self, unit: Unit, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.result: Unit | None = None
        self.is_edit = True

        title = "编辑单位" if unit.name else "添加单位"
        self.setWindowTitle(title)
        self.setMinimumSize(460, 580)
        self.setMaximumSize(500, 720)

        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)

        # 基本信息
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("名称", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["player", "monster"])
        form.addRow("类型", self.type_combo)
        layout.addLayout(form)
        layout.addWidget(_sep())

        # 血量
        form2 = QFormLayout()
        self.current_hp_spin = QSpinBox()
        self.current_hp_spin.setRange(0, 9999)
        form2.addRow("当前血量", self.current_hp_spin)

        self.max_hp_spin = QSpinBox()
        self.max_hp_spin.setRange(1, 9999)
        form2.addRow("最大血量", self.max_hp_spin)

        self.temp_hp_spin = QSpinBox()
        self.temp_hp_spin.setRange(0, 9999)
        form2.addRow("临时HP", self.temp_hp_spin)
        layout.addLayout(form2)
        layout.addWidget(_sep())

        # 战斗属性
        form3 = QFormLayout()
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 99)
        form3.addRow("速度", self.speed_spin)

        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(-99, 99)
        form3.addRow("重量", self.weight_spin)

        self.phys_res_spin = QSpinBox()
        self.phys_res_spin.setRange(-99, 99)
        form3.addRow("物理抗性", self.phys_res_spin)

        self.magic_res_spin = QSpinBox()
        self.magic_res_spin.setRange(-99, 99)
        form3.addRow("法术抗性", self.magic_res_spin)

        self.armor_combo = QComboBox()
        self.armor_combo.addItems(["轻甲", "中甲", "重甲", "无甲"])
        form3.addRow("护甲类型", self.armor_combo)
        layout.addLayout(form3)
        layout.addWidget(_sep())

        # 元素韧性
        form4 = QFormLayout()
        self.elite_combo = QComboBox()
        self.elite_combo.addItems(["0", "1", "2"])
        form4.addRow("精英化阶段", self.elite_combo)

        self.tenacity_cur_spin = QSpinBox()
        self.tenacity_cur_spin.setRange(0, 99)
        form4.addRow("元素韧性(当前)", self.tenacity_cur_spin)

        self.tenacity_max_spin = QSpinBox()
        self.tenacity_max_spin.setRange(0, 99)
        form4.addRow("元素韧性(上限)", self.tenacity_max_spin)
        layout.addLayout(form4)
        layout.addWidget(_sep())

        # BUFF 区域
        self.buff_toggle = QPushButton("+ 展开正面/负面 BUFF")
        self.buff_toggle.setCheckable(True)
        self.buff_toggle.toggled.connect(self._toggle_buffs)
        layout.addWidget(self.buff_toggle)

        self.buff_container = QWidget()
        buff_layout = QVBoxLayout(self.buff_container)
        buff_layout.setContentsMargins(0, 0, 0, 0)

        buff_layout.addWidget(QLabel("正面BUFF"))
        pos_grid = QHBoxLayout()
        self.positive_vars: dict[str, QCheckBox] = {}
        for s in POSITIVE_BUFFS:
            cb = QCheckBox(s)
            self.positive_vars[s] = cb
            pos_grid.addWidget(cb)
        buff_layout.addLayout(pos_grid)

        buff_layout.addWidget(QLabel("负面BUFF / 状态"))
        neg_grid = QHBoxLayout()
        self.negative_vars: dict[str, QCheckBox] = {}
        for s in NEGATIVE_BUFFS:
            cb = QCheckBox(s)
            self.negative_vars[s] = cb
            neg_grid.addWidget(cb)
        buff_layout.addLayout(neg_grid)

        self.buff_container.setVisible(False)
        layout.addWidget(self.buff_container)

        # 保存/取消
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._load_unit_data()

    def _toggle_buffs(self, checked):
        self.buff_container.setVisible(checked)

    def _load_unit_data(self):
        u = self.unit
        self.name_edit.setText(u.name)
        self.type_combo.setCurrentText(u.unit_type)
        self.current_hp_spin.setValue(u.current_hp)
        self.max_hp_spin.setValue(u.max_hp)
        self.temp_hp_spin.setValue(u.temp_hp)
        self.speed_spin.setValue(u.speed)
        self.weight_spin.setValue(u.weight)
        self.phys_res_spin.setValue(u.physical_resist)
        self.magic_res_spin.setValue(u.magic_resist)
        self.armor_combo.setCurrentText(u.armor_type)
        self.elite_combo.setCurrentText(str(u.elite_stage))
        self.tenacity_cur_spin.setValue(u.elemental_tenacity_current)
        self.tenacity_max_spin.setValue(u.elemental_tenacity_max)

        for s in POSITIVE_BUFFS:
            self.positive_vars[s].setChecked(u.has_status(s))
        for s in NEGATIVE_BUFFS:
            self.negative_vars[s].setChecked(u.has_status(s))

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "请输入单位名称")
            return
        if self.current_hp_spin.value() < 0 or self.max_hp_spin.value() <= 0:
            QMessageBox.warning(self, "验证失败", "血量设置不合法")
            return

        self.unit.name = name
        self.unit.unit_type = self.type_combo.currentText()
        self.unit.current_hp = self.current_hp_spin.value()
        self.unit.max_hp = self.max_hp_spin.value()
        self.unit.temp_hp = self.temp_hp_spin.value()
        self.unit.speed = self.speed_spin.value()
        self.unit.weight = self.weight_spin.value()
        self.unit.physical_resist = self.phys_res_spin.value()
        self.unit.magic_resist = self.magic_res_spin.value()
        self.unit.armor_type = self.armor_combo.currentText()
        self.unit.elite_stage = int(self.elite_combo.currentText())
        self.unit.elemental_tenacity_current = self.tenacity_cur_spin.value()
        self.unit.elemental_tenacity_max = self.tenacity_max_spin.value()

        # 更新状态
        new_effects = []
        for s in POSITIVE_BUFFS + NEGATIVE_BUFFS:
            cb = self.positive_vars.get(s) or self.negative_vars.get(s)
            if cb and cb.isChecked():
                existing = self.unit.get_status(s)
                stacks = existing["stacks"] if existing else 0
                new_effects.append({"name": s, "stacks": stacks})
        self.unit.status_effects = new_effects

        self.result = self.unit
        self.accept()


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f
