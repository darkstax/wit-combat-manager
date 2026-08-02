"""TRPG 战斗管理器 - 单位编辑弹窗 (PySide6)"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QSpinBox, QPushButton, QScrollArea, QWidget,
    QCheckBox, QLabel, QMessageBox, QGroupBox, QGridLayout,
    QDialogButtonBox,
)
from models import (
    Unit, RuleMode, POSITIVE_BUFFS, NEGATIVE_BUFFS,
    V03_POSITIVE_BUFFS, V03_NEGATIVE_BUFFS,
    ELITE_TENACITY, X_STATUSES, x_statuses_for,
)
from ui.fluent import set_button_role


class UnitDialog(QDialog):
    Accepted = QDialog.Accepted

    def __init__(
        self,
        unit: Unit,
        parent=None,
        rule_mode: RuleMode | str = RuleMode.V1_2,
    ):
        super().__init__(parent)
        self.unit = unit
        self.rule_mode = RuleMode.coerce(rule_mode)
        self.positive_statuses = (
            V03_POSITIVE_BUFFS if self.rule_mode == RuleMode.V0_3 else POSITIVE_BUFFS
        )
        self.negative_statuses = (
            V03_NEGATIVE_BUFFS if self.rule_mode == RuleMode.V0_3 else NEGATIVE_BUFFS
        )
        self.result: Unit | None = None
        self.is_edit = True
        self._loading = False

        title = "编辑单位" if unit.name else "添加单位"
        self.setWindowTitle(title)
        self.setMinimumSize(580, 650)
        self.resize(620, 760)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        page_title = QLabel(title)
        page_title.setObjectName("PageTitle")
        outer.addWidget(page_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        basic_group = QGroupBox("基本信息")
        form = QFormLayout(basic_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("单位名称")
        form.addRow("名称", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem("玩家", "player")
        self.type_combo.addItem("怪物", "monster")
        form.addRow("类型", self.type_combo)

        self.profession_edit = QLineEdit()
        form.addRow("职业", self.profession_edit)
        self.subprofession_edit = QLineEdit()
        form.addRow("分支", self.subprofession_edit)
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 999)
        form.addRow("等级", self.level_spin)
        layout.addWidget(basic_group)

        hp_group = QGroupBox("生命值")
        form2 = QFormLayout(hp_group)
        form2.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.current_hp_spin = QSpinBox()
        self.current_hp_spin.setRange(0, 9999)
        form2.addRow("当前血量", self.current_hp_spin)

        self.max_hp_spin = QSpinBox()
        self.max_hp_spin.setRange(0, 9999)
        form2.addRow("当前生命上限", self.max_hp_spin)

        self.initial_max_hp_spin = QSpinBox()
        self.initial_max_hp_spin.setRange(1, 9999)
        form2.addRow("初始生命上限", self.initial_max_hp_spin)

        self.temp_hp_spin = QSpinBox()
        self.temp_hp_spin.setRange(0, 9999)
        form2.addRow("临时HP", self.temp_hp_spin)
        layout.addWidget(hp_group)

        combat_group = QGroupBox("战斗属性")
        form3 = QFormLayout(combat_group)
        form3.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 99)
        form3.addRow("速度", self.speed_spin)

        self.reaction_mobility_spin = QSpinBox()
        self.reaction_mobility_spin.setRange(0, 999)
        form3.addRow("反应机动", self.reaction_mobility_spin)

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
        layout.addWidget(combat_group)

        resource_group = QGroupBox("行动资源")
        resource_form = QFormLayout(resource_group)
        resource_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.current_sp_spin = QSpinBox()
        self.current_sp_spin.setRange(0, 999)
        resource_form.addRow("当前 SP", self.current_sp_spin)
        self.max_sp_spin = QSpinBox()
        self.max_sp_spin.setRange(0, 999)
        resource_form.addRow("SP 上限", self.max_sp_spin)
        self.current_stamina_spin = QSpinBox()
        self.current_stamina_spin.setRange(0, 999)
        resource_form.addRow("当前耐力", self.current_stamina_spin)
        self.max_stamina_spin = QSpinBox()
        self.max_stamina_spin.setRange(0, 999)
        resource_form.addRow("耐力上限", self.max_stamina_spin)
        self.effect_die_edit = QLineEdit()
        self.effect_die_edit.setPlaceholderText("例如 D+ 或 2d6")
        resource_form.addRow("效能骰", self.effect_die_edit)
        self.auxiliary_die_edit = QLineEdit()
        self.auxiliary_die_edit.setPlaceholderText("例如 D2 或 d8")
        resource_form.addRow("辅助骰", self.auxiliary_die_edit)
        layout.addWidget(resource_group)

        element_group = QGroupBox("元素韧性")
        form4 = QFormLayout(element_group)
        form4.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.elite_combo = QComboBox()
        self.elite_combo.addItem("精零", 0)
        self.elite_combo.addItem("精一", 1)
        self.elite_combo.addItem("精二", 2)
        self.elite_combo.currentIndexChanged.connect(self._on_elite_changed)
        self.elite_label = QLabel("精英化阶段")
        form4.addRow(self.elite_label, self.elite_combo)

        self.tenacity_cur_spin = QSpinBox()
        self.tenacity_cur_spin.setRange(0, 99)
        form4.addRow("元素韧性(当前)", self.tenacity_cur_spin)

        self.tenacity_max_spin = QSpinBox()
        self.tenacity_max_spin.setRange(0, 99)
        form4.addRow("元素韧性(上限)", self.tenacity_max_spin)
        layout.addWidget(element_group)

        self.buff_toggle = QPushButton("展开状态与 BUFF")
        self.buff_toggle.setCheckable(True)
        self.buff_toggle.toggled.connect(self._toggle_buffs)
        layout.addWidget(self.buff_toggle)

        self.buff_container = QGroupBox("状态与 BUFF")
        buff_layout = QVBoxLayout(self.buff_container)
        buff_layout.setSpacing(8)

        buff_layout.addWidget(QLabel("正面BUFF"))
        pos_grid = QGridLayout()
        pos_grid.setHorizontalSpacing(12)
        self.positive_vars: dict[str, QCheckBox] = {}
        for index, s in enumerate(self.positive_statuses):
            cb = QCheckBox(s)
            self.positive_vars[s] = cb
            pos_grid.addWidget(cb, index // 3, index % 3)
        buff_layout.addLayout(pos_grid)

        buff_layout.addWidget(QLabel("负面BUFF / 状态"))
        neg_grid = QGridLayout()
        neg_grid.setHorizontalSpacing(12)
        self.negative_vars: dict[str, QCheckBox] = {}
        for index, s in enumerate(self.negative_statuses):
            cb = QCheckBox(s)
            self.negative_vars[s] = cb
            neg_grid.addWidget(cb, index // 3, index % 3)
        buff_layout.addLayout(neg_grid)

        self.buff_container.setVisible(False)
        layout.addWidget(self.buff_container)
        layout.addStretch()

        is_v03 = self.rule_mode == RuleMode.V0_3
        self.elite_label.setVisible(not is_v03)
        self.elite_combo.setVisible(not is_v03)

        buttons = QDialogButtonBox()
        save_btn = QPushButton("保存")
        set_button_role(save_btn, "primary")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        outer.addWidget(buttons)

        self._load_unit_data()

    def _toggle_buffs(self, checked):
        self.buff_container.setVisible(checked)
        self.buff_toggle.setText("收起状态与 BUFF" if checked else "展开状态与 BUFF")

    def _load_unit_data(self):
        self._loading = True
        u = self.unit
        self.name_edit.setText(u.name)
        self.profession_edit.setText(u.profession)
        self.subprofession_edit.setText(u.subprofession)
        self.level_spin.setValue(u.level)
        type_index = self.type_combo.findData(u.unit_type)
        self.type_combo.setCurrentIndex(max(0, type_index))
        self.current_hp_spin.setValue(u.current_hp)
        self.max_hp_spin.setValue(u.max_hp)
        self.initial_max_hp_spin.setValue(u.initial_max_hp)
        self.temp_hp_spin.setValue(u.temp_hp)
        self.current_sp_spin.setValue(u.current_sp)
        self.max_sp_spin.setValue(u.max_sp)
        self.current_stamina_spin.setValue(u.current_stamina)
        self.max_stamina_spin.setValue(u.max_stamina)
        self.effect_die_edit.setText(u.effect_die)
        self.auxiliary_die_edit.setText(u.auxiliary_die)
        self.speed_spin.setValue(u.speed)
        self.reaction_mobility_spin.setValue(u.reaction_mobility)
        self.weight_spin.setValue(u.weight)
        self.phys_res_spin.setValue(u.physical_resist)
        self.magic_res_spin.setValue(u.magic_resist)
        self.armor_combo.setCurrentText(u.armor_type)
        elite_index = self.elite_combo.findData(u.elite_stage)
        self.elite_combo.setCurrentIndex(max(0, elite_index))
        self.tenacity_cur_spin.setValue(u.elemental_tenacity_current)
        self.tenacity_max_spin.setValue(u.elemental_tenacity_max)

        for s in self.positive_statuses:
            self.positive_vars[s].setChecked(u.has_status(s))
        for s in self.negative_statuses:
            self.negative_vars[s].setChecked(u.has_status(s))
        self._loading = False

    def _on_elite_changed(self, index):
        """精英阶段变化时，若韧性上限为旧标准值则自动同步到新标准值"""
        if self._loading:
            return
        if self.rule_mode == RuleMode.V0_3:
            return
        elite = self.elite_combo.itemData(index)
        if elite in ELITE_TENACITY and self.tenacity_max_spin.value() in ELITE_TENACITY.values():
            standard = ELITE_TENACITY[elite]
            self.tenacity_max_spin.setValue(standard)
            self.tenacity_cur_spin.setValue(standard)
        if elite in ELITE_TENACITY and self.max_sp_spin.value() in (9, 12, 15):
            standard_sp = 9 + 3 * elite
            self.max_sp_spin.setValue(standard_sp)
            self.current_sp_spin.setValue(min(self.current_sp_spin.value(), standard_sp))

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "请输入单位名称")
            return
        if (self.current_hp_spin.value() < 0 or self.max_hp_spin.value() < 0
                or self.current_hp_spin.value() > self.max_hp_spin.value()):
            QMessageBox.warning(self, "验证失败", "血量设置不合法（当前HP不能超过最大HP）")
            return
        if self.current_sp_spin.value() > self.max_sp_spin.value():
            QMessageBox.warning(self, "验证失败", "当前 SP 不能超过 SP 上限")
            return
        if self.current_stamina_spin.value() > self.max_stamina_spin.value():
            QMessageBox.warning(self, "验证失败", "当前耐力不能超过耐力上限")
            return

        self.unit.name = name
        self.unit.unit_type = self.type_combo.currentData()
        self.unit.profession = self.profession_edit.text().strip()
        self.unit.subprofession = self.subprofession_edit.text().strip()
        self.unit.level = self.level_spin.value()
        self.unit.current_hp = self.current_hp_spin.value()
        self.unit.max_hp = self.max_hp_spin.value()
        self.unit.initial_max_hp = self.initial_max_hp_spin.value()
        self.unit.temp_hp = self.temp_hp_spin.value()
        self.unit.current_sp = self.current_sp_spin.value()
        self.unit.max_sp = self.max_sp_spin.value()
        self.unit.current_stamina = self.current_stamina_spin.value()
        self.unit.max_stamina = self.max_stamina_spin.value()
        self.unit.effect_die = self.effect_die_edit.text().strip()
        self.unit.auxiliary_die = self.auxiliary_die_edit.text().strip()
        self.unit.speed = self.speed_spin.value()
        self.unit.reaction_mobility = self.reaction_mobility_spin.value()
        self.unit.weight = self.weight_spin.value()
        self.unit.physical_resist = self.phys_res_spin.value()
        self.unit.magic_resist = self.magic_res_spin.value()
        self.unit.armor_type = self.armor_combo.currentText()
        self.unit.elite_stage = self.elite_combo.currentData()
        self.unit.elemental_tenacity_current = self.tenacity_cur_spin.value()
        self.unit.elemental_tenacity_max = self.tenacity_max_spin.value()

        # 更新状态
        new_effects = []
        for s in self.positive_statuses + self.negative_statuses:
            cb = self.positive_vars.get(s) or self.negative_vars.get(s)
            if cb and cb.isChecked():
                existing = self.unit.get_status(s)
                if existing:
                    new_effects.append(dict(existing))
                else:
                    new_effects.append({
                        "name": s,
                        "stacks": 1 if s in x_statuses_for(self.rule_mode) else 0,
                    })
        self.unit.status_effects = new_effects
        if self.unit.has_status("濒死"):
            self.unit.current_hp = 0

        self.result = self.unit
        self.accept()
