"""qfluentwidgets 迁移集成冒烟测试（offscreen）。

覆盖：迁移后公共组件的构造与基本操作、ComboBox userData 回归、
消息框 helper 的 parent 约束、TabWidget fade no-op、Mica 降级、
主题 API 冒烟与 section_label helper。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QSplitter,
    QTreeWidgetItem,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    ComboBox,
    EditableComboBox,
    InfoBar,
    InfoBarIcon,
    ListWidget,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SpinBox,
    TabWidget,
    TreeWidget,
    setTheme,
    setThemeColor,
    Theme,
)

from models import THEME
from ui.combat_panel import CombatPanel
from ui.fluent import (
    danger_button,
    enable_mica,
    info_box,
    install_tab_fade,
    section_label,
)
from ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_qfw_components_smoke():
    """迁移后的 qfw 组件可 offscreen 构造，基本操作不抛异常。"""
    _app()
    widgets = [
        PushButton("按钮"),
        PrimaryPushButton("主按钮"),
        ComboBox(),
        SpinBox(),
        CheckBox("勾选"),
        TabWidget(),
        TreeWidget(),
        ListWidget(),
        CardWidget(),
        EditableComboBox(),
        SearchLineEdit(),
    ]
    try:
        widgets[0].setText("改")
        assert widgets[0].text() == "改"
        widgets[1].setText("主改")
        assert widgets[1].text() == "主改"
        widgets[2].addItem("a")
        assert widgets[2].count() == 1
        widgets[3].setValue(5)
        assert widgets[3].value() == 5
        widgets[4].setChecked(True)
        assert widgets[4].isChecked()
        tabs = widgets[5]
        tabs.addTab(QLabel("页"), "页")
        assert tabs.count() == 1
        widgets[6].addTopLevelItem(QTreeWidgetItem(["a"]))
        assert widgets[6].topLevelItemCount() == 1
        widgets[7].addItem("a")
        assert widgets[7].count() == 1
        widgets[9].setCurrentText("x")  # qfw：无此项时 no-op，不抛异常
        widgets[10].setText("查询")
        assert widgets[10].text() == "查询"
    finally:
        for w in widgets:
            w.close()

    # InfoBar 构造参数与普通组件不同，单独构造并断言标题
    bar = InfoBar(
        InfoBarIcon.SUCCESS, "标题", "内容", Qt.Horizontal, True, 1000, None, None
    )
    try:
        assert bar.title == "标题"
    finally:
        bar.close()


def test_combo_user_data_roundtrip():
    """回归：ComboBox userData 修正（b770e40）后 currentData 往返一致。"""
    _app()
    combo = ComboBox()
    try:
        combo.addItem("a", userData="x")
        assert combo.currentData() == "x"
        combo.addItem("b", userData="y")
        combo.setCurrentIndex(1)
        assert combo.currentData() == "y"
    finally:
        combo.close()

    editable = EditableComboBox()
    try:
        editable.addItem("自定义")
        editable.setCurrentText("自定义")
        assert editable.currentText() == "自定义"
    finally:
        editable.close()


def test_message_box_helper_requires_parent(monkeypatch):
    """info_box 强制非 None parent；有 parent 时构造成功（stub exec）。"""
    _app()
    # parent=None 必须在 exec 前拒绝
    with pytest.raises(ValueError):
        info_box(None, "标题", "内容")

    # stub exec 防止 offscreen 下进入模态事件循环（仅验证构造链路）
    monkeypatch.setattr(MessageBox, "exec", lambda self: 0)
    parent = QWidget()
    try:
        info_box(parent, "标题", "内容")  # 构造 + 按钮文案，不抛异常
    finally:
        parent.close()


def test_install_tab_fade_noop_on_qfw_tabwidget():
    """qfw TabWidget 非 QTabWidget 子类，install_tab_fade 必须安全 no-op。"""
    _app()
    tabs = TabWidget()
    try:
        tabs.addTab(QLabel("a"), "页一")
        install_tab_fade(tabs)
        tabs.addTab(QLabel("b"), "页二")
        install_tab_fade(tabs)  # 再次调用同样不抛
        assert tabs.count() == 2
    finally:
        tabs.close()


def test_enable_mica_returns_false_on_offscreen():
    """enable_mica 在非 win32 / offscreen 下不抛异常（通常返回 False）。"""
    _app()
    window = QWidget()
    try:
        result = enable_mica(window)
        assert isinstance(result, bool)
    finally:
        window.close()


def test_theme_apis_smoke():
    """setTheme / setThemeColor 冒烟；结束后恢复全局主题。"""
    _app()
    try:
        setTheme(Theme.DARK)
        setThemeColor(QColor("#009faa"))
        setTheme(Theme.LIGHT)
    finally:
        setTheme(Theme.LIGHT)  # 恢复，避免污染其他测试的全局状态


def test_danger_button_matches_default_button_metrics():
    """危险按钮与普通按钮尺寸一致，且常态为红底白字（非透明）。"""
    _app()
    danger = danger_button("删除")
    plain = PushButton("普通")
    try:
        # 尺寸回归：删除 min-height/padding/border 后完全继承 qfw 默认尺寸
        assert danger.sizeHint().height() == plain.sizeHint().height()
        assert danger.sizeHint().width() == plain.sizeHint().width()
        # 底色回归：亮色 QSS 必须含红底（非 transparent）
        light_qss = danger.property("lightCustomQss") or ""
        assert f"background: {THEME['danger']}" in light_qss
        assert "background: transparent" not in light_qss
    finally:
        danger.close()
        plain.close()


def test_splitter_handle_stylesheet():
    """回归：分栏分隔条着色（全局 QSS 删除后分界线缺失）。

    用未初始化的 MainWindow 实例直接调用 _style_splitter_handles，
    避免 offscreen 下完整构造主窗口（数据/规则目录加载）的开销。
    """
    _app()
    main_splitter = QSplitter(Qt.Horizontal)
    work_splitter = QSplitter(Qt.Vertical)
    window = MainWindow.__new__(MainWindow)
    window.splitter = main_splitter
    window.work_splitter = work_splitter
    try:
        window._style_splitter_handles()
        light_qss = main_splitter.styleSheet()
        assert "QSplitter::handle" in light_qss
        assert "#d8d8d8" in light_qss  # 亮色分隔条
        assert work_splitter.styleSheet() == light_qss

        # 幂等：重复调用（主题切换触发）样式保持一致
        window._style_splitter_handles()
        assert main_splitter.styleSheet() == light_qss

        # 暗色主题使用暗色分隔条
        setTheme(Theme.DARK)
        try:
            window._style_splitter_handles()
            dark_qss = main_splitter.styleSheet()
            assert "QSplitter::handle" in dark_qss
            assert "#3a3a3a" in dark_qss
        finally:
            setTheme(Theme.LIGHT)
    finally:
        main_splitter.close()
        work_splitter.close()


def test_combat_panel_target_context_is_card():
    """回归：目标栏由无样式 QFrame 改为 CardWidget，恢复卡片观感。"""
    _app()
    panel = CombatPanel()
    try:
        target_labels = [l for l in panel.findChildren(QLabel) if l.text() == "目标"]
        assert target_labels, "CombatPanel 应包含『目标』标签"
        container = target_labels[0].parentWidget()
        assert isinstance(container, CardWidget)
        assert container.objectName() != "TargetContext"  # 旧 objectName 对应 QSS 已删
    finally:
        panel.close()
        # 排空 qfw 组件构造/销毁遗留的 pending 事件，避免事件队列饥饿
        # 后续 test_ui_motion 的 30ms 动画测试（QTest.qWait(60) 硬超时）
        for _ in range(3):
            QApplication.processEvents()


def test_section_label_returns_label():
    """section_label 返回标题容器，内部 QLabel（StrongBodyLabel）文本正确。

    注意：section_label 实际返回 QWidget 容器（含 stretch 布局，调用方以
    addWidget 使用），文本由内部的 StrongBodyLabel（QLabel 子类）承载。
    """
    _app()
    widget = section_label("标题")
    try:
        assert isinstance(widget, QWidget)
        labels = widget.findChildren(QLabel)
        assert labels and labels[0].text() == "标题"
    finally:
        widget.close()
