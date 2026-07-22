import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QStyle, QStyleOptionButton

from ui.fluent import apply_fluent_style


def test_fluent_style_preserves_native_checkbox_indicator_metrics():
    app = QApplication.instance() or QApplication([])
    previous_stylesheet = app.styleSheet()
    checkbox = QCheckBox("测试")
    try:
        app.setStyleSheet("")
        native_size = (
            checkbox.style().pixelMetric(QStyle.PM_IndicatorWidth, None, checkbox),
            checkbox.style().pixelMetric(QStyle.PM_IndicatorHeight, None, checkbox),
        )

        apply_fluent_style(app)
        styled_size = (
            checkbox.style().pixelMetric(QStyle.PM_IndicatorWidth, None, checkbox),
            checkbox.style().pixelMetric(QStyle.PM_IndicatorHeight, None, checkbox),
        )
        option = QStyleOptionButton()
        checkbox.initStyleOption(option)
        indicator_rect = checkbox.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, option, checkbox
        )

        assert styled_size == native_size
        assert indicator_rect.left() >= 2
    finally:
        checkbox.close()
        app.setStyleSheet(previous_stylesheet)
