from rule_catalog import (
    WORKBOOK_FILENAMES,
    RuleCatalog,
    RuleEntry,
    _cell_text,
    get_shared_catalog,
    refresh_shared_catalog,
    scan_directory_for_workbooks,
    search_entries,
)


def test_rule_catalog_contains_both_versions_without_external_files():
    catalog = RuleCatalog(workbook_paths={})

    assert not catalog.search("先攻")
    assert not catalog.external_loaded

    catalog._external_entries = (
        RuleEntry("0.3", "战斗流程", "先攻顺序", "按速度从高到低行动", keywords=("速度",)),
        RuleEntry("1.2", "战斗流程", "先攻模式", "团队先攻或逐人先攻", keywords=("团队先攻",)),
    )

    assert catalog.search("先攻", version="0.3")
    assert catalog.search("先攻", version="1.2")
    assert not catalog.search("不存在的关键词", version="1.2")


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


def test_scan_directory_finds_workbooks(tmp_path):
    for filename in WORKBOOK_FILENAMES.values():
        (tmp_path / filename).touch()

    paths = scan_directory_for_workbooks(tmp_path)

    assert set(paths) == set(WORKBOOK_FILENAMES)
    assert all(path.is_file() for path in paths.values())


def test_scan_directory_matches_case_insensitively_and_omits_missing(tmp_path):
    (tmp_path / "V1.2.战斗职业（非法术部分）.XLSX").touch()
    (tmp_path / "V1.2.角色卡.PLUS .XLSX").touch()

    paths = scan_directory_for_workbooks(tmp_path)

    assert set(paths) == {"v12_professions", "v12_card"}


def test_scan_directory_returns_empty_for_missing_directory(tmp_path):
    assert scan_directory_for_workbooks(tmp_path / "不存在") == {}


def test_refresh_shared_catalog_replaces_instance():
    original = get_shared_catalog()
    refreshed = refresh_shared_catalog({})

    assert refreshed is not original
    assert get_shared_catalog() is refreshed
