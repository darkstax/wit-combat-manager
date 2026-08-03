"""qfluentwidgets 迁移后的 CheckBox 样式回归测试。

旧的 app 级 QSS（含 checkbox indicator 指标覆写）已随迁移整体移除，
原 test_fluent_style_preserves_native_checkbox_indicator_metrics 的
断言语义已死。本文件重写为：qfluentwidgets CheckBox 可 offscreen
构造，系统样式指标保持有效（indicator 尺寸 > 0），文本读写正常。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStyle
from qfluentwidgets import CheckBox


def _app():
    return QApplication.instance() or QApplication([])


def test_qfw_checkbox_constructible_with_sane_indicator_metrics():
    _app()
    checkbox = CheckBox("测试")
    try:
        # 文本读写正常
        assert checkbox.text() == "测试"
        checkbox.setText("新文本")
        assert checkbox.text() == "新文本"

        # 系统样式指标保持有效：无 QSS 覆写，indicator 尺寸必须 > 0
        width = checkbox.style().pixelMetric(QStyle.PM_IndicatorWidth, None, checkbox)
        height = checkbox.style().pixelMetric(QStyle.PM_IndicatorHeight, None, checkbox)
        assert width > 0
        assert height > 0
    finally:
        checkbox.close()
