"""Shared Fluent styling helpers for the PySide6 interface.

该模块负责两件事：
1. qfluentwidgets 主题系统初始化（apply_fluent_style / _init_qfw）；
2. 提供与旧自研 QSS 体系兼容的公共 helper（section_label、danger_button、
   info_box / warn_box / question_box、动画、滚轮保护等）。

全局 QSS 已随 _stylesheet() 的删除而移除；控件观感改由 qfluentwidgets
主题（含 Theme.AUTO 跟随系统）与 setCustomStyleSheet 局部样式承担。
"""

import os
import platform
import re
import sys
import warnings

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QGraphicsOpacityEffect,
    QPushButton,
    QStyle,
    QTabWidget,
    QWidget,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from qfluentwidgets import (
    BodyLabel,
    MessageBox,
    PushButton,
    StrongBodyLabel,
    Theme,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
    setTheme,
    setThemeColor,
)
from qfluentwidgets.components.widgets.combo_box import ComboBoxBase

from app_paths import writable_data_dir
from models import THEME


# 暗色主题 palette（与亮色 THEME 同构派生；仅用于 _apply_palette_for_theme）
THEME_DARK = {
    "window_bg": "#1f1f1f",
    "surface": "#2b2b2b",
    "surface_alt": "#262626",
    "surface_translucent": "rgba(43, 43, 43, 232)",
    "surface_alt_translucent": "rgba(38, 38, 38, 224)",
    "surface_hover": "rgba(50, 50, 50, 244)",
    "border": "#3c3c3c",
    "border_strong": "#555555",
    "hover_border": "#7a7a7a",
    "text": "#e0e0e0",
    "muted_text": "#9d9d9d",
    "accent": "#4cc2ff",
    "accent_hover": "#6ecfff",
    "accent_pressed": "#3aa0e0",
    "accent_text": "#1f1f1f",
    "danger": "#e5484d",
    "danger_hover": "#f2555a",
    "success": "#46a758",
    "disabled_bg": "#333333",
    "disabled_text": "#7a7a7a",
    "pressed_bg": "#343434",
    "scrollbar": "#5a5a5a",
    "subtle_fill": "rgba(255, 255, 255, 8)",
    "subtle_fill_hover": "rgba(255, 255, 255, 12)",
    "current_actor_bg": "#2a4a68",
    "monster_row_bg": "#4a2c2a",
    "ally_row_bg": "#2a4632",
}


