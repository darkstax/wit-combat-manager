"""TRPG 战斗管理器 - 战斗控制面板 (PySide6)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QListWidgetItem,
    QDialog, QFormLayout,
    QScrollArea, QSplitter,
    QAbstractItemView, QLayout, QSizePolicy,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, ComboBox, SpinBox, DoubleSpinBox,
    CheckBox, TabWidget, ListWidget, CardWidget, ToolButton, LineEdit,
    TabCloseButtonDisplayMode,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QIntValidator
from models import (
    Unit, CombatState, RuleMode, ALL_STATUS_NAMES,
    X_STATUSES, ELEMENT_TYPES, STATUS_DEFINITIONS, THEME,
    UNIT_TYPE_LABELS,
    element_types_for, status_names_for, x_statuses_for,
)
from combat import (
    team_initiative, traditional_initiative, manual_initiative, ranked_initiative,
    apply_damage, apply_healing, apply_elemental_damage,
    resolve_pending_elemental_burst,
    apply_status, clear_all_statuses, next_actor, advance_turn,
)
from persistence import save_combat_state, load_combat_state, delete_combat_state
from ui.fluent import (
    install_tab_fade, pulse, section_label, danger_button,
    info_box, warn_box, question_box, EmptyStateLabel,
)


class InitiativeRollDialog(QDialog):
    """Collect player-entered reaction/mobility check results."""

    def __init__(
        self,
        units: list[Unit],
        rule_mode: RuleMode | str = RuleMode.V1_2,
        parent=None,
    ):
        super().__init__(parent)
        self.rule_mode = RuleMode.coerce(rule_mode)
        self.setWindowTitle(
            "录入同速对抗 d100" if self.rule_mode == RuleMode.V0_3
            else "录入反应机动检定"
        )
        self.setMinimumSize(480, 420)
        self.result_values: dict[str, int] | None = None
        self._edits: dict[str, LineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel(
            "同速对抗 d100" if self.rule_mode == RuleMode.V0_3
            else "反应机动检定"
        )
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(12, 12, 12, 12)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for unit in units:
            edit = LineEdit()
            if self.rule_mode == RuleMode.V0_3:
                edit.setValidator(QIntValidator(1, 100, edit))
                edit.setPlaceholderText("1-100")
            else:
                edit.setValidator(QIntValidator(0, 9999, edit))
                edit.setPlaceholderText("必填")
            type_name = UNIT_TYPE_LABELS.get(unit.unit_type, unit.unit_type)
            form.addRow(f"{unit.name}  ·  {type_name}", edit)
            self._edits[unit.unit_id] = edit
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        confirm_btn = PrimaryPushButton("确认并开始")
        cancel_btn = PushButton("取消")
        buttons.addWidget(confirm_btn)
        buttons.addWidget(cancel_btn)
        confirm_btn.clicked.connect(self._accept_values)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(buttons)

        if self._edits:
            next(iter(self._edits.values())).setFocus()

    def _accept_values(self):
        values = {}
        for unit_id, edit in self._edits.items():
            text = edit.text().strip()
            if not text:
                edit.setFocus()
                warn_box(self, "检定未填写", "请填写每个单位的反应机动检定结果")
                return
            values[unit_id] = int(text)
        self.result_values = values
        self.accept()


class CombatPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rule_mode = RuleMode.V1_2
        self.combat_state: CombatState | None = None
        self.unit_provider = None
        self.selected_target: Unit | None = None
        self.operation_buttons: list[PushButton] = []
        self._refreshing_order = False
        self._log_callback = print  # 默认直接 print，连接后走主窗口日志
        self._work_splitter: QSplitter | None = None
        self._pre_expand_sizes: list[int] | None = None  # 展开前分栏真实分配快照

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        # ---- 先攻与战斗命令栏 ----
        command_panel = CardWidget()
        command_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        command_layout = QGridLayout(command_panel)
        command_layout.setContentsMargins(10, 10, 10, 10)
        command_layout.setHorizontalSpacing(6)
        command_layout.setVerticalSpacing(8)

        command_layout.addWidget(QLabel("先攻"), 0, 0)
        self.init_mode_combo = ComboBox()
        self.init_mode_combo.addItem("传统先攻", userData="traditional")
        self.init_mode_combo.addItem("团队先攻", userData="team")
        self.init_mode_combo.addItem("客观判断", userData="manual")
        self.init_mode_combo.addItem("指定顺位", userData="ranked")
        self.init_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.init_mode_combo.setMinimumWidth(112)
        command_layout.addWidget(self.init_mode_combo, 0, 1)

        self._manual_row = QHBoxLayout()
        self._manual_row.setContentsMargins(0, 0, 0, 0)
        self._manual_row.addWidget(QLabel("先动阵营"))
        self.manual_team_combo = ComboBox()
        self.manual_team_combo.addItem("玩家", userData="player")
        self.manual_team_combo.addItem("怪物", userData="monster")
        self._manual_row.addWidget(self.manual_team_combo)
        manual_container = QWidget()
        manual_container.setLayout(self._manual_row)
        command_layout.addWidget(manual_container, 0, 2)

        self._dice_row = QHBoxLayout()
        self._dice_row.setContentsMargins(0, 0, 0, 0)
        traditional_label = QLabel("录入反应机动")
        traditional_label.setToolTip("开始战斗时逐单位填写反应机动检定结果")
        traditional_label.setObjectName("SecondaryText")
        self._dice_row.addWidget(traditional_label)
        dice_container = QWidget()
        dice_container.setLayout(self._dice_row)
        command_layout.addWidget(dice_container, 0, 2)

        self._on_mode_changed(0)
        self.turn_label = QLabel("轮次 0")
        self.turn_label.setObjectName("StatusBadge")
        command_layout.addWidget(self.turn_label, 0, 4)
        self.now_label = QLabel("当前行动 --")
        self.now_label.setObjectName("StatusBadge")
        command_layout.addWidget(self.now_label, 0, 5)
        self.team_score_label = QLabel("")
        self.team_score_label.setObjectName("SecondaryText")
        self.team_score_label.setWordWrap(True)
        self.team_score_label.setVisible(False)
        command_layout.addWidget(self.team_score_label, 2, 0, 1, 8)

        # ---- 战斗控制按钮 ----
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.start_btn = PrimaryPushButton("开始战斗")
        self.start_btn.clicked.connect(self._start_combat)
        action_row.addWidget(self.start_btn, 1)

        self.next_btn = PushButton("下一行动")
        self.next_btn.clicked.connect(self._next_action)
        self.next_btn.setEnabled(False)
        action_row.addWidget(self.next_btn, 1)

        self.end_turn_btn = PushButton("强制下一轮")
        self.end_turn_btn.clicked.connect(self._end_turn)
        self.end_turn_btn.setEnabled(False)
        action_row.addWidget(self.end_turn_btn, 1)

        self.end_combat_btn = danger_button("结束战斗")
        self.end_combat_btn.clicked.connect(self._end_combat)
        self.end_combat_btn.setEnabled(False)
        action_row.addWidget(self.end_combat_btn, 1)
        command_layout.addLayout(action_row, 1, 0, 1, 8)
        command_layout.setColumnStretch(3, 1)
        layout.addWidget(command_panel)

        # ---- 战斗操作 ----
        layout.addWidget(section_label("计算操作"))
        target_context = CardWidget()
        target_layout = QHBoxLayout(target_context)
        target_layout.setContentsMargins(10, 6, 10, 6)
        target_layout.setSpacing(8)
        target_layout.addWidget(QLabel("目标"))
        self.target_context_label = QLabel("未选择单位")
        self.target_context_label.setObjectName("SecondaryText")
        target_layout.addWidget(self.target_context_label, 1)
        layout.addWidget(target_context)

        self.operations_tabs = TabWidget()
        self.operations_tabs.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self.operations_tabs.tabBar.setAddButtonVisible(False)
        self._ops_tabs_base_height = 164
        self.operations_tabs.setMinimumHeight(self._ops_tabs_base_height)

        damage_tab = QWidget()
        damage_layout = QVBoxLayout(damage_tab)
        damage_layout.setContentsMargins(14, 12, 14, 14)
        damage_layout.setSpacing(8)
        damage_grid = QGridLayout()
        damage_grid.setHorizontalSpacing(12)
        damage_grid.setVerticalSpacing(6)
        self.damage_amount_label = QLabel("攻击检定 / 折前伤害")
        self.damage_amount_label.setToolTip("填写攻击检定骰值或抗性折减前的伤害")
        damage_grid.addWidget(self.damage_amount_label, 0, 0)
        self.dmg_amount_spin = SpinBox()
        self.dmg_amount_spin.setRange(1, 9999)
        self.dmg_amount_spin.setValue(5)
        self.dmg_amount_spin.setMaximumWidth(240)
        damage_grid.addWidget(self.dmg_amount_spin, 1, 0)
        damage_grid.addWidget(QLabel("伤害类型"), 0, 1)
        self.dmg_type_combo = ComboBox()
        self.dmg_type_combo.addItems(["物理", "法术", "真实", "治疗"])
        self.dmg_type_combo.setMaximumWidth(240)
        damage_grid.addWidget(self.dmg_type_combo, 1, 1)
        self.final_damage_cb = CheckBox("忽略抗性")
        self.final_damage_cb.setToolTip("直接按输入值结算，不再扣减目标抗性")
        self.is_attack_cb = CheckBox("按攻击规则")
        self.is_attack_cb.setToolTip(
            "启用命中、护盾、攻击者增益与攻击后状态；"
            "持续伤害、环境伤害等直接伤害请关闭"
        )
        self.is_attack_cb.setChecked(True)
        self.is_attack_cb.toggled.connect(
            lambda _checked: self._on_damage_type_changed(
                self.dmg_type_combo.currentText()
            )
        )
        apply_dmg_btn = PrimaryPushButton("施加")
        apply_dmg_btn.setMinimumWidth(84)
        apply_dmg_btn.clicked.connect(self._apply_damage)
        damage_grid.addWidget(apply_dmg_btn, 1, 2, 1, 1)
        self.operation_buttons.append(apply_dmg_btn)
        damage_grid.setColumnStretch(0, 2)
        damage_grid.setColumnStretch(1, 2)
        damage_grid.setColumnStretch(2, 1)
        damage_layout.addLayout(damage_grid)

        self.damage_modifiers_toggle = ToolButton()
        self.damage_modifiers_toggle.setText("修正")
        self.damage_modifiers_toggle.setCheckable(True)
        self.damage_modifiers_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.damage_modifiers_toggle.setArrowType(Qt.RightArrow)
        self.damage_modifiers_toggle.toggled.connect(self._set_damage_modifiers_visible)
        damage_layout.addWidget(self.damage_modifiers_toggle, 0, Qt.AlignLeft)

        self.damage_modifiers = QWidget()
        modifier_grid = QGridLayout(self.damage_modifiers)
        modifier_grid.setContentsMargins(0, 0, 0, 0)
        modifier_grid.setHorizontalSpacing(12)
        modifier_grid.setVerticalSpacing(8)
        self.aux_damage_cb = CheckBox("加入辅助骰伤害")
        modifier_grid.addWidget(self.aux_damage_cb, 1, 0)
        self.aux_damage_spin = SpinBox()
        self.aux_damage_spin.setRange(0, 9999)
        self.aux_damage_spin.setMaximumWidth(240)
        self.aux_damage_spin.setEnabled(False)
        self.aux_damage_cb.toggled.connect(self.aux_damage_spin.setEnabled)
        modifier_grid.addWidget(self.aux_damage_spin, 1, 1)
        self.half_damage_cb = CheckBox("伤害减半")
        self.half_damage_cb.setToolTip("最终结算伤害乘以 50%")
        modifier_grid.addWidget(self.half_damage_cb, 0, 2)
        modifier_grid.addWidget(self.is_attack_cb, 0, 0)
        modifier_grid.addWidget(self.final_damage_cb, 0, 1)

        self.v03_attack_label = QLabel("命中 d100 / 成功率")
        modifier_grid.addWidget(self.v03_attack_label, 2, 0)
        self.v03_attack_roll_spin = SpinBox()
        self.v03_attack_roll_spin.setRange(1, 100)
        modifier_grid.addWidget(self.v03_attack_roll_spin, 2, 1)
        self.v03_success_rate_spin = SpinBox()
        self.v03_success_rate_spin.setRange(0, 100)
        self.v03_success_rate_spin.setValue(50)
        modifier_grid.addWidget(self.v03_success_rate_spin, 2, 2)
        self.v03_dying_save_combo = ComboBox()
        self.v03_dying_save_combo.addItem("濒死检定：暂不结算", userData=None)
        self.v03_dying_save_combo.addItem("濒死检定：成功", userData=True)
        self.v03_dying_save_combo.addItem("濒死检定：失败", userData=False)
        modifier_grid.addWidget(self.v03_dying_save_combo, 3, 0, 1, 3)
        self.v03_formula_label = QLabel("常规倍率 / 最终常数")
        modifier_grid.addWidget(self.v03_formula_label, 4, 0)
        self.v03_normal_multiplier_spin = DoubleSpinBox()
        self.v03_normal_multiplier_spin.setRange(0.0, 99.0)
        self.v03_normal_multiplier_spin.setDecimals(2)
        self.v03_normal_multiplier_spin.setSingleStep(0.1)
        self.v03_normal_multiplier_spin.setValue(1.0)
        modifier_grid.addWidget(self.v03_normal_multiplier_spin, 4, 1)
        self.v03_final_constant_spin = SpinBox()
        self.v03_final_constant_spin.setRange(-9999, 9999)
        modifier_grid.addWidget(self.v03_final_constant_spin, 4, 2)
        self.dmg_type_combo.currentTextChanged.connect(self._on_damage_type_changed)
        self._on_damage_type_changed(self.dmg_type_combo.currentText())
        modifier_grid.setColumnStretch(0, 2)
        modifier_grid.setColumnStretch(1, 2)
        modifier_grid.setColumnStretch(2, 1)
        self.damage_modifiers.setVisible(False)
        damage_layout.addWidget(self.damage_modifiers)
        self.operations_tabs.addTab(damage_tab, "伤害")

        element_tab = QWidget()
        element_grid = QGridLayout(element_tab)
        element_grid.setContentsMargins(14, 12, 14, 14)
        element_grid.setHorizontalSpacing(12)
        element_grid.setVerticalSpacing(10)
        element_grid.addWidget(QLabel("数值"), 0, 0)
        self.elem_amount_spin = SpinBox()
        self.elem_amount_spin.setRange(1, 999)
        self.elem_amount_spin.setValue(2)
        element_grid.addWidget(self.elem_amount_spin, 0, 1)
        element_grid.addWidget(QLabel("类型"), 0, 2)
        self.elem_type_combo = ComboBox()
        self.elem_type_combo.addItems(ELEMENT_TYPES)
        element_grid.addWidget(self.elem_type_combo, 0, 3)
        apply_elem_btn = PrimaryPushButton("施加")
        apply_elem_btn.clicked.connect(self._apply_elem_dmg)
        element_grid.addWidget(apply_elem_btn, 0, 4)
        self.operation_buttons.append(apply_elem_btn)
        element_grid.setColumnStretch(5, 1)

        self.burst_roll_cb = CheckBox("同时填写爆发骰")
        element_grid.addWidget(self.burst_roll_cb, 1, 0, 1, 2)
        self.burst_roll_label = QLabel("单次骰值")
        element_grid.addWidget(self.burst_roll_label, 1, 2)
        self.burst_roll_spin = SpinBox()
        self.burst_roll_spin.setRange(0, 9999)
        self.burst_roll_spin.setEnabled(False)
        self.burst_roll_cb.toggled.connect(self.burst_roll_spin.setEnabled)
        element_grid.addWidget(self.burst_roll_spin, 1, 3)
        self.resolve_burst_btn = PushButton("补结待处理爆发")
        self.resolve_burst_btn.setEnabled(False)
        self.burst_roll_cb.toggled.connect(lambda _checked: self._update_operation_actions())
        self.resolve_burst_btn.clicked.connect(self._resolve_pending_burst)
        element_grid.addWidget(self.resolve_burst_btn, 1, 4)
        self.operation_buttons.append(self.resolve_burst_btn)
        self.element_resistance_label = QLabel("元素抗性")
        element_grid.addWidget(self.element_resistance_label, 2, 0)
        self.element_resistance_spin = SpinBox()
        self.element_resistance_spin.setRange(0, 9999)
        element_grid.addWidget(self.element_resistance_spin, 2, 1)
        self.operations_tabs.addTab(element_tab, "元素损伤")

        status_tab = QWidget()
        status_grid = QGridLayout(status_tab)
        status_grid.setContentsMargins(14, 12, 14, 14)
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(10)
        status_grid.addWidget(QLabel("状态"), 0, 0)
        self.status_combo = ComboBox()
        self.status_combo.addItems(ALL_STATUS_NAMES)
        status_grid.addWidget(self.status_combo, 0, 1)
        self.x_label = QLabel("X")
        self.x_spin = SpinBox()
        self.x_spin.setRange(0, 99)
        status_grid.addWidget(self.x_label, 0, 2)
        status_grid.addWidget(self.x_spin, 0, 3)
        apply_status_btn = PrimaryPushButton("施加")
        apply_status_btn.clicked.connect(self._apply_status)
        status_grid.addWidget(apply_status_btn, 0, 4)
        self.operation_buttons.append(apply_status_btn)
        clear_status_btn = danger_button("清除全部")
        clear_status_btn.clicked.connect(self._clear_current_status)
        status_grid.addWidget(clear_status_btn, 0, 5)
        self.operation_buttons.append(clear_status_btn)
        self.use_resistance_cb = CheckBox("允许目标消耗抵抗")
        self.use_resistance_cb.setChecked(True)
        status_grid.addWidget(self.use_resistance_cb, 1, 0, 1, 2)
        self.save_succeeded_cb = CheckBox("豁免检定成功")
        status_grid.addWidget(self.save_succeeded_cb, 1, 2, 1, 2)
        status_grid.setColumnStretch(6, 1)

        self.status_combo.currentTextChanged.connect(self._on_status_selected)
        self._on_status_selected(self.status_combo.currentText())
        self.operations_tabs.addTab(status_tab, "状态")
        install_tab_fade(self.operations_tabs)
        layout.addWidget(self.operations_tabs)

        # ---- 行动顺序 ----
        self.order_heading = section_label("行动顺序")
        layout.addWidget(self.order_heading)
        self.order_list = ListWidget()
        self.order_list.setAlternatingRowColors(True)
        self.order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.order_list.setDefaultDropAction(Qt.MoveAction)
        self.order_list.model().rowsMoved.connect(
            lambda *_: QTimer.singleShot(0, self._sync_order_from_list)
        )
        self.order_placeholder = EmptyStateLabel(self.order_list.viewport())
        self.order_placeholder.set_text("暂无行动顺序。添加单位后开始战斗。")
        self.order_placeholder.hide()
        layout.addWidget(self.order_list, 1)
        self.set_rule_mode(self.rule_mode)
        self._update_operation_actions()

    # ============================================================
    # 接口
    # ============================================================

    def attach_splitter(self, splitter: QSplitter):
        """关联外层垂直分栏，展开“修正”时主动重排，让下方日志区让位。"""
        self._work_splitter = splitter

    def set_unit_provider(self, panel):
        self.unit_provider = panel
        self.set_selected_target(panel.get_selected_unit())

    def set_selected_target(self, unit: Unit | None):
        self.selected_target = unit
        if unit is None:
            self.target_context_label.setText("未选择单位")
        else:
            unit_type = UNIT_TYPE_LABELS.get(unit.unit_type, unit.unit_type)
            self.target_context_label.setText(
                f"{unit.name} · {unit_type} · HP {unit.current_hp}/{unit.max_hp}"
            )
        self._update_operation_actions()

    def _update_operation_actions(self):
        has_target = self.selected_target is not None
        for button in self.operation_buttons:
            if button is self.resolve_burst_btn:
                button.setEnabled(has_target and self.burst_roll_cb.isChecked())
            else:
                button.setEnabled(has_target)

    def _set_damage_modifiers_visible(self, visible: bool):
        self.damage_modifiers.setVisible(visible)
        self.damage_modifiers_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)
        if visible and self._work_splitter is not None and self._pre_expand_sizes is None:
            # 记录展开前的真实分栏分配，收起时按此精确恢复
            self._pre_expand_sizes = list(self._work_splitter.sizes())
        # QSplitter 不会因子 widget 的 sizeHint 变大而自动重排，必须主动 setSizes；
        # 延后到布局重算之后执行，确保拿到的 sizeHint 是展开后的准确值。
        QTimer.singleShot(0, self._sync_splitter_for_modifiers)

    def _sync_splitter_for_modifiers(self):
        """根据“修正”区展开/收起状态，主动调整垂直分栏分配。"""
        if self._work_splitter is None:
            return
        total = self._work_splitter.height()
        if total <= 0:
            return
        if self.damage_modifiers.isVisible():
            need = self.sizeHint().height()
            if self._pre_expand_sizes:
                # 保证展开后明显高于展开前分配
                need = max(need, self._pre_expand_sizes[0] + 100)
            # 给下方日志区至少留 80px 可视空间（log_tabs 的 minimumHeight 120 亦会被 QSplitter 尊重）
            need = min(need, total - 80)
            self._work_splitter.setSizes([need, max(total - need, 0)])
        else:
            # 精确恢复展开前的分配
            if self._pre_expand_sizes is not None:
                self._work_splitter.setSizes(self._pre_expand_sizes)
            self._pre_expand_sizes = None

    def set_log_callback(self, callback):
        """设置日志回调，替代 print 劫持 sys.stdout 的方式"""
        self._log_callback = callback

    def set_rule_mode(self, rule_mode: RuleMode | str):
        self.rule_mode = RuleMode.coerce(rule_mode)

        self.init_mode_combo.blockSignals(True)
        self.init_mode_combo.clear()
        if self.rule_mode == RuleMode.V0_3:
            self.init_mode_combo.addItem("速度先攻", userData="v03_speed")
            self.init_mode_combo.addItem("指定顺位", userData="ranked")
        else:
            self.init_mode_combo.addItem("传统先攻", userData="traditional")
            self.init_mode_combo.addItem("团队先攻", userData="team")
            self.init_mode_combo.addItem("客观判断", userData="manual")
            self.init_mode_combo.addItem("指定顺位", userData="ranked")
        self.init_mode_combo.blockSignals(False)

        self.status_combo.blockSignals(True)
        self.status_combo.clear()
        self.status_combo.addItems(status_names_for(self.rule_mode))
        self.status_combo.blockSignals(False)
        self.elem_type_combo.clear()
        self.elem_type_combo.addItems(element_types_for(self.rule_mode))

        is_v03 = self.rule_mode == RuleMode.V0_3
        self.damage_amount_label.setText(
            "伤害骰结果 / 折前伤害" if is_v03 else "攻击检定 / 折前伤害"
        )
        self.v03_attack_label.setVisible(is_v03)
        self.v03_attack_roll_spin.setVisible(is_v03)
        self.v03_success_rate_spin.setVisible(is_v03)
        self.v03_dying_save_combo.setVisible(is_v03)
        self.v03_formula_label.setVisible(is_v03)
        self.v03_normal_multiplier_spin.setVisible(is_v03)
        self.v03_final_constant_spin.setVisible(is_v03)
        self.element_resistance_label.setVisible(is_v03)
        self.element_resistance_spin.setVisible(is_v03)
        self.burst_roll_label.setText("10d6 爆发总值" if is_v03 else "单次骰值")
        self.use_resistance_cb.setVisible(not is_v03)
        self.save_succeeded_cb.setVisible(not is_v03)
        self.operations_tabs.setMinimumHeight(308 if is_v03 else 164)
        self._on_mode_changed(0)
        self._on_status_selected(self.status_combo.currentText())
        self._on_damage_type_changed(self.dmg_type_combo.currentText())

    def _get_target(self) -> Unit | None:
        return self.selected_target

    def _commit_unit_changes(self):
        if self.unit_provider:
            saved = self.unit_provider.commit_changes()
        else:
            saved = True
        self._refresh_order_list()
        self.set_selected_target(self._get_target())
        return saved

    def _persist_combat_state(self) -> bool:
        if not self.combat_state:
            return True
        try:
            save_combat_state(self.combat_state)
            return True
        except OSError as exc:
            self._log(f"[错误] 战斗进度保存失败: {exc}")
            return False

    # ============================================================
    # 战斗操作
    # ============================================================

    def _start_combat(self):
        if not self.unit_provider:
            return
        players = self.unit_provider.get_players()
        monsters = self.unit_provider.get_monsters()
        all_units = players + monsters

        if not all_units:
            info_box(self, "提示", "请先添加至少一个单位")
            return

        saved = load_combat_state()
        if saved and saved.active:
            if RuleMode.coerce(saved.rule_mode) != self.rule_mode:
                info_box(
                    self,
                    "战斗规则不一致",
                    f"未完成战斗使用 v{RuleMode.coerce(saved.rule_mode).value}，"
                    f"请切换到该版本后再恢复。",
                )
                return
            if question_box(
                self, "恢复战斗",
                f"检测到第 {saved.turn} 轮的未完成战斗，是否继续？",
            ):
                self.combat_state = saved
                self._update_ui_state()
                self._refresh_order_list()
                return

        mode = self.init_mode_combo.currentData()

        if mode == "team":
            if not players or not monsters:
                info_box(self, "提示", "团队先攻模式需要至少一个玩家和一个怪物")
                return
            self.combat_state = team_initiative(
                players, monsters, rule_mode=self.rule_mode
            )
            p_s = sorted([u.speed for u in players])
            m_s = sorted([u.speed for u in monsters])
            p_team = (max(p_s) + min(p_s)) if len(p_s) >= 2 else (p_s[0] * 2 if p_s else 0)
            m_team = (max(m_s) + min(m_s)) if len(m_s) >= 2 else (m_s[0] * 2 if m_s else 0)
            self._set_team_score(
                f"玩家团队值: {p_team} | 怪物团队值: {m_team} | "
                f"{'玩家' if self.combat_state.first_team == 'player' else '怪物'}先动"
            )
        elif mode == "manual":
            first = self.manual_team_combo.currentData()
            self.combat_state = manual_initiative(
                first, players, monsters, rule_mode=self.rule_mode
            )
            self._set_team_score(
                f"客观判断: {'玩家' if self.combat_state.first_team == 'player' else '怪物'}先行")
        elif mode == "ranked":
            self.combat_state = ranked_initiative(
                players, monsters, rule_mode=self.rule_mode
            )
            self._set_team_score("指定顺位: 按单位先攻顺位排序")
        else:
            roll_units = all_units
            if self.rule_mode == RuleMode.V0_3:
                grouped: dict[tuple[int, int], list[Unit]] = {}
                for unit in all_units:
                    grouped.setdefault(
                        (unit.speed, unit.reaction_mobility), []
                    ).append(unit)
                roll_units = [
                    unit for group in grouped.values() if len(group) > 1
                    for unit in group
                ]
            roll_values: dict[str, int] = {}
            if roll_units:
                dialog = InitiativeRollDialog(roll_units, self.rule_mode, self)
                if dialog.exec() != QDialog.Accepted or dialog.result_values is None:
                    return
                roll_values = dialog.result_values
            try:
                self.combat_state = traditional_initiative(
                    all_units,
                    roll_values=roll_values,
                    rule_mode=self.rule_mode,
                )
            except ValueError as exc:
                warn_box(self, "检定结果无效", str(exc))
                return
            rolls = self.combat_state.initiative_rolls
            lines = []
            for uid, roll in sorted(rolls.items(), key=lambda x: x[1], reverse=True):
                unit = self.unit_provider.find_unit(uid)
                name = unit.name if unit else uid
                label = "d100" if self.rule_mode == RuleMode.V0_3 else "反应机动"
                lines.append(f"{name}: {label} {roll}")
            if self.rule_mode == RuleMode.V0_3 and not lines:
                lines.append("按速度、反应机动排序；无完全同值单位")
            self._set_team_score(" | ".join(lines))

        self._update_ui_state()
        self._refresh_order_list()
        self._persist_combat_state()

    def _next_action(self):
        if not self.combat_state or not self.combat_state.active:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = next_actor(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        if self._commit_unit_changes():
            self._persist_combat_state()
        else:
            self._log("[错误] 单位数据未保存，战斗进度暂未写入；请修复存档路径后重试")

    def _end_turn(self):
        if not self.combat_state:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = advance_turn(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        if self._commit_unit_changes():
            self._persist_combat_state()
        else:
            self._log("[错误] 单位数据未保存，战斗进度暂未写入；请修复存档路径后重试")

    def _end_combat(self):
        if not self.combat_state:
            return
        if question_box(
            self, "结束战斗",
            f"确定要在第 {self.combat_state.turn} 轮结束战斗吗？",
        ):
            self.combat_state.active = False
            self.combat_state = None
            delete_combat_state()
            self.turn_label.setText("轮次 --")
            self.now_label.setText("当前行动 --")
            self._set_team_score("")
            self._refresh_order_list()
            self.start_btn.setEnabled(True)
            self.next_btn.setEnabled(False)
            self.end_turn_btn.setEnabled(False)
            self.end_combat_btn.setEnabled(False)

    # ============================================================
    # 伤害 / 治疗 / 元素 / 状态
    # ============================================================

    def _apply_damage(self):
        target = self._get_target()
        if not target:
            info_box(self, "提示", "请先在左侧选择一个目标单位")
            return
        amount = self.dmg_amount_spin.value()
        dmg_type = self.dmg_type_combo.currentText()
        is_attack = self.is_attack_cb.isChecked() and dmg_type != "治疗"

        attacker = None
        if is_attack and self.combat_state and self.combat_state.active:
            cur_id = self.combat_state.current_unit_id
            if cur_id:
                attacker = self.unit_provider.find_unit(cur_id)
            if attacker is None:
                info_box(self, "提示", "勾选了「攻击」但无法确定当前行动者，请先开始战斗")
                return

        if dmg_type == "治疗":
            msg = apply_healing(target, amount, rule_mode=self.rule_mode)
        else:
            msg = apply_damage(
                target,
                amount,
                dmg_type,
                is_attack,
                attacker=attacker,
                amount_is_final=self.final_damage_cb.isChecked(),
                auxiliary_damage=self.aux_damage_spin.value() if self.aux_damage_cb.isChecked() else 0,
                final_multiplier=0.5 if self.half_damage_cb.isChecked() else 1.0,
                rule_mode=self.rule_mode,
                attack_roll=(
                    self.v03_attack_roll_spin.value()
                    if self.rule_mode == RuleMode.V0_3 and is_attack else None
                ),
                success_rate=(
                    self.v03_success_rate_spin.value()
                    if self.rule_mode == RuleMode.V0_3 and is_attack else None
                ),
                dying_save_succeeded=(
                    self.v03_dying_save_combo.currentData()
                    if self.rule_mode == RuleMode.V0_3 else None
                ),
                normal_multiplier=self.v03_normal_multiplier_spin.value(),
                final_constant=self.v03_final_constant_spin.value(),
            )

        self._log(msg)
        self._commit_unit_changes()

    def _apply_elem_dmg(self):
        target = self._get_target()
        if not target:
            info_box(self, "提示", "请先在左侧选择一个目标单位")
            return
        amount = self.elem_amount_spin.value()
        elem_type = self.elem_type_combo.currentText()
        burst_roll = self.burst_roll_spin.value() if self.burst_roll_cb.isChecked() else None
        msg = apply_elemental_damage(
            target,
            amount,
            elem_type,
            burst_roll=burst_roll,
            rule_mode=self.rule_mode,
            element_resistance=self.element_resistance_spin.value(),
        )
        self._log(msg)
        self._commit_unit_changes()

    def _resolve_pending_burst(self):
        target = self._get_target()
        if not target:
            info_box(self, "提示", "请先在左侧选择一个目标单位")
            return
        msg = resolve_pending_elemental_burst(
            target,
            self.burst_roll_spin.value(),
            rule_mode=self.rule_mode,
            element_resistance=self.element_resistance_spin.value(),
        )
        self._log(msg)
        self._commit_unit_changes()

    def _apply_status(self):
        target = self._get_target()
        if not target:
            info_box(self, "提示", "请先在左侧选择一个目标单位")
            return
        status_name = self.status_combo.currentText()
        if not status_name:
            return
        stacks = self.x_spin.value() if status_name in x_statuses_for(self.rule_mode) else 0
        msg = apply_status(
            target,
            status_name,
            stacks,
            use_resistance=self.use_resistance_cb.isChecked(),
            save_succeeded=self.save_succeeded_cb.isChecked(),
            rule_mode=self.rule_mode,
        )
        self._log(msg)
        self._commit_unit_changes()

    def _clear_current_status(self):
        target = self._get_target()
        if not target:
            info_box(self, "提示", "请先在左侧选择一个目标单位")
            return
        removed = clear_all_statuses(target)
        if removed:
            self._log(f"{target.name} 清除了全部状态: {'、'.join(removed)}")
        else:
            self._log(f"{target.name} 无状态可清除")
        self._commit_unit_changes()

    # ============================================================
    # UI 刷新
    # ============================================================

    def _update_ui_state(self):
        if not self.combat_state or not self.combat_state.active:
            return
        self.turn_label.setText(f"轮次 {self.combat_state.turn}")
        cur_id = self.combat_state.current_unit_id
        if cur_id and self.unit_provider:
            unit = self.unit_provider.find_unit(cur_id)
            if unit:
                self.now_label.setText(
                    f"当前行动 {unit.name} · HP {unit.current_hp}/{unit.max_hp}"
                )
            else:
                self.now_label.setText(f"当前行动 {cur_id}")
        else:
            self.now_label.setText("当前行动 --")
        pulse(self.now_label)

        self.start_btn.setEnabled(False)
        self.next_btn.setEnabled(True)
        self.end_turn_btn.setEnabled(True)
        self.end_combat_btn.setEnabled(True)

    def _refresh_order_list(self):
        self._refreshing_order = True
        self.order_list.clear()
        if not self.combat_state or not self.combat_state.turn_order:
            if self.combat_state:
                text = "未开始战斗——点击『开始战斗』后显示行动顺序"
            else:
                text = "暂无行动顺序。添加单位后开始战斗。"
            self.order_placeholder.set_text(text)
            self.order_placeholder.show()
            self._refreshing_order = False
            return
        for i, uid in enumerate(self.combat_state.turn_order):
            unit = self.unit_provider.find_unit(uid) if self.unit_provider else None
            if not unit:
                continue
            roll = self.combat_state.initiative_rolls.get(uid, "")
            roll_text = f" (检定: {roll})" if roll else ""
            if self.combat_state.initiative_mode == "ranked":
                roll_text = f" (顺位: {unit.initiative_rank})"
            hp = f"HP:{unit.current_hp}/{unit.max_hp}"
            tenacity = f"韧性:{unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}"
            line = f"{i + 1}. {unit.name}  [{hp}] [{tenacity}]{roll_text}"
            if i == self.combat_state.now_index:
                line += "  · 当前行动"
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, uid)
            if i == self.combat_state.now_index:
                item.setBackground(QBrush(QColor(THEME["current_actor_bg"])))
            self.order_list.addItem(item)
        self.order_placeholder.hide()
        self._refreshing_order = False

    def _sync_order_from_list(self):
        if self._refreshing_order or not self.combat_state:
            return
        current_id = self.combat_state.current_unit_id
        order = [
            self.order_list.item(index).data(Qt.UserRole)
            for index in range(self.order_list.count())
        ]
        self.combat_state.turn_order = [uid for uid in order if uid]
        if current_id in self.combat_state.turn_order:
            self.combat_state.now_index = self.combat_state.turn_order.index(current_id)
        else:
            self.combat_state.now_index = 0
        self._refresh_order_list()
        self._persist_combat_state()

    def _on_mode_changed(self, index: int):
        """先攻模式切换时显示/隐藏相关子控件"""
        mode = self.init_mode_combo.currentData()
        # 手动/隐藏先动阵营行
        for i in range(self._manual_row.count()):
            w = self._manual_row.itemAt(i).widget()
            if w:
                w.setVisible(mode == "manual")
        # 传统先攻/隐藏骰子行
        for i in range(self._dice_row.count()):
            w = self._dice_row.itemAt(i).widget()
            if w:
                w.setVisible(mode in {"traditional", "v03_speed"})

    def _set_team_score(self, text: str):
        self.team_score_label.setText(text)
        self.team_score_label.setVisible(bool(text))

    def _on_status_selected(self, status: str):
        if status in x_statuses_for(self.rule_mode):
            self.x_label.show()
            self.x_spin.show()
        else:
            self.x_label.hide()
            self.x_spin.hide()
            self.x_spin.setValue(0)
        if self.rule_mode == RuleMode.V0_3:
            self.use_resistance_cb.setEnabled(False)
            self.save_succeeded_cb.setEnabled(False)
            return
        definition = STATUS_DEFINITIONS.get(status)
        is_negative = bool(definition and definition.polarity == "negative")
        self.use_resistance_cb.setEnabled(is_negative)
        self.save_succeeded_cb.setEnabled(is_negative)
        if not is_negative:
            self.save_succeeded_cb.setChecked(False)

    def _on_damage_type_changed(self, damage_type: str):
        is_healing = damage_type == "治疗"
        is_true = damage_type == "真实"
        if self.operations_tabs.count():
            self.operations_tabs.setTabText(0, "治疗" if is_healing else "伤害")
        self.is_attack_cb.setEnabled(not is_healing)
        self.final_damage_cb.setEnabled(not is_healing and not is_true)
        self.aux_damage_cb.setEnabled(not is_healing and not is_true)
        self.aux_damage_spin.setEnabled(
            self.aux_damage_cb.isChecked() and self.aux_damage_cb.isEnabled()
        )
        self.half_damage_cb.setEnabled(not is_healing and not is_true)
        v03_attack_inputs = (
            self.rule_mode == RuleMode.V0_3 and not is_healing
            and self.is_attack_cb.isChecked()
        )
        self.v03_attack_roll_spin.setEnabled(v03_attack_inputs)
        self.v03_success_rate_spin.setEnabled(v03_attack_inputs)
        if is_healing or is_true:
            self.final_damage_cb.setChecked(False)
            self.aux_damage_cb.setChecked(False)
            self.half_damage_cb.setChecked(False)

    def _log(self, msg: str):
        for line in msg.split("\n"):
            self._log_callback(f"[战斗日志] {line}")
