"""TRPG 战斗管理器 - 战斗控制面板 (PySide6)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QSpinBox, QComboBox, QCheckBox, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from models import (
    Unit, CombatState, ALL_STATUS_NAMES,
    X_STATUSES, ELEMENT_TYPES, THEME,
)
from combat import (
    team_initiative, traditional_initiative, manual_initiative,
    apply_damage, apply_healing, apply_elemental_damage,
    apply_status, clear_all_statuses, next_actor, advance_turn,
)
from persistence import save_combat_state, load_combat_state, delete_combat_state


class CombatPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.combat_state: CombatState | None = None
        self.unit_provider = None
        self._log_callback = print  # 默认直接 print，连接后走主窗口日志

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- 先攻模式（下拉栏） ----
        mode_group = QGroupBox("先攻模式")
        mode_layout = QVBoxLayout(mode_group)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("模式:"))
        self.init_mode_combo = QComboBox()
        self.init_mode_combo.addItem("传统先攻", "traditional")
        self.init_mode_combo.addItem("团队先攻", "team")
        self.init_mode_combo.addItem("客观判断", "manual")
        self.init_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.init_mode_combo)
        mode_row.addStretch()
        mode_layout.addLayout(mode_row)

        self._manual_row = QHBoxLayout()
        self._manual_row.addWidget(QLabel("先动阵营:"))
        self.manual_team_combo = QComboBox()
        self.manual_team_combo.addItems(["player", "monster"])
        self._manual_row.addWidget(self.manual_team_combo)
        self._manual_row.addStretch()
        mode_layout.addLayout(self._manual_row)

        self._dice_row = QHBoxLayout()
        self._dice_row.addWidget(QLabel("检定骰子:"))
        self.dice_spin = QSpinBox()
        self.dice_spin.setRange(2, 100)
        self.dice_spin.setValue(20)
        self._dice_row.addWidget(self.dice_spin)
        self._dice_row.addWidget(QLabel("面"))
        self._dice_row.addStretch()
        mode_layout.addLayout(self._dice_row)

        self._on_mode_changed(0)
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

        # ---- 战斗操作（合并） ----
        ops_group = QGroupBox("战斗操作")
        ops_grid = QGridLayout(ops_group)
        ops_grid.setSpacing(4)

        # 行 0：伤害/治疗
        ops_grid.addWidget(QLabel("伤害/治疗"), 0, 0)
        ops_grid.addWidget(QLabel("数值:"), 0, 1)
        self.dmg_amount_spin = QSpinBox()
        self.dmg_amount_spin.setRange(1, 9999)
        self.dmg_amount_spin.setValue(5)
        ops_grid.addWidget(self.dmg_amount_spin, 0, 2)
        ops_grid.addWidget(QLabel("类型:"), 0, 3)
        self.dmg_type_combo = QComboBox()
        self.dmg_type_combo.addItems(["物理", "法术", "真实", "治疗"])
        ops_grid.addWidget(self.dmg_type_combo, 0, 4)
        self.is_attack_cb = QCheckBox("攻击")
        self.is_attack_cb.setChecked(True)
        ops_grid.addWidget(self.is_attack_cb, 0, 5)
        apply_dmg_btn = QPushButton("施加")
        apply_dmg_btn.clicked.connect(self._apply_damage)
        ops_grid.addWidget(apply_dmg_btn, 0, 6)

        # 行 1：元素损伤
        ops_grid.addWidget(QLabel("元素损伤"), 1, 0)
        ops_grid.addWidget(QLabel("数值:"), 1, 1)
        self.elem_amount_spin = QSpinBox()
        self.elem_amount_spin.setRange(1, 999)
        self.elem_amount_spin.setValue(2)
        ops_grid.addWidget(self.elem_amount_spin, 1, 2)
        ops_grid.addWidget(QLabel("类型:"), 1, 3)
        self.elem_type_combo = QComboBox()
        self.elem_type_combo.addItems(ELEMENT_TYPES)
        ops_grid.addWidget(self.elem_type_combo, 1, 4)
        apply_elem_btn = QPushButton("施加")
        apply_elem_btn.clicked.connect(self._apply_elem_dmg)
        ops_grid.addWidget(apply_elem_btn, 1, 6)

        # 行 2：状态操作
        ops_grid.addWidget(QLabel("状态操作"), 2, 0)
        ops_grid.addWidget(QLabel("状态:"), 2, 1)
        self.status_combo = QComboBox()
        self.status_combo.addItems(ALL_STATUS_NAMES)
        ops_grid.addWidget(self.status_combo, 2, 2)
        self.x_label = QLabel("X:")
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 99)
        ops_grid.addWidget(self.x_label, 2, 3)
        ops_grid.addWidget(self.x_spin, 2, 4)
        apply_status_btn = QPushButton("施加")
        apply_status_btn.clicked.connect(self._apply_status)
        ops_grid.addWidget(apply_status_btn, 2, 5)
        clear_status_btn = QPushButton("清除全部")
        clear_status_btn.clicked.connect(self._clear_current_status)
        ops_grid.addWidget(clear_status_btn, 2, 6)

        self.status_combo.currentTextChanged.connect(self._on_status_selected)
        self._on_status_selected(self.status_combo.currentText())
        layout.addWidget(ops_group)

        # ---- 行动顺序 ----
        order_group = QGroupBox("行动顺序")
        order_layout = QVBoxLayout(order_group)
        self.order_list = QListWidget()
        self.order_list.setMaximumHeight(140)
        order_layout.addWidget(self.order_list)
        layout.addWidget(order_group, 1)

    # ============================================================
    # 接口
    # ============================================================

    def set_unit_provider(self, panel):
        self.unit_provider = panel

    def set_log_callback(self, callback):
        """设置日志回调，替代 print 劫持 sys.stdout 的方式"""
        self._log_callback = callback

    def _get_target(self) -> Unit | None:
        if not self.unit_provider:
            return None
        if self.combat_state and self.combat_state.active:
            cur_id = self.combat_state.current_unit_id
            if cur_id:
                return self.unit_provider.find_unit(cur_id)
        return self.unit_provider.get_selected_unit()

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

        saved = load_combat_state()
        if saved and saved.active:
            reply = QMessageBox.question(
                self, "恢复战斗",
                f"检测到第 {saved.turn} 回合的未完成战斗，是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.combat_state = saved
                self._update_ui_state()
                self._refresh_order_list()
                return

        mode = self.init_mode_combo.currentData()

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
        save_combat_state(self.combat_state)

    def _next_action(self):
        if not self.combat_state or not self.combat_state.active:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = next_actor(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        self._refresh_order_list()
        save_combat_state(self.combat_state)

    def _end_turn(self):
        if not self.combat_state:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = advance_turn(self.combat_state, all_units)
        for msg in messages:
            self._log(msg)
        self._update_ui_state()
        self._refresh_order_list()
        save_combat_state(self.combat_state)

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
            delete_combat_state()
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
        target = self.unit_provider.get_selected_unit() if self.unit_provider else None
        if not target:
            QMessageBox.information(self, "提示", "请先在左侧选择一个目标单位")
            return
        amount = self.dmg_amount_spin.value()
        dmg_type = self.dmg_type_combo.currentText()
        is_attack = self.is_attack_cb.isChecked()

        attacker = None
        if is_attack and self.combat_state and self.combat_state.active:
            cur_id = self.combat_state.current_unit_id
            if cur_id:
                attacker = self.unit_provider.find_unit(cur_id)
            if attacker is None:
                QMessageBox.information(self, "提示", "勾选了"攻击"但无法确定当前回合方，请先开始战斗")
                return

        if dmg_type == "治疗":
            msg = apply_healing(target, amount)
        else:
            msg = apply_damage(target, amount, dmg_type, is_attack, attacker=attacker)

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
                item.setBackground(QBrush(QColor(THEME["current_actor_bg"])))
            self.order_list.addItem(item)

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
                w.setVisible(mode == "traditional")

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
            self._log_callback(f"[战斗日志] {line}")
