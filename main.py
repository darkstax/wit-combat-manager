"""TRPG 战斗管理器 - 入口

一个为跑团主持人设计的战斗管理工具，支持：
- 玩家和怪物角色数据管理
- 团队先攻 / 传统先攻 / 客观判断三种先攻模式
- 回合追踪（Turn / Now）
- 状态效果升级系统
"""

import tkinter as tk
from ui.main_window import MainWindow


def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
