from rule_catalog import RuleCatalog, RuleEntry, _cell_text, get_shared_catalog, search_entries


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


def test_get_profession_names_empty_without_profession_entries():
    catalog = RuleCatalog(workbook_paths={})

    assert catalog.get_profession_names() == []
    assert catalog.get_profession_names("1.2") == []
    assert catalog.get_profession_names("0.3") == []


def test_get_profession_names_dedupes_and_sorts():
    catalog = RuleCatalog(workbook_paths={})
    catalog._external_entries = (
        RuleEntry("1.2", "职业", "先锋", "主体"),
        RuleEntry("1.2", "职业", "重装", "主体"),
        RuleEntry("1.2", "职业", "先锋", "重复标题"),
        RuleEntry("1.2", "职业技艺", "冲锋号令", "技艺", keywords=("近卫", "精英化零")),
        RuleEntry("0.3", "职业", "旧职业", "主体"),
    )

    assert catalog.get_profession_names() == ["先锋", "旧职业", "近卫", "重装"]
    assert catalog.get_profession_names("1.2") == ["先锋", "近卫", "重装"]
    assert catalog.get_profession_names("0.3") == ["旧职业"]


def test_get_profession_names_uses_first_keyword_of_profession_skill():
    catalog = RuleCatalog(workbook_paths={})
    catalog._external_entries = (
        RuleEntry("1.2", "职业技艺", "技能A", "正文", keywords=("辅助职业", "精英化零")),
    )

    assert catalog.get_profession_names("1.2") == ["辅助职业"]


def test_get_shared_catalog_is_singleton():
    assert get_shared_catalog() is get_shared_catalog()
