"""TRPG 战斗管理器 - 单位列表面板（左侧）"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from models import Unit


class QuickImportDialog(tk.Toplevel):
    """快速导入弹窗：粘贴骰娘导出文本"""

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("快速导入角色")
        self.geometry("500x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="角色名称:").pack(anchor=tk.W)
        self.name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.name_var, width=40).pack(fill=tk.X, pady=(2, 8))

        ttk.Label(frame, text="粘贴骰娘导出文本:").pack(anchor=tk.W)
        self.text_widget = tk.Text(frame, height=10, width=55, font=("Microsoft YaHei", 9))
        self.text_widget.pack(fill=tk.BOTH, expand=True, pady=2)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="导入", command=self._on_import, width=12).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy, width=12).pack(side=tk.RIGHT)

    def _on_import(self):
        text = self.text_widget.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("提示", "请粘贴导入文本")
            return
        self.result = {"text": text, "name": self.name_var.get().strip() or "快速导入角色"}
        self.destroy()


class UnitPanel(ttk.Frame):
    """单位管理面板：玩家/怪物统一列表 + 详情显示"""

    def __init__(self, parent, on_units_changed=None):
        super().__init__(parent, padding=5)
        self.units: list[Unit] = []
        self.on_units_changed = on_units_changed

        # 类型筛选
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(filter_frame, text="筛选:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value="全部")
        for label, val in [("全部", "全部"), ("玩家", "player"), ("怪物", "monster")]:
            ttk.Radiobutton(filter_frame, text=label, variable=self.filter_var,
                            value=val, command=self._refresh_trees).pack(side=tk.LEFT, padx=5)

        # 统一列表
        columns = ("type", "name", "hp", "speed", "tenacity")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        self.tree.heading("type", text="类型")
        self.tree.heading("name", text="名称")
        self.tree.heading("hp", text="HP")
        self.tree.heading("speed", text="速度")
        self.tree.heading("tenacity", text="韧性")
        self.tree.column("type", width=45, anchor=tk.CENTER)
        self.tree.column("name", width=100)
        self.tree.column("hp", width=65, anchor=tk.CENTER)
        self.tree.column("speed", width=50, anchor=tk.CENTER)
        self.tree.column("tenacity", width=65, anchor=tk.CENTER)
        self.tree.pack(fill=tk.X)

        # 行颜色标记
        self.tree.tag_configure("player", background="#d4e6f1")
        self.tree.tag_configure("monster", background="#f5d4d4")

        # 详情面板
        detail_frame = ttk.LabelFrame(self, text="选中单位详情", padding=5)
        detail_frame.pack(fill=tk.X, pady=5)

        self.detail_text = tk.Text(detail_frame, height=12, width=32, state=tk.DISABLED,
                                   font=("Microsoft YaHei", 9))
        self.detail_text.pack(fill=tk.X)

        # 操作按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="添加玩家", command=lambda: self._add_unit("player"), width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加怪物", command=lambda: self._add_unit("monster"), width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="编辑单位", command=self._edit_unit, width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除单位", command=self._delete_unit, width=9).pack(side=tk.LEFT, padx=2)

        # 第二行：导入按钮
        import_frame = ttk.Frame(self)
        import_frame.pack(fill=tk.X, pady=(2, 5))
        ttk.Button(import_frame, text="导入角色卡 (xlsx)", command=self._import_card, width=18).pack(side=tk.LEFT, padx=2)
        ttk.Button(import_frame, text="快速导入 (文本)", command=self._import_quick_text, width=18).pack(side=tk.LEFT, padx=2)

        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_detail(self._get_selected_unit()))

    # ---- 数据加载 ----
    def load_units(self, units: list[Unit]):
        self.units = units
        self._refresh_trees()

    def _refresh_trees(self):
        self.tree.delete(*self.tree.get_children())
        f = self.filter_var.get()
        for u in self.units:
            if f != "全部" and u.unit_type != f:
                continue
            type_label = "玩家" if u.unit_type == "player" else "怪物"
            tag = u.unit_type
            self.tree.insert("", tk.END, iid=u.unit_id,
                             values=(type_label, u.name, f"{u.current_hp}/{u.max_hp}",
                                     u.speed, f"{u.elemental_tenacity_current}/{u.elemental_tenacity_max}"),
                             tags=(tag,))

    def _get_selected_unit(self) -> Unit | None:
        sel = self.tree.selection()
        if not sel:
            return None
        for u in self.units:
            if u.unit_id == sel[0]:
                return u
        return None

    # ---- 详情显示 ----
    def _show_detail(self, unit: Unit | None):
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        if not unit:
            self.detail_text.insert("1.0", "请选择一个单位")
            self.detail_text.configure(state=tk.DISABLED)
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
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.configure(state=tk.DISABLED)

    # ---- 按钮操作 ----
    def _add_unit(self, unit_type: str = "player"):
        from ui.unit_dialog import UnitDialog
        unit = Unit(unit_type=unit_type)
        dlg = UnitDialog(self.winfo_toplevel(), unit)
        self.wait_window(dlg)
        if dlg.result:
            self.units.append(dlg.result)
            self._refresh_trees()
            self._notify_change()

    def _edit_unit(self):
        unit = self._get_selected_unit()
        if not unit:
            messagebox.showinfo("提示", "请先选择一个单位")
            return
        from ui.unit_dialog import UnitDialog
        dlg = UnitDialog(self.winfo_toplevel(), unit)
        self.wait_window(dlg)
        if dlg.result:
            self._refresh_trees()
            self._show_detail(dlg.result)
            self._notify_change()

    def _delete_unit(self):
        unit = self._get_selected_unit()
        if not unit:
            messagebox.showinfo("提示", "请先选择一个单位")
            return
        if messagebox.askyesno("确认删除", f"确定要删除「{unit.name}」吗？"):
            self.units.remove(unit)
            self._refresh_trees()
            self._show_detail(None)
            self._notify_change()

    def _import_card(self):
        filepath = filedialog.askopenfilename(
            title="选择角色卡文件",
            filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")],
        )
        if not filepath:
            return

        try:
            from character_card import import_character_card
            unit = import_character_card(filepath)
        except FileNotFoundError:
            messagebox.showerror("导入失败", f"文件不存在: {filepath}")
            return
        except ValueError as e:
            messagebox.showerror("导入失败", str(e))
            return
        except Exception as e:
            messagebox.showerror("导入失败", f"无法解析角色卡:\n{e}")
            return

        if not unit.name or unit.name == "未命名角色":
            messagebox.showwarning("警告", "未能读取到角色名称，请手动编辑")

        self.units.append(unit)
        self._refresh_trees()
        self._notify_change()
        messagebox.showinfo("导入成功", f"已导入角色: {unit.name}\n"
                             f"HP: {unit.max_hp}  物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  "
                             f"精英: {unit.elite_stage}")

    def _import_quick_text(self):
        """快速导入：从骰娘导出文本中提取属性"""
        dlg = QuickImportDialog(self.winfo_toplevel())
        self.wait_window(dlg)
        if not dlg.result:
            return

        try:
            from character_card import import_from_quick_text
            unit = import_from_quick_text(dlg.result["text"], name=dlg.result["name"])
        except Exception as e:
            messagebox.showerror("导入失败", f"无法解析文本:\n{e}")
            return

        self.units.append(unit)
        self._refresh_trees()
        self._notify_change()
        messagebox.showinfo("导入成功", f"已导入角色: {unit.name}\n"
                             f"HP: {unit.max_hp}  物抗: {unit.physical_resist}  法抗: {unit.magic_resist}  "
                             f"速度: {unit.speed}  重量: {unit.weight}\n"
                             f"(精英化等级未包含在快速导入中，默认为0)")

    def _notify_change(self):
        if self.on_units_changed:
            self.on_units_changed(self.units)

    # ---- 公共方法 ----
    def get_players(self) -> list[Unit]:
        return [u for u in self.units if u.unit_type == "player"]

    def get_monsters(self) -> list[Unit]:
        return [u for u in self.units if u.unit_type == "monster"]

    def find_unit(self, unit_id: str) -> Unit | None:
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        return None
