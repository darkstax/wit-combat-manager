import openpyxl
import pytest

from character_card import (
    detect_character_card_rule_mode,
    import_character_card_with_report,
)
from models import RuleMode


def _new_workbook_with_sheets(sheet_names):
    workbook = openpyxl.Workbook()
    workbook.active.title = sheet_names[0]
    for name in sheet_names[1:]:
        workbook.create_sheet(name)
    return workbook


def test_detects_and_imports_synthetic_v03_character_card(tmp_path):
    path = tmp_path / "v03.xlsx"
    workbook = _new_workbook_with_sheets(["角色卡", "简化卡", "光荣之路"])
    sheet = workbook["角色卡"]
    sheet["H7"] = "旧版角色"
    sheet["H14"] = "重装"
    sheet["I21"] = 67
    sheet["AH139"] = 42
    sheet["AK139"] = 10
    sheet["AN139"] = 9
    sheet["AW139"] = 6
    sheet["AZ139"] = 4
    sheet["BI139"] = 12
    sheet["AX22"] = 5
    sheet["AH141"] = "中甲"
    workbook.save(path)
    workbook.close()

    assert detect_character_card_rule_mode(str(path)) is RuleMode.V0_3
    result = import_character_card_with_report(str(path), RuleMode.V0_3)
    unit = result.unit

    assert result.detected_rule_mode is RuleMode.V0_3
    assert unit.name == "旧版角色"
    assert (unit.current_hp, unit.max_hp) == (42, 42)
    assert (unit.speed, unit.reaction_mobility) == (9, 67)
    assert (unit.physical_resist, unit.magic_resist) == (6, 4)
    assert (unit.elemental_tenacity_current, unit.elemental_tenacity_max) == (10, 10)
    assert (unit.current_sp, unit.max_sp) == (12, 12)
    assert (unit.profession, unit.level, unit.armor_type) == ("重装", 5, "中甲")


def test_detects_and_imports_synthetic_v12_character_card(tmp_path):
    path = tmp_path / "v12.xlsx"
    workbook = _new_workbook_with_sheets(["主卡", "战斗卡", "简化卡", "职业计算表"])
    main = workbook["主卡"]
    main["D3"] = "新版角色"
    main["D9"] = "先锋"
    main["H9"] = "冲锋手"
    main["AR10"] = "精一"
    main["AX10"] = 7
    simple = workbook["简化卡"]
    simple["D3"] = 6
    simple["H8"] = 35
    simple["K24"] = 3
    simple["K25"] = 5
    simple["N22"] = 12
    simple["N23"] = 4
    simple["N24"] = 8
    simple["N25"] = 6
    simple["P22"] = "D+"
    simple["P23"] = "D2"
    simple["P24"] = 9
    simple["P25"] = 2
    workbook["职业计算表"]["G3"] = "轻甲"
    workbook.save(path)
    workbook.close()

    assert detect_character_card_rule_mode(str(path)) is RuleMode.V1_2
    result = import_character_card_with_report(str(path), "v1.2")
    unit = result.unit

    assert result.detected_rule_mode is RuleMode.V1_2
    assert unit.name == "新版角色"
    assert (unit.current_hp, unit.max_hp) == (35, 35)
    assert (unit.speed, unit.reaction_mobility) == (6, 6)
    assert (unit.physical_resist, unit.magic_resist) == (3, 5)
    assert (unit.current_sp, unit.max_sp) == (4, 12)
    assert (unit.current_stamina, unit.max_stamina) == (6, 8)
    assert (unit.effect_die, unit.auxiliary_die) == ("D+", "D2")
    assert (unit.elite_stage, unit.level, unit.weight) == (1, 7, 2)
    assert (unit.profession, unit.subprofession, unit.armor_type) == ("先锋", "冲锋手", "轻甲")


def test_character_card_rejects_selected_version_mismatch(tmp_path):
    path = tmp_path / "v03.xlsx"
    workbook = _new_workbook_with_sheets(["角色卡", "简化卡", "光荣之路"])
    workbook["角色卡"]["AH139"] = 10
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="所选规则为 v1.2.*属于 v0.3"):
        import_character_card_with_report(str(path), RuleMode.V1_2)


def test_character_card_detection_rejects_unknown_sheet_signature(tmp_path):
    path = tmp_path / "unknown.xlsx"
    workbook = _new_workbook_with_sheets(["Sheet1", "Sheet2"])
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="无法根据工作表结构识别"):
        detect_character_card_rule_mode(str(path))
