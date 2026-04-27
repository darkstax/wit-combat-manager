"""TRPG 战斗管理器 - 单位添加/编辑弹窗"""

import tkinter as tk
from tkinter import ttk, messagebox
from models import Unit, POSITIVE_BUFFS, NEGATIVE_BUFFS


class UnitDialog(tk.Toplevel):
    """添加或编辑单位的弹窗"""

    def __init__(self, parent, unit: Unit = None):
        super().__init__(parent)
        self.result: Unit | None = None
        self.unit = unit or Unit()
        self.is_edit = unit is not None

        title = "编辑单位" if self.is_edit else "添加单位"
        self.title(title)
        self.geometry("440x680")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_form()
        self._load_unit_data()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _sep(self, row):
        ttk.Separator(self.form, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)

    def _build_form(self):
        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self.form = ttk.Frame(canvas)

        self.form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.form, anchor=tk.NW, width=400)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._mw_binding = _on_mousewheel

        r = 0  # row

        # ==== 基本信息 ====
        ttk.Label(self.form, text="名称", font=("", 9, "bold")).grid(row=r, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(self.form, textvariable=self.name_var, width=28).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="类型").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.type_var = tk.StringVar(value="player")
        ttk.Combobox(self.form, textvariable=self.type_var, values=["player", "monster"], state="readonly", width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        self._sep(r); r += 1

        # ==== 血量 ====
        for label, var_name in [("当前血量", "current_hp_var"), ("最大血量", "max_hp_var"), ("临时HP", "temp_hp_var")]:
            ttk.Label(self.form, text=label).grid(row=r, column=0, sticky=tk.W, pady=2)
            setattr(self, var_name, tk.IntVar(value=10 if "hp" in var_name.lower() else 0))
            ttk.Spinbox(self.form, textvariable=getattr(self, var_name), from_=0, to=9999, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
            r += 1
        self._sep(r); r += 1

        # ==== 战斗属性 ====
        ttk.Label(self.form, text="速度").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.speed_var = tk.IntVar(value=10)
        ttk.Spinbox(self.form, textvariable=self.speed_var, from_=0, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="重量").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.weight_var = tk.IntVar(value=0)
        ttk.Spinbox(self.form, textvariable=self.weight_var, from_=-99, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="物理抗性").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.phys_res_var = tk.IntVar(value=0)
        ttk.Spinbox(self.form, textvariable=self.phys_res_var, from_=-99, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="法术抗性").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.magic_res_var = tk.IntVar(value=0)
        ttk.Spinbox(self.form, textvariable=self.magic_res_var, from_=-99, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="护甲类型").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.armor_var = tk.StringVar(value="轻甲")
        ttk.Combobox(self.form, textvariable=self.armor_var, values=["轻甲", "中甲", "重甲", "无甲"], width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        self._sep(r); r += 1

        # ==== 元素韧性 ====
        ttk.Label(self.form, text="精英化阶段").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.elite_var = tk.IntVar(value=0)
        ttk.Combobox(self.form, textvariable=self.elite_var, values=[0, 1, 2], state="readonly", width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.form, text="韧性上限: 精零=6  精一=9  精二=12", font=("", 7)).grid(row=r + 1, column=1, sticky=tk.W)
        r += 2

        ttk.Label(self.form, text="元素韧性(当前)").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.tenacity_cur_var = tk.IntVar(value=6)
        ttk.Spinbox(self.form, textvariable=self.tenacity_cur_var, from_=0, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1

        ttk.Label(self.form, text="元素韧性(上限)").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.tenacity_max_var = tk.IntVar(value=6)
        ttk.Spinbox(self.form, textvariable=self.tenacity_max_var, from_=0, to=99, width=26).grid(row=r, column=1, sticky=tk.EW, pady=2)
        r += 1
        self._sep(r); r += 1

        # ==== 状态效果（可折叠） ====
        self.buff_visible = tk.BooleanVar(value=False)

        ttk.Button(self.form, text="+ 展开正面/负面 BUFF", command=self._toggle_buffs,
                   width=30).grid(row=r, column=0, columnspan=2, pady=2)
        r += 1

        # 正面BUFF容器
        self.pos_container = ttk.Frame(self.form)
        self.pos_container.grid(row=r, column=0, columnspan=2, sticky=tk.EW)
        ttk.Label(self.pos_container, text="正面BUFF", font=("", 8, "bold")).pack(anchor=tk.W)
        pos_frame = ttk.Frame(self.pos_container)
        pos_frame.pack(fill=tk.X)
        self.positive_vars: dict[str, tk.BooleanVar] = {}
        for i, s in enumerate(POSITIVE_BUFFS):
            var = tk.BooleanVar(value=False)
            self.positive_vars[s] = var
            ttk.Checkbutton(pos_frame, text=s, variable=var).grid(row=i // 3, column=i % 3, sticky=tk.W, padx=2)
        r += 1

        # 负面BUFF容器
        self.neg_container = ttk.Frame(self.form)
        self.neg_container.grid(row=r, column=0, columnspan=2, sticky=tk.EW)
        ttk.Label(self.neg_container, text="负面BUFF / 状态", font=("", 8, "bold")).pack(anchor=tk.W, pady=(8, 0))
        neg_frame = ttk.Frame(self.neg_container)
        neg_frame.pack(fill=tk.X)
        self.negative_vars: dict[str, tk.BooleanVar] = {}
        for i, s in enumerate(NEGATIVE_BUFFS):
            var = tk.BooleanVar(value=False)
            self.negative_vars[s] = var
            ttk.Checkbutton(neg_frame, text=s, variable=var).grid(row=i // 3, column=i % 3, sticky=tk.W, padx=2)
        r += 1

        # 默认隐藏
        self.pos_container.grid_remove()
        self.neg_container.grid_remove()

        # 按钮
        btn_frame = ttk.Frame(self.form)
        btn_frame.grid(row=r, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="保存", command=self._on_save, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy, width=12).pack(side=tk.LEFT, padx=5)

    def _toggle_buffs(self):
        if self.buff_visible.get():
            self.pos_container.grid_remove()
            self.neg_container.grid_remove()
            self.buff_visible.set(False)
        else:
            self.pos_container.grid()
            self.neg_container.grid()
            self.buff_visible.set(True)

    def _load_unit_data(self):
        u = self.unit
        self.name_var.set(u.name)
        self.type_var.set(u.unit_type)
        self.current_hp_var.set(u.current_hp)
        self.max_hp_var.set(u.max_hp)
        self.temp_hp_var.set(u.temp_hp)
        self.speed_var.set(u.speed)
        self.weight_var.set(u.weight)
        self.phys_res_var.set(u.physical_resist)
        self.magic_res_var.set(u.magic_resist)
        self.armor_var.set(u.armor_type)
        self.elite_var.set(u.elite_stage)
        self.tenacity_cur_var.set(u.elemental_tenacity_current)
        self.tenacity_max_var.set(u.elemental_tenacity_max)

        for s in POSITIVE_BUFFS:
            self.positive_vars[s].set(u.has_status(s))
        for s in NEGATIVE_BUFFS:
            self.negative_vars[s].set(u.has_status(s))

    def _on_save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("验证失败", "请输入单位名称")
            return
        if self.current_hp_var.get() < 0 or self.max_hp_var.get() <= 0:
            messagebox.showwarning("验证失败", "血量设置不合法")
            return

        self.unit.name = name
        self.unit.unit_type = self.type_var.get()
        self.unit.current_hp = self.current_hp_var.get()
        self.unit.max_hp = self.max_hp_var.get()
        self.unit.temp_hp = self.temp_hp_var.get()
        self.unit.speed = self.speed_var.get()
        self.unit.weight = self.weight_var.get()
        self.unit.physical_resist = self.phys_res_var.get()
        self.unit.magic_resist = self.magic_res_var.get()
        self.unit.armor_type = self.armor_var.get()
        self.unit.elite_stage = self.elite_var.get()
        self.unit.elemental_tenacity_current = self.tenacity_cur_var.get()
        self.unit.elemental_tenacity_max = self.tenacity_max_var.get()

        # 更新状态
        new_effects = []
        for s in POSITIVE_BUFFS + NEGATIVE_BUFFS:
            if self.positive_vars.get(s, tk.BooleanVar(value=False)).get() or \
               self.negative_vars.get(s, tk.BooleanVar(value=False)).get():
                existing = self.unit.get_status(s)
                stacks = existing["stacks"] if existing else 0
                new_effects.append({"name": s, "stacks": stacks})
        self.unit.status_effects = new_effects

        self.result = self.unit
        self.destroy()

    def destroy(self):
        try:
            self.form.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()
