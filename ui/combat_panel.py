"""TRPG 战斗管理器 - 战斗控制面板（右侧）"""

import tkinter as tk
from tkinter import ttk, messagebox
from models import (
    Unit, CombatState, ALL_STATUS_NAMES,
    X_STATUSES, ELEMENT_TYPES,
)
from combat import (
    team_initiative, traditional_initiative, manual_initiative,
    apply_damage, apply_healing, apply_elemental_damage,
    apply_status, clear_all_statuses, next_actor, advance_turn,
)


class CombatPanel(ttk.Frame):
    """战斗控制面板"""

    def __init__(self, parent):
        super().__init__(parent, padding=5)
        self.combat_state: CombatState | None = None
        self.unit_provider = None
        self._build_ui()

    def set_unit_provider(self, panel):
        self.unit_provider = panel

    def _build_ui(self):
        # ---- 先攻模式 ----
        mode_frame = ttk.LabelFrame(self, text="先攻模式", padding=5)
        mode_frame.pack(fill=tk.X, pady=2)

        self.init_mode_var = tk.StringVar(value="traditional")
        ttk.Radiobutton(mode_frame, text="传统先攻", variable=self.init_mode_var, value="traditional").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="团队先攻", variable=self.init_mode_var, value="team").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="客观判断", variable=self.init_mode_var, value="manual").grid(row=1, column=0, columnspan=2, sticky=tk.W)

        manual_row = ttk.Frame(mode_frame)
        manual_row.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Label(manual_row, text="先动阵营:").pack(side=tk.LEFT)
        self.manual_team_var = tk.StringVar(value="player")
        ttk.Combobox(manual_row, textvariable=self.manual_team_var, values=["player", "monster"], state="readonly", width=10).pack(side=tk.LEFT, padx=5)

        dice_row = ttk.Frame(mode_frame)
        dice_row.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Label(dice_row, text="检定骰子:").pack(side=tk.LEFT)
        self.dice_var = tk.IntVar(value=20)
        ttk.Spinbox(dice_row, textvariable=self.dice_var, from_=2, to=100, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(dice_row, text="面").pack(side=tk.LEFT)

        # ---- 回合信息 ----
        info_frame = ttk.LabelFrame(self, text="战斗状态", padding=5)
        info_frame.pack(fill=tk.X, pady=2)

        self.turn_label = ttk.Label(info_frame, text="Turn: 0", font=("", 12, "bold"))
        self.turn_label.pack(side=tk.LEFT, padx=10)
        self.now_label = ttk.Label(info_frame, text="Now: --", font=("", 12))
        self.now_label.pack(side=tk.LEFT, padx=10)
        self.team_score_label = ttk.Label(info_frame, text="", font=("", 9))
        self.team_score_label.pack(anchor=tk.W)

        # ---- 战斗控制按钮 ----
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)

        self.start_btn = ttk.Button(btn_frame, text="开始战斗", command=self._start_combat, width=10)
        self.start_btn.pack(side=tk.LEFT, padx=1)
        self.next_btn = ttk.Button(btn_frame, text="下一行动", command=self._next_action, width=10, state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=1)
        self.end_turn_btn = ttk.Button(btn_frame, text="结束回合", command=self._end_turn, width=10, state=tk.DISABLED)
        self.end_turn_btn.pack(side=tk.LEFT, padx=1)
        self.end_combat_btn = ttk.Button(btn_frame, text="结束战斗", command=self._end_combat, width=10, state=tk.DISABLED)
        self.end_combat_btn.pack(side=tk.LEFT, padx=1)

        # ---- 伤害 / 治疗 ----
        dmg_frame = ttk.LabelFrame(self, text="伤害 / 治疗", padding=5)
        dmg_frame.pack(fill=tk.X, pady=3)

        row1 = ttk.Frame(dmg_frame)
        row1.pack(fill=tk.X)

        ttk.Label(row1, text="数值:").pack(side=tk.LEFT)
        self.dmg_amount_var = tk.IntVar(value=5)
        ttk.Spinbox(row1, textvariable=self.dmg_amount_var, from_=1, to=9999, width=6).pack(side=tk.LEFT, padx=3)

        ttk.Label(row1, text="类型:").pack(side=tk.LEFT, padx=(5, 0))
        self.dmg_type_var = tk.StringVar(value="物理")
        ttk.Combobox(row1, textvariable=self.dmg_type_var, values=["物理", "法术", "真实", "治疗"], state="readonly", width=6).pack(side=tk.LEFT, padx=3)

        self.is_attack_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="攻击", variable=self.is_attack_var).pack(side=tk.LEFT, padx=5)

        ttk.Button(row1, text="施加", command=self._apply_damage, width=6).pack(side=tk.RIGHT, padx=2)

        # ---- 元素损伤 ----
        elem_frame = ttk.LabelFrame(self, text="元素损伤", padding=5)
        elem_frame.pack(fill=tk.X, pady=3)

        e_row = ttk.Frame(elem_frame)
        e_row.pack(fill=tk.X)

        ttk.Label(e_row, text="数值:").pack(side=tk.LEFT)
        self.elem_amount_var = tk.IntVar(value=2)
        ttk.Spinbox(e_row, textvariable=self.elem_amount_var, from_=1, to=999, width=6).pack(side=tk.LEFT, padx=3)

        ttk.Label(e_row, text="类型:").pack(side=tk.LEFT, padx=(5, 0))
        self.elem_type_var = tk.StringVar()
        ttk.Combobox(e_row, textvariable=self.elem_type_var, values=ELEMENT_TYPES, state="readonly", width=12).pack(side=tk.LEFT, padx=3)
        if ELEMENT_TYPES:
            self.elem_type_var.set(ELEMENT_TYPES[0])

        ttk.Button(e_row, text="施加", command=self._apply_elem_dmg, width=6).pack(side=tk.RIGHT, padx=2)

        # ---- 行动顺序 ----
        order_frame = ttk.LabelFrame(self, text="行动顺序", padding=5)
        order_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        self.order_list = tk.Listbox(order_frame, height=7, font=("Microsoft YaHei", 9))
        self.order_list.pack(fill=tk.BOTH, expand=True)

        # ---- 状态操作 ----
        status_frame = ttk.LabelFrame(self, text="状态操作", padding=5)
        status_frame.pack(fill=tk.X, pady=2)

        s_row1 = ttk.Frame(status_frame)
        s_row1.pack(fill=tk.X)

        ttk.Label(s_row1, text="状态:").pack(side=tk.LEFT)
        self.apply_status_var = tk.StringVar()
        self.status_combo = ttk.Combobox(s_row1, textvariable=self.apply_status_var,
                                         values=ALL_STATUS_NAMES, width=12)
        self.status_combo.pack(side=tk.LEFT, padx=3)
        if ALL_STATUS_NAMES:
            self.status_combo.current(0)

        # X 输入（条件显示）
        self.x_label = ttk.Label(s_row1, text="X:")
        self.status_x_var = tk.IntVar(value=0)
        self.x_spinbox = ttk.Spinbox(s_row1, textvariable=self.status_x_var, from_=0, to=99, width=4)

        ttk.Button(s_row1, text="施加", command=self._apply_status, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Button(s_row1, text="清除全部", command=self._clear_current_status, width=8).pack(side=tk.LEFT, padx=2)

        # 状态变更时条件显示X
        self.status_combo.bind("<<ComboboxSelected>>", self._on_status_selected)
        self._on_status_selected()  # 初始状态

    # ---- 目标获取 ----
    def _get_target(self) -> Unit | None:
        if not self.unit_provider:
            return None
        # 优先选 Now，否则选左侧选中
        if self.combat_state and self.combat_state.active:
            cur_id = self.combat_state.current_unit_id
            if cur_id:
                return self.unit_provider.find_unit(cur_id)
        return self.unit_provider._get_selected_unit()

    # ---- 战斗操作 ----
    def _start_combat(self):
        if not self.unit_provider:
            return
        players = self.unit_provider.get_players()
        monsters = self.unit_provider.get_monsters()
        all_units = players + monsters

        if not all_units:
            messagebox.showinfo("提示", "请先添加至少一个单位")
            return

        mode = self.init_mode_var.get()

        if mode == "team":
            if not players or not monsters:
                messagebox.showinfo("提示", "团队先攻模式需要至少一个玩家和一个怪物")
                return
            self.combat_state = team_initiative(players, monsters)
            p_scores = sorted([u.speed for u in players])
            m_scores = sorted([u.speed for u in monsters])
            p_team = (max(p_scores) + min(p_scores)) if len(p_scores) >= 2 else (p_scores[0] * 2 if p_scores else 0)
            m_team = (max(m_scores) + min(m_scores)) if len(m_scores) >= 2 else (m_scores[0] * 2 if m_scores else 0)
            self.team_score_label.config(
                text=f"玩家团队值: {p_team} | 怪物团队值: {m_team} | "
                     f"{'玩家' if self.combat_state.first_team == 'player' else '怪物'}先动"
            )
        elif mode == "manual":
            first = self.manual_team_var.get()
            self.combat_state = manual_initiative(first, players, monsters)
            self.team_score_label.config(
                text=f"客观判断: {'玩家' if self.combat_state.first_team == 'player' else '怪物'}先行")
        else:
            self.combat_state = traditional_initiative(all_units, self.dice_var.get())
            rolls = self.combat_state.initiative_rolls
            lines = []
            for uid, roll in sorted(rolls.items(), key=lambda x: x[1], reverse=True):
                unit = self.unit_provider.find_unit(uid)
                name = unit.name if unit else uid
                lines.append(f"{name}: d{self.dice_var.get()}+{unit.speed if unit else '?'}={roll}")
            self.team_score_label.config(text=" | ".join(lines))

        self._update_ui_state()
        self._refresh_order_list()

    def _next_action(self):
        if not self.combat_state or not self.combat_state.active:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = next_actor(self.combat_state, all_units)
        for msg in messages:
            self._log_message(msg)
        self._update_ui_state()
        self._refresh_order_list()

    def _end_turn(self):
        if not self.combat_state:
            return
        all_units = self.unit_provider.units if self.unit_provider else []
        state, messages = advance_turn(self.combat_state, all_units)
        for msg in messages:
            self._log_message(msg)
        self._update_ui_state()
        self._refresh_order_list()

    def _end_combat(self):
        if not self.combat_state:
            return
        if messagebox.askyesno("结束战斗", f"确定要在第 {self.combat_state.turn} 回合结束战斗吗？"):
            self.combat_state.active = False
            self.combat_state = None
            self.turn_label.config(text="Turn: --")
            self.now_label.config(text="Now: --")
            self.team_score_label.config(text="")
            self.order_list.delete(0, tk.END)
            self.start_btn.config(state=tk.NORMAL)
            self.next_btn.config(state=tk.DISABLED)
            self.end_turn_btn.config(state=tk.DISABLED)
            self.end_combat_btn.config(state=tk.DISABLED)

    # ---- 伤害 / 治疗 ----
    def _apply_damage(self):
        target = self._get_target()
        if not target:
            messagebox.showinfo("提示", "请先在左侧选择一个目标单位")
            return

        amount = self.dmg_amount_var.get()
        dmg_type = self.dmg_type_var.get()
        is_attack = self.is_attack_var.get()

        if dmg_type == "治疗":
            msg = apply_healing(target, amount)
        else:
            msg = apply_damage(target, amount, dmg_type, is_attack)

        self._log_message(msg)
        self.unit_provider._refresh_trees()
        self._refresh_order_list()

    # ---- 元素损伤 ----
    def _apply_elem_dmg(self):
        target = self._get_target()
        if not target:
            messagebox.showinfo("提示", "请先在左侧选择一个目标单位")
            return

        amount = self.elem_amount_var.get()
        elem_type = self.elem_type_var.get()
        msg = apply_elemental_damage(target, amount, elem_type)
        self._log_message(msg)
        self.unit_provider._refresh_trees()
        self._refresh_order_list()

    # ---- 状态 ----
    def _apply_status(self):
        target = self._get_target()
        if not target:
            messagebox.showinfo("提示", "请先在左侧选择一个目标单位")
            return

        status_name = self.apply_status_var.get()
        if not status_name:
            return

        stacks = self.status_x_var.get() if status_name in X_STATUSES else 0
        msg = apply_status(target, status_name, stacks)
        self._log_message(msg)
        self.unit_provider._refresh_trees()
        self._refresh_order_list()

    def _clear_current_status(self):
        target = self._get_target()
        if not target:
            messagebox.showinfo("提示", "请先在左侧选择一个目标单位")
            return

        removed = clear_all_statuses(target)
        if removed:
            self._log_message(f"{target.name} 清除了全部状态: {'、'.join(removed)}")
        else:
            self._log_message(f"{target.name} 无状态可清除")
        self.unit_provider._refresh_trees()
        self._refresh_order_list()

    # ---- UI 刷新 ----
    def _update_ui_state(self):
        if not self.combat_state or not self.combat_state.active:
            return

        self.turn_label.config(text=f"Turn: {self.combat_state.turn}")
        cur_id = self.combat_state.current_unit_id
        if cur_id and self.unit_provider:
            unit = self.unit_provider.find_unit(cur_id)
            self.now_label.config(text=f"Now: {unit.name if unit else cur_id}")
        else:
            self.now_label.config(text="Now: --")

        self.start_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL)
        self.end_turn_btn.config(state=tk.NORMAL)
        self.end_combat_btn.config(state=tk.NORMAL)

    def _refresh_order_list(self):
        self.order_list.delete(0, tk.END)
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
            self.order_list.insert(tk.END, line)

            if i == self.combat_state.now_index:
                self.order_list.itemconfig(tk.END, bg="#d4e6f1")

    def _on_status_selected(self, event=None):
        """选中带X的状态时显示X输入，否则隐藏"""
        status = self.apply_status_var.get()
        if status in X_STATUSES:
            self.x_label.pack(side=tk.LEFT, padx=(5, 0))
            self.x_spinbox.pack(side=tk.LEFT, padx=3)
        else:
            self.x_label.pack_forget()
            self.x_spinbox.pack_forget()
            self.status_x_var.set(0)

    def _log_message(self, msg: str):
        for line in msg.split("\n"):
            print(f"[战斗日志] {line}")
