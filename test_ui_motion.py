import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget, QWidget

from ui.fluent import fade_in, install_tab_fade, motion_enabled, stop_animation


def _app():
    return QApplication.instance() or QApplication([])


def test_motion_can_be_disabled(monkeypatch):
    _app()
    monkeypatch.setenv("WIT_DISABLE_ANIMATIONS", "1")
    monkeypatch.delenv("WIT_ENABLE_ANIMATIONS", raising=False)
    widget = QLabel("stable")
    widget.show()

    assert motion_enabled() is False
    fade_in(widget)
    assert widget.graphicsEffect() is None
    assert widget.windowOpacity() == 1.0
    widget.close()


def test_fade_is_interruptible_and_restores_opacity(monkeypatch):
    _app()
    monkeypatch.delenv("WIT_DISABLE_ANIMATIONS", raising=False)
    monkeypatch.setenv("WIT_ENABLE_ANIMATIONS", "1")
    widget = QLabel("animated")
    widget.show()

    fade_in(widget, duration=30, start_opacity=0.4)
    fade_in(widget, duration=30, start_opacity=0.6)
    QTest.qWait(60)

    assert widget.graphicsEffect() is None
    assert getattr(widget, "_wit_opacity_animation", None) is None
    stop_animation(widget)
    widget.close()


def test_tab_fade_finishes_without_changing_layout(monkeypatch):
    _app()
    monkeypatch.delenv("WIT_DISABLE_ANIMATIONS", raising=False)
    monkeypatch.setenv("WIT_ENABLE_ANIMATIONS", "1")
    tabs = QTabWidget()
    first = QWidget()
    second = QWidget()
    tabs.addTab(first, "A")
    tabs.addTab(second, "B")
    tabs.resize(320, 180)
    tabs.show()
    install_tab_fade(tabs, duration=30)

    tabs.setCurrentIndex(1)
    QTest.qWait(60)

    assert tabs.currentWidget() is second
    assert second.graphicsEffect() is None
    assert second.isVisible()
    tabs.close()
