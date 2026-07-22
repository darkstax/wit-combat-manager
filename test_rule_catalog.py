from rule_catalog import RuleCatalog, RuleEntry, _cell_text, search_entries


def test_rule_catalog_contains_both_versions_without_external_files():
    catalog = RuleCatalog(workbook_paths={})

    assert catalog.search("先攻", version="0.3")
    assert catalog.search("先攻", version="1.2")
    assert not catalog.external_loaded


def test_search_entries_filters_and_prioritizes_title_matches():
    entries = [
        RuleEntry("1.2", "规则", "元素损伤", "元素韧性与爆发"),
        RuleEntry("1.2", "状态", "元素屏障", "提供临时元素韧性"),
        RuleEntry("0.3", "规则", "元素损伤", "旧版元素爆发"),
    ]

    results = search_entries(entries, "元素", version="1.2")

    assert {entry.title for entry in results} == {"元素损伤", "元素屏障"}
    assert all(entry.version == "1.2" for entry in results)


def test_workbook_image_formula_prefix_is_not_exposed():
    raw = '=DISPIMG("ID_A157D79EE7224A18B6A03F6C67C70505",1); 先锋'

    assert _cell_text(raw) == "先锋"
