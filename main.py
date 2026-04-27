"""WIT 战斗管理器 - Walk In the Terra

专为明日方舟跑团规则（WIT）设计的战斗管理工具。
"""

import ctypes
import sys
import tkinter as tk
from ui.main_window import MainWindow


def _fix_dpi():
    """修复 Windows 高 DPI 下文字模糊问题"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PerMonitorV2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # SystemAware
        except Exception:
            pass


def main():
    _fix_dpi()
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