def _rgba(color: str) -> QColor:
    """解析 'rgba(r, g, b, a)' 形式的颜色字符串（QColor 不直接支持该语法）。"""

    match = re.fullmatch(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
    if match:
        return QColor(*(int(part) for part in match.groups()))
    return QColor(color)


def _build_palette(theme: dict) -> QPalette:
    """按主题字典构建 QPalette（亮/暗两套共用同一映射，值逐项与旧实现一致）。"""

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme["window_bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme["text"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, _rgba(theme["subtle_fill"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(theme["accent_text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme["muted_text"]))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(theme["disabled_text"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(theme["disabled_text"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Window,
        QColor(theme["disabled_bg"]),
    )
    return palette


def _force_light_scheme(app: QApplication) -> None:
    """Force the Qt light color scheme and a matching light palette.

    Qt 6.8+ derives a dark palette from the Windows dark mode; pinning
    both the scheme and the palette keeps the base UI light until the
    qfluentwidgets theme system takes over (see _apply_palette_for_theme).
    """

    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Light)

    app.setPalette(_build_palette(THEME))


def _apply_palette_for_theme() -> None:
    """按 qconfig 当前主题应用对应 QPalette（Theme.AUTO 已解析为明/暗）。"""

    app = QApplication.instance()
    if app is None:
        return
    app.setPalette(_build_palette(THEME_DARK if isDarkTheme() else THEME))


class _WheelGuard(QObject):
    """Swallow wheel events over spin boxes / combo boxes unless focused."""

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel:
            return False
        # qfluentwidgets 的 ComboBox 不是 QComboBox 子类（ComboBoxBase + QPushButton）
        if not isinstance(watched, (QAbstractSpinBox, QComboBox, ComboBoxBase)):
            return False
        if watched.hasFocus():
            return False
        try:
            if isinstance(watched, QComboBox) and watched.view().isVisible():
                return False
        except Exception:
            # ComboBoxBase 无 view()，展开态由 popup 自身处理，这里直接放行
            pass
        return True


def install_wheel_guard(app: QApplication | None = None) -> None:
    """Install a one-time, app-wide guard against wheel mis-clicks.

    Unfocused spin boxes / combo boxes change values as soon as the cursor
    hovers them while the user scrolls a nearby log or list. The guard
    swallows those wheel events; focused widgets (and an open combo popup)
    keep normal wheel behavior.
    """

    app = app or QApplication.instance()
    if app is None or getattr(app, "_wit_wheel_guard", None) is not None:
        return
    guard = _WheelGuard(app)
    app.installEventFilter(guard)
    app._wit_wheel_guard = guard


def _init_qfw(app: QApplication) -> None:
    """初始化 qfluentwidgets 主题系统：配置加载、主题、主题色与 palette 同步。"""

    if getattr(app, "_wit_qfw_initialized", False):
        return
    qconfig.load(str(writable_data_dir() / "qfw_config.json"))
    setTheme(Theme.AUTO)
    setThemeColor(QColor(THEME["accent"]))
    qconfig.themeChangedFinished.connect(_apply_palette_for_theme)
    # setTheme 期间信号已发出过一次（连接尚未建立），这里主动同步首次状态
    _apply_palette_for_theme()
    app._wit_qfw_initialized = True


def apply_fluent_style(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is not None:
        _ensure_cjk_font(app)
        _force_light_scheme(app)
        install_wheel_guard(app)
        _init_qfw(app)


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
    """Deprecated shim：旧的 [role=...] 属性 QSS 已随全局样式移除。

    保留签名以兼容尚未迁移的调用点；请改用 danger_button() 或
    qfluentwidgets 自带的按钮样式。
    """

    warnings.warn(
        "set_button_role 已废弃：基于 [role=...] 属性的 QSS 已移除，"
        "请改用 ui.fluent.danger_button() 等专用构造器。",
        DeprecationWarning,
        stacklevel=2,
    )
    return button


def section_label(text: str, secondary: str | None = None) -> QWidget:
    container = QWidget()
    from PySide6.QtWidgets import QHBoxLayout

    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    title = StrongBodyLabel(text, container)
    title.setObjectName("SectionTitle")
    layout.addWidget(title)
    if secondary:
        detail = BodyLabel(secondary, container)
        detail.setObjectName("SecondaryText")
        layout.addWidget(detail)
    layout.addStretch()
    return container


def standard_icon(widget: QWidget, icon: QStyle.StandardPixmap):
    return widget.style().standardIcon(icon)


# ---------------------------------------------------------------- 危险按钮

_DANGER_LIGHT_QSS = """
QPushButton {{
    color: {danger};
    background: transparent;
    border: 1px solid {danger};
    border-radius: 6px;
    padding: 0 11px;
    min-height: 30px;
}}
QPushButton:hover {{
    color: #ffffff;
    background: {danger_hover};
    border-color: {danger_hover};
}}
QPushButton:pressed {{
    color: #ffffff;
    background: #9e2116;
    border-color: #9e2116;
}}
QPushButton:disabled {{
    color: {disabled_text};
    background: {disabled_bg};
    border-color: {border};
}}
"""

_DANGER_DARK_QSS = """
QPushButton {{
    color: {danger};
    background: transparent;
    border: 1px solid {danger};
    border-radius: 6px;
    padding: 0 11px;
    min-height: 30px;
}}
QPushButton:hover {{
    color: #ffffff;
    background: {danger_hover};
    border-color: {danger_hover};
}}
QPushButton:pressed {{
    color: #ffffff;
    background: #b02a30;
    border-color: #b02a30;
}}
QPushButton:disabled {{
    color: {disabled_text};
    background: {disabled_bg};
    border-color: {border};
}}
"""


def danger_button(text: str, parent: QWidget | None = None) -> PushButton:
    """创建红色系危险操作按钮（qfluentwidgets PushButton + 亮/暗两套自定义 QSS）。"""

    button = PushButton(text, parent)
    setCustomStyleSheet(
        button,
        _DANGER_LIGHT_QSS.format(
            danger=THEME["danger"],
            danger_hover=THEME["danger_hover"],
            disabled_text=THEME["disabled_text"],
            disabled_bg=THEME["disabled_bg"],
            border=THEME["border"],
        ),
        _DANGER_DARK_QSS.format(
            danger=THEME_DARK["danger"],
            danger_hover=THEME_DARK["danger_hover"],
            disabled_text=THEME_DARK["disabled_text"],
            disabled_bg=THEME_DARK["disabled_bg"],
            border=THEME_DARK["border"],
        ),
    )
    return button


# ---------------------------------------------------------------- 对话框

def _message_box(parent: QWidget, title: str, content: str) -> MessageBox:
    """构造 qfluentwidgets MessageBox；parent 必须非 None。"""

    if parent is None:
        raise ValueError(
            "信息框需要非 None 的 parent 窗口"
            "（qfluentwidgets MessageBox 的遮罩层依赖父窗口几何信息）"
        )
    return MessageBox(title, content, parent)


def info_box(parent: QWidget, title: str, content: str) -> None:
    """模态信息提示框。"""

    box = _message_box(parent, title, content)
    box.yesButton.setText("确定")
    box.hideCancelButton()
    box.exec()


def warn_box(parent: QWidget, title: str, content: str) -> None:
    """模态警告框。"""

    box = _message_box(parent, title, content)
    box.yesButton.setText("确定")
    box.hideCancelButton()
    box.exec()


def question_box(
    parent: QWidget,
    title: str,
    content: str,
    yes_text: str = "是",
    no_text: str = "否",
) -> bool:
    """模态确认框；返回 True 表示用户选择“是”（MessageBox.Accepted）。"""

    box = _message_box(parent, title, content)
    box.yesButton.setText(yes_text)
    box.cancelButton.setText(no_text)
    return box.exec() == MessageBox.Accepted


def enable_mica(window: QWidget) -> bool:
    """尝试为窗口启用 Win11 Mica 背景材质；非 Win11 或失败时返回 False。"""

    if sys.platform != "win32":
        return False
    try:
        build = int(platform.version().split(".")[2])
    except (IndexError, ValueError, AttributeError):
        return False
    if build < 22000:
        return False
    try:
        from qframelesswindow import WindowEffect

        WindowEffect().setMicaEffect(int(window.winId()))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 动画

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


def install_tab_fade(tab_widget: QTabWidget, duration: int = 220) -> None:
    """Fade only the newly selected tab page; tab geometry remains stable.

    仅对原生 QTabWidget 子类生效；qfluentwidgets 的 TabWidget 不是
    QTabWidget 子类（自绘标签页、无原生 currentChanged 语义），直接 no-op。
    """

    if not isinstance(tab_widget, QTabWidget):
        return
    if getattr(tab_widget, "_wit_tab_fade_installed", False):
        return

    def _on_changed(index: int):
        page = tab_widget.widget(index)
        if page is not None:
            fade_in(page, duration=duration, start_opacity=0.78)

    tab_widget.currentChanged.connect(_on_changed)
    tab_widget._wit_tab_fade_installed = True
    tab_widget._wit_tab_fade_callback = _on_changed
