import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from rule_catalog import RuleEntry, search_entries
from ui.rule_browser import RuleBrowserDialog, _entry_section, _entry_tree_path


class _StaticCatalog:
    def __init__(self, entries):
        self._entries = tuple(entries)
        self.external_loaded = True
        self.workbook_paths = {}
        self.errors = ()

    def search(self, query="", version=None, category=None, limit=300):
        return search_entries(self._entries, query, version, category, limit)

    def load_external(self):
        return self._entries


def _app():
    return QApplication.instance() or QApplication([])


def _child(parent: QTreeWidgetItem, label: str) -> QTreeWidgetItem:
    for index in range(parent.childCount()):
        item = parent.child(index)
        if item.text(0) == label:
            return item
    raise AssertionError(f"missing tree node {label!r}")


def test_detailed_categories_map_to_broad_sections_and_owner_folders():
    active = RuleEntry(
        "1.2", "职业技艺", "冲锋", "向前移动",
        keywords=("先锋", "精英化零"),
    )
    passive = RuleEntry(
        "1.2", "被动技艺", "战术整备", "获得增益",
        keywords=("先锋", "精英化一", "职业技艺"),
    )
    arts = RuleEntry(
        "1.2", "源石技艺", "炎爆", "造成法术伤害",
        keywords=("塑能术", "精英化零"),
    )
    old_arts = RuleEntry(
        "0.3", "源石技艺", "点燃", "施加灼烧",
        keywords=("能量", "火焰"),
    )

    assert _entry_section(active) == "professions"
    assert _entry_tree_path(active) == ("职业与战技", "先锋", "战技")
    assert _entry_tree_path(passive) == ("职业与战技", "先锋", "被动")
    assert _entry_tree_path(arts) == ("源石技艺", "塑能术", "法术与技艺")
    assert _entry_tree_path(old_arts) == ("源石技艺", "能量", "火焰")


def test_tree_nests_profession_children_and_search_keeps_leaf_searchable():
    _app()
    catalog = _StaticCatalog([
        RuleEntry("1.2", "职业", "先锋", "职业概览", keywords=("战斗职业",)),
        RuleEntry(
            "1.2", "职业技艺", "冲锋", "向前移动",
            keywords=("先锋", "精英化零"),
        ),
        RuleEntry(
            "1.2", "被动技艺", "战术整备", "获得增益",
            keywords=("先锋", "精英化一", "职业技艺"),
        ),
    ])
    dialog = RuleBrowserDialog(catalog=catalog, initial_version="1.2")

    root = dialog.result_tree.invisibleRootItem()
    section = _child(root, "职业与战技")
    profession = _child(section, "先锋")
    assert _child(_child(profession, "战技"), "冲锋")
    assert _child(_child(profession, "被动"), "战术整备")

    dialog.search_edit.setText("冲锋")
    dialog._refresh_results()
    root = dialog.result_tree.invisibleRootItem()
    profession = _child(_child(root, "职业与战技"), "先锋")
    leaf = _child(_child(profession, "战技"), "冲锋")
    dialog.result_tree.setCurrentItem(leaf)
    assert dialog.detail_title.text() == "冲锋"
    dialog.close()


def test_category_filter_uses_only_three_broad_sections():
    _app()
    dialog = RuleBrowserDialog(catalog=_StaticCatalog([]))

    assert [dialog.category_combo.itemText(index) for index in range(dialog.category_combo.count())] == [
        "全部类别", "战斗规则", "职业与战技", "源石技艺",
    ]
    dialog.close()


def test_browser_does_not_truncate_large_catalogs_and_folders_show_counts():
    _app()
    entries = [
        RuleEntry("1.2", "战斗动作", f"动作 {index:03d}", "说明")
        for index in range(550)
    ]
    dialog = RuleBrowserDialog(catalog=_StaticCatalog(entries), initial_version="1.2")

    assert len(dialog._results) == 550
    root = dialog.result_tree.invisibleRootItem()
    section = _child(root, "战斗规则")
    assert dialog.result_tree.currentItem() is section
    dialog.result_tree.setCurrentItem(section)
    dialog._show_current_entry(section)
    assert dialog.detail_title.text() == "战斗规则"
    assert dialog.detail_meta.text() == "目录 · 550 项"
    dialog.close()
