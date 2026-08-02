"""Dark-mode palette forcing and wheel-misclick guard tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPalette, QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from ui.fluent import apply_fluent_style, install_wheel_guard


def _app():
    return QApplication.instance() or QApplication([])


def _wheel_event():
    return QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def _spinbox_host(value: int):
    """A visible spin box inside a shared host window (offscreen focus
    handling only works reliably for widgets on the same window)."""

    host = QWidget()
    layout = QVBoxLayout(host)
    spin = QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(value)
    layout.addWidget(spin)
    host.show()
    QApplication.processEvents()
    return host, spin


def test_apply_fluent_style_forces_light_scheme_and_palette(monkeypatch):
    app = _app()
    hints = app.styleHints()

    if hasattr(hints, "setColorScheme"):
        calls = []
        monkeypatch.setattr(
            hints, "setColorScheme", lambda scheme: calls.append(scheme)
        )
        apply_fluent_style(app)
        # offscreen 平台不追踪 color scheme（恒为 Unknown），这里以调用 spy 验证
        assert calls == [Qt.ColorScheme.Light]
    else:
        apply_fluent_style(app)

    palette = app.palette()
    assert palette.color(QPalette.ColorRole.Window).name() == "#f3f3f3"
    assert palette.color(QPalette.ColorRole.WindowText).name() == "#1a1a1a"
    assert palette.color(QPalette.ColorRole.Base).name() == "#f8f8f8"
    assert palette.color(QPalette.ColorRole.Text).name() == "#1a1a1a"
    assert palette.color(QPalette.ColorRole.Button).name() == "#f8f8f8"
    assert palette.color(QPalette.ColorRole.Highlight).name() == "#0067c0"
    assert palette.color(QPalette.ColorRole.HighlightedText).name() == "#ffffff"
    assert palette.color(QPalette.ColorRole.ToolTipBase).name() == "#ffffff"
    assert palette.color(QPalette.ColorRole.PlaceholderText).name() == "#616161"
    assert (
        palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
        == "#9d9d9d"
    )
    assert (
        palette.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window
        ).name()
        == "#e5e5e5"
    )


def test_apply_fluent_style_is_idempotent():
    app = _app()
    apply_fluent_style(app)
    apply_fluent_style(app)

    guard = getattr(app, "_wit_wheel_guard", None)
    assert guard is not None
    # 再次调用不重复安装（PySide6 未暴露 eventFilters()，以对象同一性验证）
    install_wheel_guard(app)
    assert getattr(app, "_wit_wheel_guard", None) is guard


def test_wheel_guard_swallows_wheel_on_unfocused_spinbox():
    app = _app()
    apply_fluent_style(app)
    host, spin = _spinbox_host(10)
    spin.clearFocus()
    QApplication.processEvents()
    assert not spin.hasFocus()

    QApplication.sendEvent(spin, _wheel_event())
    assert spin.value() == 10
    host.close()


def test_wheel_guard_allows_wheel_when_focused():
    app = _app()
    apply_fluent_style(app)
    host, spin = _spinbox_host(10)
    spin.setFocus()
    QApplication.processEvents()
    assert spin.hasFocus()

    QApplication.sendEvent(spin, _wheel_event())
    assert spin.value() == 11
    host.close()


def test_wheel_guard_ignores_plain_widgets():
    app = _app()
    apply_fluent_style(app)
    received = []

    class SpyLineEdit(QLineEdit):
        def wheelEvent(self, event):
            received.append(event)
            super().wheelEvent(event)

    line = SpyLineEdit("hello")
    line.show()
    line.clearFocus()
    QApplication.processEvents()

    QApplication.sendEvent(line, _wheel_event())
    assert len(received) == 1
    line.close()
