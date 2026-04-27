"""WIT 战斗管理器 - Walk In the Terra

专为明日方舟跑团规则（WIT）设计的战斗管理工具。
"""

import tkinter as tk
from ui.main_window import MainWindow


def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
