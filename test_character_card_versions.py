import openpyxl
import pytest

from character_card import (
    detect_character_card_rule_mode,
    import_character_card_with_report,
    import_from_quick_text,
    ImportResult,
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


QUICK_IMPORT_SAMPLE = """名称：干员A
职业：先锋
分支：冲锋手
等级：10
HP：35
SP：4/12
耐力上限：8
护甲：轻甲"""


def test_quick_import_parses_name_from_text_or_argument():
    unit = import_from_quick_text("名称：干员A")
    assert unit.name == "干员A"

    unit = import_from_quick_text("名称：干员A", name="参数名")
    assert unit.name == "参数名"

    unit = import_from_quick_text("这里没有任何角色信息")
    assert unit.name == "导入角色"


def test_quick_import_type_keyword_position_priority():
    # “友方”位置在“敌人”之前，位置最前者胜
    unit = import_from_quick_text("友方单位……敌人来袭")
    assert unit.unit_type == "ally"

    unit = import_from_quick_text("敌方小怪")
    assert unit.unit_type == "monster"

    unit = import_from_quick_text("玩家角色卡")
    assert unit.unit_type == "player"

    # 无类型关键词 → 默认玩家
    unit = import_from_quick_text("名称：干员A")
    assert unit.unit_type == "player"

    # 单字“敌”不参与关键词匹配：名字含“敌”不误判为怪物
    unit = import_from_quick_text("名称：无敌剑圣")
    assert unit.unit_type == "player"
    assert unit.name == "无敌剑圣"

    # 双字“敌对”仍识别为怪物
    unit = import_from_quick_text("敌对目标")
    assert unit.unit_type == "monster"


def test_quick_import_parses_extended_fields():
    unit = import_from_quick_text(QUICK_IMPORT_SAMPLE)
    assert unit.name == "干员A"
    assert unit.profession == "先锋"
    assert unit.subprofession == "冲锋手"
    assert unit.level == 10
    assert unit.max_stamina == 8
    assert unit.current_stamina == 0
    assert unit.armor_type == "轻甲"
    assert unit.max_hp == 35
    assert unit.current_sp == 4
    assert unit.max_sp == 9  # 未提供 SP上限，v1.2 默认 9


def test_quick_import_english_aliases_hp_sp():
    unit = import_from_quick_text("HP: 20\nSP: 3")
    assert unit.max_hp == 20
    assert unit.current_sp == 3

    # 忽略大小写
    unit = import_from_quick_text("hp: 22\nsp: 5")
    assert unit.max_hp == 22
    assert unit.current_sp == 5


def test_quick_import_report_returns_import_result():
    report = import_from_quick_text(QUICK_IMPORT_SAMPLE, report=True)
    assert isinstance(report, ImportResult)
    assert report.unit.name == "干员A"
    assert report.detected_rule_mode is RuleMode.V1_2
    assert report.imported_fields["max_hp"] == 35
    assert report.imported_fields["unit_type"] == "player"
    assert report.imported_fields["armor_type"] == "轻甲"
    assert report.imported_fields["level"] == 10
    assert "未识别到类型，默认为玩家" in report.warnings


def test_quick_import_defaults_and_warnings():
    report = import_from_quick_text("没有任何字段", report=True)
    assert report.unit.name == "导入角色"
    assert report.unit.max_hp == 10  # 默认值保留
    assert report.unit.level == 1
    assert report.unit.armor_type == "轻甲"
    assert "未识别到角色名称" in report.warnings
    assert "未识别到类型，默认为玩家" in report.warnings


def test_quick_import_same_line_label_values():
    # 同行多字段：名称/职业提取不被后续字段污染
    unit = import_from_quick_text("名称：干员A 职业：先锋")
    assert unit.name == "干员A"
    assert unit.profession == "先锋"


def test_quick_import_max_sp_english_alias():
    # max_sp 英文别名：忽略大小写，V0_3 下 max_sp 上限 10
    unit = import_from_quick_text("max_SP: 20", rule_mode=RuleMode.V0_3)
    assert unit.max_sp == 20

    unit = import_from_quick_text("MAX_SP: 8", rule_mode=RuleMode.V0_3)
    assert unit.max_sp == 8


def test_quick_import_word_boundary_prevents_collateral_match():
    # 英文标签词边界保护："max_SP"/"MAX_SP" 中的 "SP" 子串不得被 "SP" 标签连带命中
    unit = import_from_quick_text("max_SP: 20", rule_mode=RuleMode.V0_3)
    assert unit.max_sp == 20
    assert unit.current_sp == 0  # 不被连带填充

    unit = import_from_quick_text("MAX_SP: 20", rule_mode=RuleMode.V0_3)
    assert unit.max_sp == 20
    assert unit.current_sp == 0

    # "SP: 12" 单独粘贴仍正常提取 current_sp
    unit = import_from_quick_text("SP: 12", rule_mode=RuleMode.V0_3)
    assert unit.current_sp == 12

    # "HP" 不被 "MAXHP" 中的子串连带命中，仍取真正的 "HP: 20"
    unit = import_from_quick_text("MAXHP: 50\nHP: 20")
    assert unit.max_hp == 20


def test_quick_import_npc_keyword_maps_to_ally():
    unit = import_from_quick_text("名称：商人\nNPC")
    assert unit.unit_type == "ally"
    assert unit.name == "商人"
