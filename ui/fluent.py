"""Shared Fluent-inspired styling helpers for the PySide6 interface."""

import os

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QStyle,
    QTabWidget,
    QWidget,
)
from PySide6.QtGui import QFont, QFontDatabase

from models import THEME


PALETTE = {
    "app_bg": THEME["window_bg"],
    "surface": THEME["surface_translucent"],
    "surface_alt": THEME["surface_alt_translucent"],
    "surface_hover": THEME["surface_hover"],
    "text": THEME["text"],
    "text_secondary": THEME["muted_text"],
    "border": THEME["border"],
    "border_strong": THEME["border_strong"],
    "accent": THEME["accent"],
    "accent_hover": THEME["accent_hover"],
    "accent_pressed": THEME["accent_pressed"],
    "accent_text": THEME["accent_text"],
    "danger": THEME["danger"],
    "danger_hover": THEME["danger_hover"],
    "disabled_bg": THEME["disabled_bg"],
    "disabled_text": THEME["disabled_text"],
    "hover_border": THEME["hover_border"],
    "pressed_bg": THEME["pressed_bg"],
    "scrollbar": THEME["scrollbar"],
    "subtle_fill": THEME["subtle_fill"],
    "subtle_fill_hover": THEME["subtle_fill_hover"],
    "selection": THEME["current_actor_bg"],
    "monster": THEME["monster_row_bg"],
}


