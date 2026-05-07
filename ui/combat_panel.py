"""TRPG 战斗管理器 - 战斗控制面板 (PySide6)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QButtonGroup, QSpinBox, QComboBox, QCheckBox, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from models import (
    Unit, CombatState, ALL_STATUS_NAMES,
    X_STATUSES, ELEMENT_TYPES,
)
from combat import (
    team_initiative, traditional_initiative, manual_initiative,
    apply_damage, apply_healing, apply_elemental_damage,
    apply_status, clear_all_statuses, next_actor, advance_turn,
)


class CombatPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.combat_state: CombatState | None = None
        self.unit_provider = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- 先攻模式 ----
        mode_group = QGroupBox("先攻模式")
        mode_layout = QVBoxLayout(mode_group)

        self.init_mode_group = QButtonGroup(self)
        for text, val in [("传统先攻", "traditional"), ("团队先攻", "team"), ("客观判断", "manual")]:
            rb = QRadioButton(text)
            self.init_mode_group.addButton(rb)
            rb.val = val
            mode_layout.addWidget(rb)
            if val == "traditional":
                rb.setChecked(True)

        manual_row = QHBoxLayout()
        manual_row.addWidget(QLabel("先动阵营:"))
        self.manual_team_combo = QComboBox()
        self.manual_team_combo.addItems(["player", "monster"])
        manual_row.addWidget(self.manual_team_combo)
        manual_row.addStretch()
        mode_layout.addLayout(manual_row)

        dice_row = QHBoxLayout()
        dice_row.addWidget(QLabel("检定骰子:"))
        self.dice_spin = QSpinBox()
        self.dice_spin.setRange(2, 100)
        self.dice_spin.setValue(20)
        dice_row.addWidget(self.dice_spin)
        dice_row.addWidget(QLabel("面"))
        dice_row.addStretch()
        mode_layout.addLayout(dice_row)

        layout.addWidget(mode_group)

        # ---- 战斗状态 ----
        info_group = QGroupBox("战斗状态")
        info_layout = QHBoxLayout(info_group)
        self.turn_label = QLabel("Turn: 0")
        self.turn_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        info_layout.addWidget(self.turn_label)
        self.now_label = QLabel("Now: --")
        self.now_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self.now_label)
        self.team_score_label = QLabel("")
        info_layout.addWidget(self.team_score_label)
        info_layout.addStretch()
        layout.addWidget(info_group)

        # ---- 战斗控制按钮 ----
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始战斗")
        self.start_btn.clicked.connect(self._start_combat)
        btn_row.addWidget(self.start_btn)

        self.next_btn = QPushButton("下一行动")
        self.next_btn.clicked.connect(self._next_action)
        self.next_btn.setEnabled(False)
        btn_row.addWidget(self.next_btn)

        self.end_turn_btn = QPushButton("结束回合")
        self.end_turn_btn.clicked.connect(self._end_turn)
        self.end_turn_btn.setEnabled(False)
        btn_row.addWidget(self.end_turn_btn)

        self.end_combat_btn = QPushButton("结束战斗")
        self.end_combat_btn.clicked.connect(self._end_combat)
        self.end_combat_btn.setEnabled(False)
        btn_row.addWidget(self.end_combat_btn)
        layout.addLayout(btn_row)

        # ---- 伤害 / 治疗 ----
        dmg_group = QGroupBox("伤害 / 治疗")
        dmg_layout = QHBoxLayout(dmg_group)
        dmg_layout.addWidget(QLabel("数值:"))
        self.dmg_amount_spin = QSpinBox()
        self.dmg_amount_spin.setRange(1, 9999)
        self.dmg_amount_spin.setValue(5)
        dmg_layout.addWidget(self.dmg_amount_spin)

        dmg_layout.addWidget(QLabel("类型:"))
        self.dmg_type_combo = QComboBox()
        self.dmg_type_combo.addItems(["物理", "法术", "真实", "治疗"])
        dmg_layout.addWidget(self.dmg_type_combo)

        self.is_attack_cb = QCheckBox("攻击")
        self.is_attack_cb.setChecked(True)
        dmg_layout.addWidget(self.is_attack_cb)

        apply_dmg_btn = QPushButton("施加")
        apply_dmg_btn.clicked.connect(self._apply_damage)
        dmg_layout.addWidget(apply_dmg_btn)
        layout.addWidget(dmg_group)

        # ---- 元素损伤 ----
        elem_group = QGroupBox("元素损伤")
        elem_layout = QHBoxLayout(elem_group)
        elem_layout.addWidget(QLabel("数值:"))
        self.elem_amount_spin = QSpinBox()
        self.elem_amount_spin.setRange(1, 999)
        self.elem_amount_spin.setValue(2)
        elem_layout.addWidget(self.elem_amount_spin)

        elem_layout.addWidget(QLabel("类型:"))
        self.elem_type_combo = QComboBox()
        self.elem_type_combo.addItems(ELEMENT_TYPES)
        elem_layout.addWidget(self.elem_type_combo)

        apply_elem_btn = QPushButton("施加")
        apply_elem_btn.clicked.connect(self._apply_elem_dmg)
        elem_layout.addWidget(apply_elem_btn)
        layout.addWidget(elem_group)

        # ---- 行动顺序 ----
        order_group = QGroupBox("行动顺序")
        order_layout = QVBoxLayout(order_group)
        self.order_list = QListWidget()
        self.order_list.setMaximumHeight(140)
        order_layout.addWidget(self.order_list)
        layout.addWidget(order_group, 1)

        # ---- 状态操作 ----
        status_group = QGroupBox("状态操作")
        status_layout = QHBoxLayout(status_group)
        status_layout.addWidget(QLabel("状态:"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(ALL_STATUS_NAMES)
        status_layout.addWidget(self.status_combo)

        self.x_label = QLabel("X:")
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 99)
        status_layout.addWidget(self.x_label)
        status_layout.addWidget(self.x_spin)

        apply_status_btn = QPushButton("施加")
        apply_status_btn.clicked.connect(self._apply_status)
        status_layout.addWidget(apply_status_btn)

        clear_status_btn = QPushButton("清除全部")
        clear_status_btn.clicked.connect(self._clear_current_status)
        status_layout.addWidget(clear_status_btn)

        self.status_combo.currentTextChanged.connect(self._on_status_selected)
        self._on_status_selected(self.status_combo.currentText())
        layout.addWidget(status_group)

    # ============================================================
    # 接口
    # ============================================================

    def set_unit_provider(self, panel):
        self.unit_provider = panel

    def _get_target(self) -> Unit | None:
        if not self.unit_provider:
            return None
        if self.combat_state and self.combat_state.active:
            cur_id = self.combat_state.current_unit_id
            if cur_id:
                return self.unit_provider.find_unit(cur_id)
        return self.unit_provider._get_selected_unit()

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
            QMessageBox.information(self, "提示", "请先添加至少一个单位")
            return

        mode = self.init_mode_group.checkedButton().val

        if mode == "team":
            if not players or not monsters:
                QMessageBox.information(self, "提示", "团队先攻模式需要至少一个玩家和一个怪物")
                return
            self.combat_state = team_initiative(players, monsters)
            p_s = sorted([u.speed for u in players])
            m_s = sorted([u.speed for u in monsters])
            p_team = (max(p_s) + min(p_s)) if len(p_s) >= 2 else (p_s[0] * 2 if p_s else 0)
            m_team = (max(m_s) + min(m_s)) if len(m_s) >= 2 else (m_s[0] * 2 if m_s else 0)
            self.team_score_label.setText(
                f"玩家团队值: {p_team} | 怪物团队值: {m_team} | "
                f"{'玩家' if self.combat_state.first_team == 'player' else '怪物'}先动"
            )
        elif mode == "manual":
            first = self.manual_team_combo.currentText()
            self.combat_state = manual_initiative(first, players, monsters)
            self.team_score_label.setText(
                f"客观判断: {'玩家' if self.combat_state.first_team == 'player' else '怪物'}先行")
        else:
            self.combat_state = traditional_initiative(all_units, self.dice_spin.value())
            rolls = self.combat_state.initiative_rolls
            lines = []
            for uid, roll in sorted(rolls.items(), key=lambda x: x[1], reverse=True):
                unit = self.unit_provider.find_unit(uid)
                name = unit.name if unit else uid
                lines.append(f"{name}: d{self.dice_spin.value()}+{unit.speed if unit else '?'}={roll}")
            self.team_score_label.setText(" | ".join(lines))

        self._update_ui_state()
        self._refresh_order_list()

    def _next_action(self):
        if not self.combat_state or not self.combat_state.active:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = next_actor(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        self._refresh_order_list()

    def _end_turn(self):
        if not self.combat_state:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = advance_turn(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        self._refresh_order_list()

    def _end_combat(self):
        if not self.combat_state:
            return
        reply = QMessageBox.question(
            self, "结束战斗",
            f"确定要在第 {self.combat_state.turn} 回合结束战斗吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.combat_state.active = False
            self.combat_state = None
            self.turn_label.setText("Turn: --")
            self.now_label.setText("Now: --")
            self.team_score_label.setText("")
            self.order_list.clear()
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
            QMessageBox.information(self, "提示", "请先在左侧选择一个目标单位")
            return
        amount = self.dmg_amount_spin.value()
        dmg_type = self.dmg_type_combo.currentText()
        is_attack = self.is_attack_cb.isChecked()

        if dmg_type == "治疗":
            msg = apply_healing(target, amount)
        else:
            msg = apply_damage(target, amount, dmg_type, is_attack)

        self._log(msg)
        self.unit_provider._refresh_tree()
        self._refresh_order_list()

    def _apply_elem_dmg(self):
        target = self._get_target()
        if not target:
            QMessageBox.information(self, "提示", "请先在左侧选择一个目标单位")
            return
        amount = self.elem_amount_spin.value()
        elem_type = self.elem_type_combo.currentText()
        msg = apply_elemental_damage(target, amount, elem_type)
        self._log(msg)
        self.unit_provider._refresh_tree()
        self._refresh_order_list()

    def _apply_status(self):
        target = self._get_target()
        if not target:
            QMessageBox.information(self, "提示", "请先在左侧选择一个目标单位")
            return
        status_name = self.status_combo.currentText()
        if not status_name:
            return
        stacks = self.x_spin.value() if status_name in X_STATUSES else 0
        msg = apply_status(target, status_name, stacks)
        self._log(msg)
        self.unit_provider._refresh_tree()
        self._refresh_order_list()

    def _clear_current_status(self):
        target = self._get_target()
        if not target:
            QMessageBox.information(self, "提示", "请先在左侧选择一个目标单位")
            return
        removed = clear_all_statuses(target)
        if removed:
            self._log(f"{target.name} 清除了全部状态: {'、'.join(removed)}")
        else:
            self._log(f"{target.name} 无状态可清除")
        self.unit_provider._refresh_tree()
        self._refresh_order_list()

    # ============================================================
    # UI 刷新
    # ============================================================

    def _update_ui_state(self):
        if not self.combat_state or not self.combat_state.active:
            return
        self.turn_label.setText(f"Turn: {self.combat_state.turn}")
        cur_id = self.combat_state.current_unit_id
        if cur_id and self.unit_provider:
            unit = self.unit_provider.find_unit(cur_id)
            self.now_label.setText(f"Now: {unit.name if unit else cur_id}")
        else:
            self.now_label.setText("Now: --")

        self.start_btn.setEnabled(False)
        self.next_btn.setEnabled(True)
        self.end_turn_btn.setEnabled(True)
        self.end_combat_btn.setEnabled(True)

    def _refresh_order_list(self):
        self.order_list.clear()
        if not self.combat_state:
            return
        for i, uid in enumerate(self.combat_state.turn_order):
            unit = self.unit_provider.find_unit(uid) if self.unit_provider else None
            if not unit:
                continue
            roll = self.combat_state.initiative_rolls.get(uid, "")
            roll_text = f" (检定: {roll})" if roll else ""
            hp = f"HP:{unit.current_hp}/{unit.max_hp}"
            tenacity = f"韧性:{unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}"
            line = f"{i + 1}. {unit.name}  [{hp}] [{tenacity}]{roll_text}"
            if i == self.combat_state.now_index:
                line += "  <- NOW"
            item = QListWidgetItem(line)
            if i == self.combat_state.now_index:
                item.setBackground(QBrush(QColor("#d4e6f1")))
            self.order_list.addItem(item)

    def _on_status_selected(self, status: str):
        if status in X_STATUSES:
            self.x_label.show()
            self.x_spin.show()
        else:
            self.x_label.hide()
            self.x_spin.hide()
            self.x_spin.setValue(0)

    def _log(self, msg: str):
        for line in msg.split("\n"):
            print(f"[战斗日志] {line}")
