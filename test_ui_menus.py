"""菜单快捷键显示测试（offscreen）。

覆盖：更多菜单（RoundMenu）中各操作的快捷键文本，以及带快捷键的操作是否
已注册到主窗口（菜单外也能用）。RoundMenu.paintEvent 会自动把
QAction.shortcut 渲染到菜单项右侧，因此这里只断言 shortcut 配置本身。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import persistence
import ui.main_window as main_window
from ui.main_window import MainWindow

SHORTCUT_MENU_TEXT = {
    "规则查询": "Ctrl+K",
    "打开规则书（PDF）...": "Ctrl+O",
    "导出战斗日志...": "Ctrl+S",
    "设置背景图片...": "Ctrl+Shift+B",
    "规则书路径（Excel）...": "",
    "背景水印强度...": "",
    "清除背景图片": "",
}
# 已注册窗口级快捷键的操作（self.addAction）与未注册的操作
WINDOW_REGISTERED_TEXTS = {"规则查询", "打开规则书（PDF）...", "导出战斗日志...", "设置背景图片..."}
UNREGISTERED_TEXTS = {"规则书路径（Excel）...", "背景水印强度...", "清除背景图片"}


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """把窗口读写的数据/日志/设置路径全部重定向到 tmp_path，避免污染真实数据。"""
    monkeypatch.setattr(main_window, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(main_window, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(main_window, "COMBAT_LOG_PATH", str(tmp_path / "combat_log.txt"))
    monkeypatch.setattr(main_window, "GM_LOG_PATH", str(tmp_path / "gm_log.txt"))
    monkeypatch.setattr(persistence, "DEFAULT_PATH", str(tmp_path / "data.json"))
    return tmp_path


def _make_window():
    _app()
    window = MainWindow()
    try:
        return window
    except Exception:
        window.deleteLater()
        raise


def _teardown(window):
    # 不调用 close()/closeEvent（会写盘），仅排入删除队列
    window.deleteLater()
    for _ in range(3):
        QApplication.processEvents()


def _menu_action(window, text):
    for action in window.more_menu.actions():
        if action.text() == text:
            return action
    raise AssertionError(f"更多菜单中找不到操作: {text!r}")


def test_more_menu_shortcut_texts(isolated_paths):
    """更多菜单中各操作的快捷键文本正确；未设快捷键的 3 项为空。"""
    window = _make_window()
    try:
        for text, expected in SHORTCUT_MENU_TEXT.items():
            assert _menu_action(window, text).shortcut().toString() == expected, text
    finally:
        _teardown(window)


def test_shortcut_actions_registered_on_window(isolated_paths):
    """带快捷键的操作已通过 addAction 注册到窗口（菜单外也能用）。"""
    window = _make_window()
    try:
        window_actions = {action.text(): action for action in window.actions()}
        for text in WINDOW_REGISTERED_TEXTS:
            assert text in window_actions, f"窗口未注册操作: {text}"
            assert window_actions[text].shortcut().toString() == SHORTCUT_MENU_TEXT[text]
        for text in UNREGISTERED_TEXTS:
            assert text not in window_actions, f"窗口不应注册无快捷键操作: {text}"
    finally:
        _teardown(window)