def _stylesheet() -> str:
    p = PALETTE
    return f"""
    QWidget {{
        color: {p['text']};
        font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QDialog, QWidget#AppSurface {{
        background: {p['app_bg']};
    }}
    QWidget#AppContent {{
        background: transparent;
    }}
    QFrame#CommandBar, QFrame#BattleCommandBar,
    QFrame#StatusPanel, QFrame#LogPanel, QFrame#TargetContext {{
        background: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 8px;
    }}
    QWidget#NavigationPane {{
        background: {p['surface']};
        border: 0;
        border-right: 1px solid {p['border']};
        border-radius: 0;
    }}
    QWidget#Workspace {{
        background: transparent;
        border: 0;
    }}
    QFrame#IntegratedTitleBar {{
        background: {p['surface']};
        border: 0;
        border-bottom: 1px solid {p['border']};
        border-radius: 0;
    }}
    QLabel#TitleBarTitle {{
        font-size: 16px;
        font-weight: 600;
    }}
    QLabel#AppTitle {{
        font-size: 19px;
        font-weight: 600;
    }}
    QLabel#PageTitle {{
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#SectionTitle {{
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#SecondaryText {{
        color: {p['text_secondary']};
    }}
    QLabel#StatusBadge {{
        background: {p['surface_alt']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 5px 9px;
        font-weight: 600;
    }}
    QGroupBox {{
        background: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        margin-top: 11px;
        padding: 12px 10px 10px 10px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {p['text']};
        background: {p['surface']};
    }}
    QPushButton, QToolButton {{
        min-height: 30px;
        padding: 0 11px;
        background: {p['surface_alt']};
        border: 1px solid {p['border_strong']};
        border-radius: 6px;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {p['surface_hover']};
        border-color: {p['hover_border']};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {p['pressed_bg']};
    }}
    QPushButton:focus, QToolButton:focus {{
        border: 2px solid {p['accent']};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {p['disabled_text']};
        background: {p['disabled_bg']};
        border-color: {p['border']};
    }}
    QPushButton[role="primary"] {{
        color: {p['accent_text']};
        background: {p['accent']};
        border-color: {p['accent']};
        font-weight: 600;
    }}
    QPushButton[role="primary"]:hover {{
        background: {p['accent_hover']};
        border-color: {p['accent_hover']};
    }}
    QPushButton[role="primary"]:pressed {{
        background: {p['accent_pressed']};
    }}
    QPushButton[role="danger"] {{
        color: {p['danger']};
    }}
    QPushButton[role="danger"]:hover {{
        color: {p['accent_text']};
        background: {p['danger_hover']};
        border-color: {p['danger_hover']};
    }}
    QPushButton[role="primary"]:disabled,
    QPushButton[role="danger"]:disabled {{
        color: {p['disabled_text']};
        background: {p['disabled_bg']};
        border-color: {p['border']};
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QListWidget, QTreeWidget {{
        background: {p['surface_alt']};
        border: 1px solid {p['border_strong']};
        border-radius: 6px;
        selection-background-color: {p['selection']};
        selection-color: {p['text']};
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        min-height: 30px;
        padding: 0 7px;
    }}
    QTabWidget#OperationsTabs QPushButton,
    QTabWidget#OperationsTabs QSpinBox,
    QTabWidget#OperationsTabs QDoubleSpinBox,
    QTabWidget#OperationsTabs QComboBox {{
        min-height: 32px;
    }}
    QTextEdit, QPlainTextEdit, QListWidget, QTreeWidget {{
        padding: 4px;
    }}
    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover,
    QDoubleSpinBox:hover, QComboBox:hover, QListWidget:hover, QTreeWidget:hover {{
        border-color: {p['hover_border']};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus, QListWidget:focus, QTreeWidget:focus {{
        border: 2px solid {p['accent']};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled,
    QComboBox:disabled, QListWidget:disabled, QTreeWidget:disabled {{
        color: {p['disabled_text']};
        background: {p['disabled_bg']};
        border-color: {p['border']};
    }}
    QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button {{
        border: 0;
        width: 22px;
    }}
    QTreeWidget, QListWidget {{
        alternate-background-color: {p['subtle_fill']};
        outline: 0;
    }}
    QTreeWidget::item, QListWidget::item {{
        min-height: 28px;
        border-radius: 3px;
        padding: 2px 4px;
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{
        background: {p['subtle_fill_hover']};
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {p['selection']};
        color: {p['text']};
    }}
    QHeaderView::section {{
        min-height: 29px;
        padding: 0 6px;
        background: {p['surface_alt']};
        border: 0;
        border-bottom: 1px solid {p['border']};
        color: {p['text_secondary']};
        font-weight: 600;
    }}
    QRadioButton {{
        min-height: 28px;
        padding: 0 10px;
        background: {p['surface_alt']};
        border: 1px solid {p['border']};
        border-radius: 6px;
    }}
    QRadioButton:hover {{
        background: {p['surface_hover']};
    }}
    QRadioButton:checked {{
        color: {p['accent_text']};
        background: {p['accent']};
        border-color: {p['accent']};
    }}
    QRadioButton::indicator {{
        width: 0;
        height: 0;
    }}
    QCheckBox {{
        min-height: 26px;
        spacing: 7px;
        padding-left: 2px;
    }}
    QTabWidget::pane {{
        background: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        top: -1px;
    }}
    QTabWidget#OperationsTabs::pane {{
        background: {p['surface']};
        border: 0;
        border-top: 1px solid {p['border']};
        border-radius: 0;
    }}
    QTabBar::tab {{
        min-height: 30px;
        padding: 0 14px;
        color: {p['text_secondary']};
        background: transparent;
        border: 0;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{
        background: {p['subtle_fill']};
    }}
    QTabBar::tab:selected {{
        color: {p['text']};
        border-bottom-color: {p['accent']};
        font-weight: 600;
    }}
    QMenuBar {{
        background: {p['app_bg']};
        border-bottom: 1px solid {p['border']};
    }}
    QMenuBar::item {{
        padding: 5px 10px;
        background: transparent;
    }}
    QMenuBar::item:selected, QMenu::item:selected {{
        background: {p['selection']};
    }}
    QMenu {{
        background: {THEME['surface']};
        border: 1px solid {p['border']};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 10px;
        border-radius: 4px;
    }}
    QStatusBar {{
        background: {p['app_bg']};
        border-top: 1px solid {p['border']};
        color: {p['text_secondary']};
    }}
    QSplitter::handle {{
        background: transparent;
        width: 8px;
        height: 8px;
    }}
    QSplitter::handle:hover {{
        background: {p['border']};
    }}
    QSplitter#WorkSplitter::handle:vertical {{
        background: transparent;
        border-top: 1px solid {p['border']};
        margin: 6px 0;
    }}
    QScrollBar:vertical {{
        width: 11px;
        background: transparent;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        min-height: 28px;
        background: {p['scrollbar']};
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p['hover_border']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0;
        background: transparent;
    }}
    QToolTip {{
        color: {p['text']};
        background: {THEME['surface']};
        border: 1px solid {p['border_strong']};
        border-radius: 6px;
        padding: 5px;
    }}
    """


