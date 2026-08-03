import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QLabel, QScrollArea, QSplitter, QTabWidget, QWidget,
)

from models import Unit, RuleMode
from ui.combat_panel import CombatPanel
from ui.fluent import fade_in, install_tab_fade, motion_enabled, stop_animation
from ui.unit_dialog import UnitDialog


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


def test_new_mode_save_and_continue_keeps_dialog_open():
    _app()
    dialog = UnitDialog(Unit(), rule_mode=RuleMode.V1_2)
    dialog.name_edit.setText("单位A")

    dialog._on_save_and_continue()

    assert len(dialog.saved_units) == 1
    assert dialog.saved_units[0].name == "单位A"
    assert dialog.name_edit.text() == ""
    assert dialog.result is None  # 未走 accept 路径，对话框未关闭
    assert dialog.is_edit is False


def test_edit_mode_save_appends_to_saved_units():
    _app()
    unit = Unit(name="已有单位")
    dialog = UnitDialog(unit)

    dialog._on_save()

    assert dialog.saved_units == [unit]
    assert dialog.result is unit
    assert dialog.is_edit is True


def test_edit_mode_has_no_save_and_continue_button():
    _app()
    dialog = UnitDialog(Unit(name="已有单位"))

    assert dialog.save_and_continue_button is None
    assert dialog.save_button.text() == "保存"
    assert dialog.is_edit is True


def test_profession_combo_editable_and_collect_keeps_text():
    _app()
    dialog = UnitDialog(Unit())
    assert dialog.profession_combo.isEditable()
    assert dialog.profession_combo.insertPolicy() == QComboBox.NoInsert

    dialog.profession_combo.setCurrentText("自定义职业")
    fresh = Unit()
    dialog._collect_unit(fresh)

    assert fresh.profession == "自定义职业"
    assert dialog.profession_combo.currentText() == "自定义职业"


def test_damage_modifiers_expand_increases_tabs_min_height():
    _app()
    panel = CombatPanel()
    panel.show()  # sizeHint 计算依赖布局激活，offscreen 下也需 show
    tabs = panel.operations_tabs
    base = tabs.minimumHeight()
    assert base == panel._ops_tabs_base_height

    # 展开“修正”：内容变多 → sizeHint 自然变大 → QSplitter 据此分配空间
    base_hint = tabs.sizeHint().height()
    panel.damage_modifiers_toggle.setChecked(True)
    QTest.qWait(20)  # 等待布局生效
    expanded_hint = tabs.sizeHint().height()
    assert expanded_hint > base_hint
    # 最小高度基线保持不变（不再动态抬高）
    assert tabs.minimumHeight() == base

    # 收起后 sizeHint 恢复
    panel.damage_modifiers_toggle.setChecked(False)
    QTest.qWait(20)
    assert tabs.sizeHint().height() == base_hint
    assert tabs.minimumHeight() == base

    panel.close()


def test_damage_modifiers_expand_resizes_splitter():
    """展开“修正”时主动重排垂直分栏，压缩下方日志区；收起后恢复。"""
    _app()
    splitter = QSplitter(Qt.Vertical)
    splitter.setChildrenCollapsible(False)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    panel = CombatPanel()
    scroll.setWidget(panel)
    splitter.addWidget(scroll)
    log_tabs = QTabWidget()
    log_tabs.setMinimumHeight(120)
    splitter.addWidget(log_tabs)
    splitter.resize(800, 900)
    splitter.show()
    panel.attach_splitter(splitter)
    QTest.qWait(20)  # 等待布局激活，基线高度生效
    # 收起状态主动对齐一次分栏到基线（attach 只记录基线不重排，
    # 初始按 sizeHint 比例的分配与基线略有偏差，先对齐保证断言精确）
    panel._sync_splitter_for_modifiers()
    collapsed = splitter.sizes()[0]
    # QSplitter 对 setSizes 有 ±2px 取整，不要求等于基线精确值；
    # 展开/收起走同一调用路径，相对断言是精确的
    assert collapsed > 0

    # 展开“修正”：QTimer.singleShot(0) 触发的主动重排生效，上方变高
    panel.damage_modifiers_toggle.setChecked(True)
    QTest.qWait(20)
    expanded = splitter.sizes()[0]
    assert expanded > collapsed
    assert splitter.sizes()[1] >= log_tabs.minimumHeight()  # 日志区不被压过 120

    # 收起后恢复基线分配
    panel.damage_modifiers_toggle.setChecked(False)
    QTest.qWait(20)
    assert splitter.sizes()[0] == collapsed

    splitter.close()
