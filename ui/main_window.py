"""TRPG 战斗管理器 - 主窗口"""

import tkinter as tk
from tkinter import ttk
from models import Unit
from persistence import save_data, load_data, DEFAULT_PATH
from ui.unit_panel import UnitPanel
from ui.combat_panel import CombatPanel


class MainWindow:
    """应用主窗口"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TRPG 战斗管理器")
        self.root.geometry("900x650")
        self.root.minsize(800, 550)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        self._build_ui()

        # 加载数据
        self.units = load_data()
        self.unit_panel.load_units(self.units)
        self._update_status()

        # 保存事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 主分栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左栏：单位管理
        self.unit_panel = UnitPanel(paned, on_units_changed=self._on_units_changed)
        paned.add(self.unit_panel, weight=1)

        # 右栏：战斗控制
        self.combat_panel = CombatPanel(paned)
        self.combat_panel.set_unit_provider(self.unit_panel)
        paned.add(self.combat_panel, weight=2)

        # 日志区域
        log_frame = ttk.LabelFrame(self.root, text="战斗日志", padding=3)
        log_frame.pack(fill=tk.X, padx=5, pady=(0, 2))

        self.log_text = tk.Text(log_frame, height=4, state=tk.DISABLED, font=("Microsoft YaHei", 9))
        self.log_text.pack(fill=tk.X)
        log_scroll = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # 状态栏
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status_bar, textvariable=self.status_var, padding=(5, 2)).pack(side=tk.LEFT)

        # 拦截日志输出
        import sys
        self._old_stdout = sys.stdout
        sys.stdout = self._LogRedirector(self)

    def _on_units_changed(self, units: list[Unit]):
        self.units = units
        self._save()
        self._update_status()

    def _save(self):
        path = save_data(self.units)
        self.status_var.set(f"已保存到 {path}")

    def _update_status(self):
        p_count = sum(1 for u in self.units if u.unit_type == "player")
        m_count = sum(1 for u in self.units if u.unit_type == "monster")
        self.status_var.set(f"玩家: {p_count} | 怪物: {m_count} | 共 {len(self.units)} 单位")

    def _on_close(self):
        self._save()
        import sys
        sys.stdout = self._old_stdout
        self.root.destroy()

    def append_log(self, message: str):
        """向日志区域追加消息"""
        self.log_text.configure(state=tk.NORMAL)
        if self.log_text.get("1.0", tk.END).strip():
            self.log_text.insert(tk.END, "\n")
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    class _LogRedirector:
        """将 print 输出重定向到日志区域"""
        def __init__(self, window: "MainWindow"):
            self.window = window

        def write(self, message: str):
            msg = message.strip()
            if msg:
                self.window.root.after(0, lambda: self.window.append_log(msg))

        def flush(self):
            pass
