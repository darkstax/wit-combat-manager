"""TRPG 战斗管理器 - 主窗口 (PySide6)"""

import json
import os
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QGroupBox, QTextEdit,
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFileDialog, QSlider,
    QDialog, QPushButton, QApplication,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QAction, QPixmap, QPainter, QFont
from models import Unit
from persistence import save_data, load_data
from ui.unit_panel import UnitPanel
from ui.combat_panel import CombatPanel

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "settings.json")


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class LogSignal(QObject):
    message = Signal(str)


class BackgroundWidget(QWidget):
    """绘制水印背景图的自定义 Widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._opacity: float = 0.35

    def set_background(self, path: str | None, opacity: float = 0.35):
        if path and os.path.exists(path):
            self._pixmap = QPixmap(path)
            self._opacity = opacity
        else:
            self._pixmap = None
        self.update()

    def set_opacity(self, opacity: float):
        self._opacity = opacity
        if self._pixmap:
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        scaled = self._pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(0, 0, scaled)
        painter.end()


class WatermarkDialog(QDialog):
    """背景水印强度调节"""

    def __init__(self, current: float, parent=None):
        super().__init__(parent)
        self.result = None
        self.setWindowTitle("背景水印强度")
        self.setFixedSize(380, 170)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("背景图显示强度 (0.10=极淡 ~ 0.70=浓):"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 70)
        self.slider.setValue(int(current * 100))
        layout.addWidget(self.slider)

        self.value_label = QLabel(f"当前强度: {current:.2f}")
        self.value_label.setFont(QFont(self.value_label.font().family(), 14, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(f"当前强度: {v / 100:.2f}"))

        layout.addWidget(QLabel("（背景图仅在控件间隙可见）"))

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_save(self):
        self.result = self.slider.value() / 100.0
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WIT 战斗管理器 - Walk In the Terra")
        self.resize(960, 680)
        self.setMinimumSize(820, 560)

        self.units: list[Unit] = []
        self.settings = _load_settings()
        self._log_signal = LogSignal()
        self._log_signal.message.connect(self._append_log)

        self._build_ui()
        self._build_menu()
        self._apply_background()
        self._load_data()

    # ============================================================
    # 菜单
    # ============================================================

    def _build_menu(self):
        bar = self.menuBar()
        settings_menu = bar.addMenu("设置")

        bg_action = QAction("设置背景图片...", self)
        bg_action.triggered.connect(self._set_background)
        settings_menu.addAction(bg_action)

        clear_bg_action = QAction("清除背景图片", self)
        clear_bg_action.triggered.connect(self._clear_background)
        settings_menu.addAction(clear_bg_action)

        watermark_action = QAction("背景水印强度...", self)
        watermark_action.triggered.connect(self._set_watermark)
        settings_menu.addAction(watermark_action)

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        # 背景层 + 内容层 共享同一个 central widget
        central = QWidget()
        self.setCentralWidget(central)
        # 不使用 layout — 手动管理背景层和内容层的位置
        central.resizeEvent = self._on_central_resize

        # 背景绘制 Widget（填满整个 central）
        self.bg_widget = BackgroundWidget(central)
        self.bg_widget.setGeometry(0, 0, central.width(), central.height())
        self.bg_widget.lower()

        # 内容 Widget（盖在背景上面）
        self.content = QWidget(central)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)
        self.unit_panel = UnitPanel()
        self.unit_panel.units_changed.connect(self._on_units_changed)
        splitter.addWidget(self.unit_panel)
        self.combat_panel = CombatPanel()
        self.combat_panel.set_unit_provider(self.unit_panel)
        splitter.addWidget(self.combat_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        log_group = QGroupBox("战斗日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(110)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group, 0)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

        import sys
        self._old_stdout = sys.stdout
        sys.stdout = self._LogRedirector(self)

    def _on_central_resize(self, event):
        """central 大小变化时，同步背景层和内容层"""
        w = self.centralWidget().width()
        h = self.centralWidget().height()
        self.bg_widget.setGeometry(0, 0, w, h)
        self.content.setGeometry(0, 0, w, h)

    # ============================================================
    # 背景
    # ============================================================

    def _set_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)"
        )
        if not path:
            return
        self.settings["bg_image"] = path
        _save_settings(self.settings)
        self._apply_background()

    def _clear_background(self):
        self.settings.pop("bg_image", None)
        _save_settings(self.settings)
        self.bg_widget.set_background(None)

    def _set_watermark(self):
        current = self.settings.get("bg_opacity", 0.35)
        dlg = WatermarkDialog(current, self)
        if dlg.exec() == QDialog.Accepted and dlg.result is not None:
            self.settings["bg_opacity"] = dlg.result
            _save_settings(self.settings)
            self.bg_widget.set_opacity(dlg.result)

    def _apply_background(self):
        path = self.settings.get("bg_image", "")
        opacity = self.settings.get("bg_opacity", 0.35)
        self.bg_widget.set_background(path or None, opacity)

    # ============================================================
    # 数据
    # ============================================================

    def _load_data(self):
        self.units = load_data()
        self.unit_panel.load_units(self.units)
        self._update_status()

    def _on_units_changed(self, units: list[Unit]):
        self.units = units
        self._save()
        self._update_status()

    def _save(self):
        path = save_data(self.units)
        self.status_label.setText(f"已保存到 {path}")

    def _update_status(self):
        p_count = sum(1 for u in self.units if u.unit_type == "player")
        m_count = sum(1 for u in self.units if u.unit_type == "monster")
        self.status_label.setText(f"玩家: {p_count} | 怪物: {m_count} | 共 {len(self.units)} 单位")

    def closeEvent(self, event):
        self._save()
        import sys
        sys.stdout = self._old_stdout
        super().closeEvent(event)

    # ============================================================
    # 日志
    # ============================================================

    def append_log(self, message: str):
        self._log_signal.message.emit(message)

    def _append_log(self, message: str):
        self.log_text.append(message)

    class _LogRedirector:
        def __init__(self, window: "MainWindow"):
            self.window = window

        def write(self, message: str):
            msg = message.strip()
            if msg:
                self.window.append_log(msg)

        def flush(self):
            pass
