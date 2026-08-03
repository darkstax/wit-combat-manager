import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QLabel, QScrollArea, QSplitter, QTabWidget, QWidget,
)
from qfluentwidgets import EditableComboBox

from models import Unit, RuleMode, CombatState
from ui.combat_panel import CombatPanel
from ui.fluent import fade_in, install_tab_fade, motion_enabled, stop_animation
from ui.unit_dialog import UnitDialog
from ui.unit_panel import UnitPanel


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
    assert isinstance(dialog.profession_combo, EditableComboBox)

    # qfw EditableComboBox 无 isEditable/insertPolicy；其 setCurrentText 只对
    # 列表内项生效（无 setEditText），故先 addItem 再选中，验证表单值能正确
    # 收集进 Unit（保留 collect 核心断言）
    dialog.profession_combo.addItem("自定义职业")
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
    """展开“修正”时主动重排垂直分栏，压缩下方日志区；收起后按展开前快照精确恢复。"""
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
    QApplication.processEvents()
    QApplication.processEvents()
    # 空 QTabWidget 的 sizeHint 极小，QSplitter 初始分配会让上方占满可用空间，
    # 展开后无余量可让位（与真实主窗口 [419, 277] 的初始分配不符）；
    # 故预设一个接近真实场景的初始分配，作为“展开前快照”基线。
    splitter.setSizes([419, 477])
    QApplication.processEvents()
    QApplication.processEvents()
    before = splitter.sizes()
    assert before[0] > 0 and before[1] > 0

    # 展开“修正”：QTimer.singleShot(0) 触发的主动重排生效，上方变高
    panel.damage_modifiers_toggle.setChecked(True)
    QApplication.processEvents()
    QApplication.processEvents()
    expanded = splitter.sizes()
    assert expanded[0] > before[0]
    assert expanded[1] >= log_tabs.minimumHeight()  # 日志区不被压过 120

    # 收起后按展开前快照精确恢复（QSplitter 对 setSizes 有 ±2px 取整，逐项允许偏差）
    panel.damage_modifiers_toggle.setChecked(False)
    QApplication.processEvents()
    QApplication.processEvents()
    restored = splitter.sizes()
    assert len(restored) == len(before)
    for r, b in zip(restored, before):
        assert abs(r - b) <= 2

    splitter.close()


def test_order_list_empty_state_placeholder_overlay():
    """行动顺序为空时显示居中灰色提示浮层（无占位 item），有数据时隐藏。"""
    _app()
    panel = CombatPanel()
    panel.show()
    try:
        # 未开始战斗（combat_state 为 None）：浮层提示且列表无占位 item
        panel._refresh_order_list()
        assert panel.order_list.count() == 0
        assert panel.order_placeholder.isVisible()
        assert "开始战斗" in panel.order_placeholder.text()

        # combat_state 存在但 turn_order 为空：同样显示浮层
        panel.combat_state = CombatState()
        panel._refresh_order_list()
        assert panel.order_list.count() == 0
        assert panel.order_placeholder.isVisible()
        assert "开始战斗" in panel.order_placeholder.text()

        # 有 turn_order 数据：浮层隐藏，列表正常填充
        provider = UnitPanel()
        provider.show()
        units = [Unit(name="甲"), Unit(name="乙")]
        provider.load_units(units)
        panel.unit_provider = provider
        panel.combat_state.turn_order = [u.unit_id for u in units]
        panel.combat_state.now_index = 0
        panel._refresh_order_list()
        assert panel.order_list.count() == 2
        assert not panel.order_placeholder.isVisible()
        provider.close()
    finally:
        panel.close()
        for _ in range(3):
            QApplication.processEvents()


def test_unit_tree_empty_state_placeholder():
    """单位树为空时显示提示浮层，有单位后隐藏。"""
    _app()
    panel = UnitPanel()
    panel.show()
    try:
        panel._refresh_tree()
        assert panel.tree.topLevelItemCount() == 0
        assert panel.tree_placeholder.isVisible()
        assert "添加" in panel.tree_placeholder.text()

        panel.load_units([Unit(name="测试单位")])
        assert panel.tree.topLevelItemCount() == 1
        assert not panel.tree_placeholder.isVisible()
    finally:
        panel.close()
        for _ in range(3):
            QApplication.processEvents()


def test_unit_panel_rule_mode_combo_emits_change():
    """单位面板的版本下拉框切换时发出 rule_mode_changed（值为 userData）。"""
    _app()
    panel = UnitPanel()
    panel.show()
    received = []
    panel.rule_mode_changed.connect(received.append)
    try:
        assert panel.rule_mode_combo.currentData() == RuleMode.V1_2.value
        index = panel.rule_mode_combo.findData(RuleMode.V0_3.value)
        panel.rule_mode_combo.setCurrentIndex(index)
        assert received == [RuleMode.V0_3.value]

        # set_combo_rule_mode 外部同步不触发信号（防递归）
        panel.set_combo_rule_mode(RuleMode.V1_2)
        assert received == [RuleMode.V0_3.value]
        assert panel.rule_mode_combo.currentData() == RuleMode.V1_2.value
    finally:
        panel.close()
        for _ in range(3):
            QApplication.processEvents()