def apply_fluent_style(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is not None:
        _ensure_cjk_font(app)
        app.setStyleSheet(_stylesheet())


def _ensure_cjk_font(app: QApplication) -> None:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
            return


def set_button_role(button: QPushButton, role: str) -> QPushButton:
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def section_label(text: str, secondary: str | None = None) -> QWidget:
    container = QWidget()
    from PySide6.QtWidgets import QHBoxLayout

    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    title = QLabel(text)
    title.setObjectName("SectionTitle")
    layout.addWidget(title)
    if secondary:
        detail = QLabel(secondary)
        detail.setObjectName("SecondaryText")
        layout.addWidget(detail)
    layout.addStretch()
    return container


def standard_icon(widget: QWidget, icon: QStyle.StandardPixmap):
    return widget.style().standardIcon(icon)


def motion_enabled() -> bool:
    """Return whether short decorative UI animations should run."""

    disabled = os.environ.get("WIT_DISABLE_ANIMATIONS", "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    forced = os.environ.get("WIT_ENABLE_ANIMATIONS", "").strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    app = QApplication.instance()
    return bool(app and app.platformName().lower() not in {"offscreen", "minimal"})


def stop_animation(widget: QWidget) -> None:
    """Stop a prior WIT opacity animation and restore a stable final state."""

    animation = getattr(widget, "_wit_opacity_animation", None)
    if animation is not None and animation.state() == QAbstractAnimation.Running:
        animation.stop()
    widget._wit_opacity_animation = None
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(None)


def fade_in(
    widget: QWidget,
    duration: int = 150,
    start_opacity: float = 0.72,
) -> None:
    """Apply a short, interruptible fade to an already visible widget."""

    stop_animation(widget)
    if not motion_enabled() or not widget.isVisible():
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(max(0.0, min(1.0, start_opacity)))
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(max(1, duration))
    animation.setStartValue(effect.opacity())
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    widget._wit_opacity_animation = animation

    def _finish():
        if getattr(widget, "_wit_opacity_animation", None) is animation:
            widget._wit_opacity_animation = None
            widget.setGraphicsEffect(None)

    animation.finished.connect(_finish)
    animation.start()


def pulse(widget: QWidget, duration: int = 130) -> None:
    """Briefly emphasize a status widget without changing its geometry."""

    fade_in(widget, duration=duration, start_opacity=0.58)


def animate_window_entrance(widget: QWidget, duration: int = 180) -> None:
    """Fade a top-level window in while keeping native frame behavior intact."""

    prior = getattr(widget, "_wit_window_animation", None)
    if prior is not None and prior.state() == QAbstractAnimation.Running:
        prior.stop()
    if not motion_enabled():
        widget.setWindowOpacity(1.0)
        return
    widget.setWindowOpacity(0.0)
    animation = QPropertyAnimation(widget, b"windowOpacity", widget)
    animation.setDuration(max(1, duration))
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    widget._wit_window_animation = animation

    def _finish():
        if getattr(widget, "_wit_window_animation", None) is animation:
            widget._wit_window_animation = None
            widget.setWindowOpacity(1.0)

    animation.finished.connect(_finish)
    animation.start()


def install_tab_fade(tab_widget: QTabWidget, duration: int = 140) -> None:
    """Fade only the newly selected tab page; tab geometry remains stable."""

    if getattr(tab_widget, "_wit_tab_fade_installed", False):
        return

    def _on_changed(index: int):
        page = tab_widget.widget(index)
        if page is not None:
            fade_in(page, duration=duration, start_opacity=0.78)

    tab_widget.currentChanged.connect(_on_changed)
    tab_widget._wit_tab_fade_installed = True
    tab_widget._wit_tab_fade_callback = _on_changed
