"""Nonmodal searchable rule browser for WIT v0.3 and v1.2."""

from __future__ import annotations

from html import escape
from typing import Mapping, Sequence
import os

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import ComboBox, SearchLineEdit, TextBrowser, TreeWidget, isDarkTheme

from models import RuleMode
from rule_catalog import RuleCatalog, RuleEntry
from ui.fluent import THEME, THEME_DARK, animate_window_entrance, fade_in


class _CatalogLoader(QThread):
    loaded = Signal()
    failed = Signal(str)

    def __init__(self, catalog: RuleCatalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog

    def run(self):
        try:
            self.catalog.load_external()
        except Exception as exc:  # Final guard around optional local data.
            self.failed.emit(str(exc))
        else:
            self.loaded.emit()


class RuleBrowserDialog(QDialog):
    """A reusable, nonmodal rule search window.

    MainWindow should keep one instance alive and call ``open_for_version`` whenever
    the command-bar action or Ctrl+K shortcut is triggered.
    """

    def __init__(
        self,
        parent=None,
        catalog: RuleCatalog | None = None,
        initial_version: RuleMode | str | None = None,
        workbook_paths: Mapping[str, str | os.PathLike] | Sequence[str | os.PathLike] | None = None,
        is_preview: bool = False,
    ):
        super().__init__(parent)
        self.catalog = catalog or RuleCatalog(workbook_paths)
        self.is_preview = is_preview
        self._results: list[RuleEntry] = []
        self._item_entries: dict[int, RuleEntry] = {}
        self._load_started = False
        self._loader: _CatalogLoader | None = None

        self.setWindowTitle("WIT 规则查询")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.resize(980, 660)
        self.setMinimumSize(720, 480)

        self._build_ui()
        self._connect_signals()
        if initial_version is not None:
            self.set_version(initial_version)
        else:
            self._refresh_categories()
            self._refresh_results()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_loader)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("规则与资料查询")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        toolbar = QFrame()
        toolbar.setObjectName("CommandBar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        self.search_edit = SearchLineEdit()
        self.search_edit.setPlaceholderText("搜索规则、状态、职业或技艺")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("规则搜索")
        toolbar_layout.addWidget(self.search_edit, 1)

        self.version_combo = ComboBox()
        self.version_combo.setAccessibleName("规则版本")
        self.version_combo.addItem("全部版本", userData=None)
        self.version_combo.addItem("v0.3", userData=RuleMode.V0_3.value)
        self.version_combo.addItem("v1.2", userData=RuleMode.V1_2.value)
        self.version_combo.setMinimumWidth(112)
        toolbar_layout.addWidget(self.version_combo)

        self.category_combo = ComboBox()
        self.category_combo.setAccessibleName("规则类别")
        self.category_combo.setMinimumWidth(132)
        toolbar_layout.addWidget(self.category_combo)
        root.addWidget(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        result_pane = QWidget()
        result_layout = QVBoxLayout(result_pane)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(6)
        result_heading = QLabel("结果")
        result_heading.setObjectName("SectionTitle")
        result_layout.addWidget(result_heading)
        self.result_tree = TreeWidget()
        self.result_tree.setHeaderHidden(True)
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setUniformRowHeights(True)
        self.result_tree.setAccessibleName("查询结果")
        self.empty_hint = QLabel("未配置规则书路径：请在 更多 → 规则书路径（Excel）中设置")
        self.empty_hint.setObjectName("SecondaryText")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.hide()
        result_layout.addWidget(self.empty_hint, 1)
        result_layout.addWidget(self.result_tree, 1)
        splitter.addWidget(result_pane)

        detail_pane = QWidget()
        detail_layout = QVBoxLayout(detail_pane)
        detail_layout.setContentsMargins(4, 0, 0, 0)
        detail_layout.setSpacing(6)
        self.detail_title = QLabel("选择一项查看详情")
        self.detail_title.setObjectName("SectionTitle")
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("SecondaryText")
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.detail_meta)
        self.detail_text = TextBrowser()
        self.detail_text.setOpenExternalLinks(False)
        self.detail_text.setAccessibleName("规则详情")
        detail_layout.addWidget(self.detail_text, 1)
        splitter.addWidget(detail_pane)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([370, 590])
        root.addWidget(splitter, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("SecondaryText")
        root.addWidget(self.status_label)

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._close_shortcut = QShortcut(QKeySequence("Escape"), self)

    def _connect_signals(self):
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self._refresh_results)

        self.search_edit.textChanged.connect(lambda: self._refresh_timer.start())
        self.version_combo.currentIndexChanged.connect(self._on_version_changed)
        self.category_combo.currentIndexChanged.connect(self._refresh_results)
        self.result_tree.currentItemChanged.connect(self._show_current_entry)
        self.result_tree.itemActivated.connect(lambda item, _column: self._show_current_entry(item))
        self._search_shortcut.activated.connect(self.search_edit.setFocus)
        self._close_shortcut.activated.connect(self.hide)

    def showEvent(self, event):
        super().showEvent(event)
        animate_window_entrance(self, duration=160)
        self.search_edit.setFocus(Qt.OtherFocusReason)
        self._start_external_load()

    def open_for_version(self, version: RuleMode | str | None = None, query: str | None = None):
        """Show, focus and optionally retarget the existing browser window."""

        if version is not None:
            self.set_version(version)
        if query is not None:
            self.search_edit.setText(query)
            self.search_edit.selectAll()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_edit.setFocus(Qt.ShortcutFocusReason)

    def set_version(self, version: RuleMode | str | None):
        value = RuleMode.coerce(version).value if version is not None else None
        index = self.version_combo.findData(value)
        self.version_combo.setCurrentIndex(max(0, index))
        self._refresh_categories()
        self._refresh_results()

    def focus_search(self, query: str | None = None):
        if query is not None:
            self.search_edit.setText(query)
            self.search_edit.selectAll()
        self.search_edit.setFocus(Qt.ShortcutFocusReason)

    def _start_external_load(self):
        if self._load_started or self.catalog.external_loaded:
            return
        self._load_started = True
        if not self.catalog.workbook_paths:
            self.catalog.load_external()
            self._on_catalog_loaded()
            return
        kind = "预览" if self.is_preview else "本地"
        self.status_label.setText(f"正在载入 {len(self.catalog.workbook_paths)} 份{kind}资料表…")
        self._loader = _CatalogLoader(self.catalog, self)
        self._loader.loaded.connect(self._on_catalog_loaded)
        self._loader.failed.connect(self._on_catalog_failed)
        self._loader.finished.connect(self._loader.deleteLater)
        self._loader.start()

    def _on_catalog_loaded(self):
        self._refresh_categories()
        self._refresh_results()
        errors = self.catalog.errors
        if errors:
            self.status_label.setToolTip("\n".join(errors))
        self._loader = None

    def _on_catalog_failed(self, message: str):
        self.status_label.setText("本地资料表载入失败，请检查规则书工作簿文件")
        self.status_label.setToolTip(message)
        self._loader = None

    def _shutdown_loader(self):
        loader = self._loader
        if loader is not None and loader.isRunning():
            loader.wait(10000)

    def _on_version_changed(self):
        self._refresh_categories()
        self._refresh_results()

    def _refresh_categories(self):
        previous = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("全部类别", userData=None)
        self.category_combo.addItem("战斗规则", userData="rules")
        self.category_combo.addItem("职业与战技", userData="professions")
        self.category_combo.addItem("源石技艺", userData="arts")
        index = self.category_combo.findData(previous)
        self.category_combo.setCurrentIndex(max(0, index))
        self.category_combo.blockSignals(False)

    def _refresh_results(self):
        current_item = self.result_tree.currentItem()
        current = self._entry_for_item(current_item)
        selected_key = self._entry_key(current) if current else None

        matches = self.catalog.search(
            query=self.search_edit.text(),
            version=self.version_combo.currentData(),
            category=None,
            limit=None,
        )
        section = self.category_combo.currentData()
        self._results = [
            entry for entry in matches
            if section is None or _entry_section(entry) == section
        ]
        selected_item = self._populate_tree(selected_key)

        if self._results:
            if selected_item is None:
                if self.search_edit.text().strip():
                    selected_item = self._first_entry_item()
                else:
                    root = self.result_tree.invisibleRootItem()
                    selected_item = root.child(0) if root.childCount() else None
            self.result_tree.setCurrentItem(selected_item)
            self._show_current_entry(selected_item)
        else:
            self.detail_title.setText("没有匹配结果")
            self.detail_meta.clear()
            self.detail_text.clear()

        configured = bool(self.catalog.workbook_paths) or bool(self._results)
        if not self._results and not configured:
            self.empty_hint.show()
            self.result_tree.hide()
            state = "未配置规则书"
        elif self.is_preview:
            self.empty_hint.hide()
            self.result_tree.show()
            state = "预览规则数据"
        else:
            self.empty_hint.hide()
            self.result_tree.show()
            state = "资料表已载入" if self.catalog.external_loaded else "正在准备本地资料表"
        error_note = f"，{len(self.catalog.errors)} 份资料读取异常" if self.catalog.errors else ""
        self.status_label.setText(f"{len(self._results)} 条结果 · {state}{error_note}")

    def _populate_tree(self, selected_key: tuple[str, str, str, str] | None):
        self.result_tree.blockSignals(True)
        self.result_tree.clear()
        self._item_entries.clear()
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
        selected_item = None
        show_versions = self.version_combo.currentData() is None

        for entry in sorted(self._results, key=_entry_tree_sort_key):
            path = _entry_tree_path(entry)
            if show_versions:
                path = (f"v{entry.version}",) + path
            parent = self.result_tree.invisibleRootItem()
            prefix: tuple[str, ...] = ()
            for label in path:
                prefix += (label,)
                item = nodes.get(prefix)
                if item is None:
                    item = QTreeWidgetItem(parent, [label])
                    item.setToolTip(0, label)
                    nodes[prefix] = item
                parent = item

            if _entry_is_folder(entry):
                item = parent
            else:
                item = QTreeWidgetItem(parent, [entry.title])
            item.setToolTip(0, entry.source)
            self._item_entries[id(item)] = entry
            if self._entry_key(entry) == selected_key:
                selected_item = item

        self.result_tree.expandAll()
        self.result_tree.blockSignals(False)
        return selected_item

    def _first_entry_item(self):
        iterator = self.result_tree.invisibleRootItem()
        stack = [iterator.child(index) for index in reversed(range(iterator.childCount()))]
        while stack:
            item = stack.pop()
            if self._entry_for_item(item) is not None:
                return item
            stack.extend(item.child(index) for index in reversed(range(item.childCount())))
        return None

    def _entry_for_item(self, item: QTreeWidgetItem | None) -> RuleEntry | None:
        return self._item_entries.get(id(item)) if item is not None else None

    @staticmethod
    def _entry_key(entry: RuleEntry) -> tuple[str, str, str, str]:
        return entry.version, entry.category, entry.title, entry.source

    def _show_current_entry(self, item: QTreeWidgetItem | None, _previous=None):
        entry = self._entry_for_item(item)
        if entry is None:
            if item is not None:
                self.detail_title.setText(item.text(0))
                self.detail_meta.setText(f"目录 · {_descendant_entry_count(item, self._item_entries)} 项")
                self.detail_text.clear()
                fade_in(self.detail_text, duration=120, start_opacity=0.8)
            return
        self.detail_title.setText(entry.title)
        self.detail_meta.setText(f"v{entry.version} · {entry.category} · {entry.source}")
        paragraphs = "".join(
            f"<p>{escape(line)}</p>" for line in entry.body.splitlines() if line.strip()
        )
        if not paragraphs:
            paragraphs = "<p>此条目没有附加说明。</p>"
        text_color = THEME_DARK["text"] if isDarkTheme() else THEME["text"]
        self.detail_text.setHtml(f"""
            <style>
                body {{ color: {text_color}; font-family: 'Segoe UI', 'Microsoft YaHei UI';
                       font-size: 13px; line-height: 1.55; }}
                p {{ margin: 0 0 9px 0; }}
            </style>
            {paragraphs}
        """)
        fade_in(self.detail_text, duration=120, start_opacity=0.8)


def _entry_section(entry: RuleEntry) -> str:
    """Map the detailed catalog categories to the three user-facing sections."""

    if entry.category in {"职业", "职业技艺"}:
        return "professions"
    if entry.category == "被动技艺":
        return "arts" if "源石技艺" in entry.keywords else "professions"
    if entry.category in {"源石技艺", "召唤物"}:
        return "arts"
    return "rules"


def _entry_tree_path(entry: RuleEntry) -> tuple[str, ...]:
    """Return folder labels only; the caller adds leaf entries where needed."""

    section = _entry_section(entry)
    if section == "professions":
        profession = entry.title if entry.category == "职业" else _owner_keyword(entry)
        if entry.category == "职业":
            return ("职业与战技", profession)
        kind = "被动" if entry.category == "被动技艺" else "战技"
        return ("职业与战技", profession, kind)

    if section == "arts":
        if entry.version == RuleMode.V0_3.value:
            major = entry.keywords[0] if entry.keywords else "其他流派"
            minor = entry.keywords[1] if len(entry.keywords) > 1 else "通用"
            return ("源石技艺", major, minor)
        school = _owner_keyword(entry)
        kind = {
            "被动技艺": "被动",
            "召唤物": "召唤物",
        }.get(entry.category, "法术与技艺")
        return ("源石技艺", school, kind)

    return ("战斗规则", entry.category)


def _entry_is_folder(entry: RuleEntry) -> bool:
    return entry.category == "职业"


def _owner_keyword(entry: RuleEntry) -> str:
    return entry.keywords[0] if entry.keywords else "其他"


def _entry_tree_sort_key(entry: RuleEntry) -> tuple:
    section_rank = {"rules": 0, "professions": 1, "arts": 2}
    return (
        entry.version,
        section_rank[_entry_section(entry)],
        tuple(part.casefold() for part in _entry_tree_path(entry)),
        entry.title.casefold(),
    )


def _descendant_entry_count(
    item: QTreeWidgetItem,
    item_entries: Mapping[int, RuleEntry],
) -> int:
    count = 1 if id(item) in item_entries else 0
    for index in range(item.childCount()):
        count += _descendant_entry_count(item.child(index), item_entries)
    return count
